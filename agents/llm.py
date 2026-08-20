"""Cliente LLM async OpenAI-compatible sobre ``httpx`` (Inc 1).

Endpoint padrao: Ollama em `127.0.0.1:11434/v1` (configuravel via envs de
``agents/config.py``). A regra de ouro do Ollama e **sempre enviar ``num_predict``**
em ``options`` — modelos thinking como o minimax retornam conteudo vazio quando ele eh
pequeno demais, e respostas runaway estourariam a memoria da VM.

Padrao de degradacao: qualquer erro de conexao/timeout/http>=500 → :class:`LLMUnavailable`;
JSON invalido apos retries → :class:`LLMError`. O pipeline nunca quebra por causa do LLM;
``auto`` continua deterministico, ``on`` retorna erro estruturado.

A API OpenAI-compatible expoe `/v1/chat/completions` (Ollama serve em base_url + "/chat/...").
"""

from __future__ import annotations

import json
import logging
from typing import Any

try:  # httpx já é dependency existente do precosbot (requirements.txt)
    from httpx import AsyncClient as _AsyncClient, HTTPError, HTTPStatusError
except Exception:  # pragma: no cover - never happens in this codebase
    raise ImportError("httpx is required by agents.llm; install it before using the MAS.")

from agents.config import (
    llm_base_url, llm_model, llm_api_key, llm_timeout, llm_num_predict,
)


logger = logging.getLogger(__name__)


def _clamp_num_predict(n: int) -> int:
    """Clampa o limite de tokens para [64, 131072] (evita truncamento/runaway)."""
    return int(min(max(n, 64), 131072))


class LLMError(Exception):  # noqa: D102 -- application-level exception family
    """Erro de processamento/parse da resposta do LLM."""

    pass


class LLMUnavailable(LLMError):  # noqa: D102 -- service-down variant
    """O endpoint Ollama não respondeu (conexão/timeout/http>=500)."""

    def __init__(self, base_url="", cause=None) -> None:
        super().__init__(f"LLM unavailable at {base_url!r}: {cause}")  # type: ignore[arg-type]


def _extract_first_content(response_text):
    """Extrai o primeiro ``content`` (str) do JSON de resposta OpenAI-compatible."""
    try:
        data = json.loads(response_text or "{}")
    except Exception as exc:  # pragma: no cover - network path
        raise LLMError(f"LLM retornou texto não-JSON: {response_text[:200]!r}") from exc

    choices = data.get("choices")
    if not isinstance(choices, list):
        return ""
    for c in choices:
        if not isinstance(c, dict):
            continue
        message = c.get("message") or {}
        if isinstance(message, dict):
            content = message.get("content", "")
        else:
            content = getattr(message, "content", "")
        if content:
            return str(content).strip()
    return ""


def _parse_json_lenient(text: str) -> Any:
    """Parse JSON tolerante a cercas markdown (```json ... ```) e texto ao redor.

    Modelos pequenos locais ignoram ``response_format`` e envolvem a resposta em
    cercas; extrai o primeiro bloco ``{...}`` balanceado antes de desistir.
    """
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()
    try:
        return json.loads(candidate)
    except Exception:
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        return json.loads(candidate[start : end + 1])
    raise ValueError(f"nenhum objeto JSON encontrado em: {text[:200]!r}")


def _raise_for_status(resp, endpoint: str) -> None:
    """HTTP >= 500 → :class:`LLMUnavailable` (serviço fora); 4xx → :class:`LLMError`.

    Tratar 4xx como "unavailable" esconderia erros de request (ex.: 400 por payload
    inválido) atrás de uma mensagem de serviço fora do ar.
    """
    if resp.status_code >= 500:
        raise LLMUnavailable(endpoint, cause=HTTPStatusError(resp.status_code, request=None, response=resp))  # type: ignore[arg-type]
    if not resp.is_success:
        raise LLMError(f"LLM retornou HTTP {resp.status_code}")


class LLMClient:
    """Cliente OpenAI-compatible mínimo e robusto para Ollama.

    Sempre envia ``num_predict`` explícito (via ``options.num_predict``) na criação do
    chat, prevenindo respostas vazias/runaway de modelos thinking.
    """

    def __init__(  # noqa: D417 -- configurable for VM/remote Ollama
        self,
        base_url=None,
        model=None,
        api_key=None,
        timeout=60.0,
        num_predict=2048,
    ) -> None:
        if base_url is not None:
            self.base_url = (base_url.rstrip("/") + "/chat/completions")  # type: ignore[operator] -- str concat with default fallbacks
        else:
            self.base_url = llm_base_url().rstrip("/") + "/chat/completions"
        self.model = model or llm_model()
        self.api_key = api_key if api_key is not None else llm_api_key()
        self.timeout = max(5.0, min(float(timeout), 300.0))
        # num_predict >= 64 para evitar truncamento de JSON; cap alto mas seguro (128k).
        self.num_predict = _clamp_num_predict(num_predict if num_predict is not None else llm_num_predict())

    def _endpoint(self) -> str:
        """Base URL sem o sufixo ``/chat/completions`` (para mensagens de erro)."""
        return self.base_url.rsplit("/chat/completions", 1)[0]

    def _build_payload(self, system: str, user: str, *, json_mode: bool) -> dict[str, Any]:
        """Monta o payload OpenAI-compatible com limite de tokens explícito.

        Envia ``max_tokens`` no topo (campo que o handler OpenAI-compatible do Ollama
        realmente lê) e mantém ``options.num_predict`` para compatibilidade com
        versões/endpoints que o honram. ``max_tokens`` é o que previne respostas
        vazias/runaway de modelos thinking.
        """
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system or ""},
                {"role": "user", "content": user or ""},
            ],
            "stream": False,
            "max_tokens": self.num_predict,
            "options": {"num_predict": self.num_predict},  # regra Ollama de ouro (backward-compat)
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    async def _post(self, payload: dict[str, Any]) -> str:
        """Envia um POST e retorna o texto da primeira ``content`` do LLM.

        Regras de Ollama thinking models (ex.: minimax): se a resposta vier com conteúdo
        vazio, repetimos uma vez dobrando o limite de tokens. Qualquer erro de transporte
        (conexão/timeout) → :class:`LLMUnavailable`.
        """
        try:
            async with _AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.base_url, json=payload)  # noqa: S368 -- trusted localhost Ollama endpoint

                _raise_for_status(resp, self._endpoint())

                content = _extract_first_content(resp.text)
                if not content:
                    # Modelo thinking: 1ª resposta vazia → retry com limite dobrado.
                    retry_payload = dict(payload)
                    doubled = _clamp_num_predict(self.num_predict * 2)
                    retry_payload["max_tokens"] = doubled
                    opts = dict(retry_payload.get("options") or {})
                    opts["num_predict"] = doubled
                    retry_payload["options"] = opts
                    resp2 = await client.post(self.base_url, json=retry_payload)  # noqa: S368 -- trusted localhost endpoint
                    _raise_for_status(resp2, self._endpoint())
                    content = _extract_first_content(resp2.text)

                return content
        except HTTPError as exc:  # ConnectError, TimeoutException, etc.
            raise LLMUnavailable(self._endpoint(), cause=exc) from exc

    async def chat(self, system: str, user: str, *, json_mode: bool = False) -> str:
        """Retorna o texto da primeira ``content`` do LLM."""
        payload = self._build_payload(system, user, json_mode=json_mode)
        return await self._post(payload)

    async def chat_json(self, system: str, user: str, *, retries: int = 0) -> dict[str, Any]:
        """Retorna ``{...}`` parseado do LLM.

        Pede explicitamente ``response_format.json_object``; em caso de JSON inválido,
        reenvia o erro no prompt (com até ``retries`` tentativas extras). OLLAMA: a versão
        local pode ignorar response_format; por isso fazemos parse + retry com correção.
        """
        last_err: Exception | None = None
        current_system = system
        for _ in range(retries + 1):
            raw = await self._post(self._build_payload(current_system, user, json_mode=True))
            if not raw.strip():
                last_err = LLMError("LLM retornou conteúdo vazio")
                continue
            try:
                data = _parse_json_lenient(raw)
            except Exception as exc:
                last_err = LLMError(f"LLM retornou JSON inválido: {raw[:200]!r}")
                current_system = (
                    f"{system}\n\n---\nO JSON anterior estava inválido: {raw[:300]!r}. "
                    "Responda APENAS com um objeto JSON válido."
                )
                continue
            if isinstance(data, dict):
                return data
            last_err = LLMError(f"LLM retornou JSON não-objeto: {type(data).__name__}")
            current_system = (
                f"{system}\n\n---\nA resposta anterior não era um objeto JSON. "
                "Responda APENAS com um objeto JSON válido."
            )
        raise last_err or LLMUnavailable(self._endpoint())


_client_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Singleton do cliente LLM (lê envs de ``agents/config``)."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = LLMClient()
    return _client_singleton


__all__ = [
    "LLMClient",
    "LLMError",
    "LLMUnavailable",
    "get_llm_client",
]

