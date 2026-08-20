"""tests/test_llm_client.py — Inc 1: LLMClient (OpenAI-compatible sobre httpx).

Cobre a regra de ouro do Ollama (``num_predict`` sempre explícito), o retry
com ``num_predict`` dobrado quando o conteúdo vem vazio (modelos thinking),
a degradação para :class:`LLMUnavailable` em falha de rede/HTTP e o parse de
JSON com retry em ``chat_json``.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.llm import LLMClient, LLMError, LLMUnavailable


def _resp(content: str, *, status: int = 200) -> MagicMock:
    """Monta um httpx.Response fake com o ``content`` do primeiro choice."""
    body = {"choices": [{"message": {"content": content}}]}
    r = MagicMock()
    r.is_success = status < 400
    r.status_code = status
    r.text = json.dumps(body)
    return r


def _client_with_posts(*responses) -> tuple[LLMClient, AsyncMock]:
    """Cria um LLMClient cujo ``_AsyncClient`` retorna as respostas dadas."""
    client = LLMClient(base_url="http://127.0.0.1:11434/v1", model="m", num_predict=128)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=list(responses))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return client, mock_client


class TestPayload:
    def test_num_predict_always_explicit(self):
        client = LLMClient(base_url="http://x/v1", model="m", num_predict=128)
        payload = client._build_payload("sys", "usr", json_mode=False)
        assert payload["options"]["num_predict"] == 128
        assert payload["model"] == "m"
        assert payload["stream"] is False

    def test_num_predict_clamped_to_minimum(self):
        client = LLMClient(base_url="http://x/v1", model="m", num_predict=1)
        assert client.num_predict >= 64
        payload = client._build_payload("s", "u", json_mode=False)
        assert payload["options"]["num_predict"] >= 64

    def test_json_mode_sets_response_format(self):
        client = LLMClient(base_url="http://x/v1", model="m")
        payload = client._build_payload("s", "u", json_mode=True)
        assert payload["response_format"] == {"type": "json_object"}


class TestChat:
    async def test_chat_returns_first_content(self):
        client, mock = _client_with_posts(_resp("olá"))
        with patch("agents.llm._AsyncClient", return_value=mock):
            out = await client.chat("sys", "usr")
        assert out == "olá"

    async def test_chat_retries_with_doubled_num_predict_when_empty(self):
        """Modelo thinking: 1ª resposta vazia → retry com num_predict dobrado."""
        client, mock = _client_with_posts(_resp(""), _resp("conteúdo"))
        with patch("agents.llm._AsyncClient", return_value=mock):
            out = await client.chat("sys", "usr")
        assert out == "conteúdo"
        # duas chamadas: a segunda deve ter num_predict dobrado
        assert mock.post.await_count == 2
        first_payload = mock.post.await_args_list[0].kwargs["json"]
        second_payload = mock.post.await_args_list[1].kwargs["json"]
        assert second_payload["options"]["num_predict"] == 2 * first_payload["options"]["num_predict"]

    async def test_chat_http_error_raises_unavailable(self):
        client, mock = _client_with_posts(_resp("x", status=500))
        with patch("agents.llm._AsyncClient", return_value=mock):
            with pytest.raises(LLMUnavailable):
                await client.chat("sys", "usr")


class TestChatJson:
    async def test_chat_json_parses_dict(self):
        client, mock = _client_with_posts(_resp(json.dumps({"valid": True, "reason": "ok"})))
        with patch("agents.llm._AsyncClient", return_value=mock):
            data = await client.chat_json("sys", "usr")
        assert data == {"valid": True, "reason": "ok"}

    async def test_chat_json_invalid_raises_llm_error(self):
        client, mock = _client_with_posts(_resp("não é json"))
        with patch("agents.llm._AsyncClient", return_value=mock):
            with pytest.raises(LLMError):
                await client.chat_json("sys", "usr")


class TestExtractFirstContent:
    def test_extracts_content(self):
        from agents.llm import _extract_first_content
        body = json.dumps({"choices": [{"message": {"content": "  hi  "}}]})
        assert _extract_first_content(body) == "hi"

    def test_non_json_raises(self):
        from agents.llm import _extract_first_content
        with pytest.raises(LLMError):
            _extract_first_content("isso não é json")
