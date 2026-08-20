"""Knobs do MAS — Inc 1.

Lê as envs que controlam se o LLM é usado e quantas iterações de feedback são
permitidas. Valor inválido degrada para um log + padrão, nunca lança.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_VALID_MODES = frozenset({"auto", "on", "off"})


def agent_llm_mode() -> str:  # noqa: D401 -- reads env with fallback
    """``PRECOSBOT_AGENT_LLM``: ``"auto"`` | ``"on"`` | ``"off"``, default ``"auto"``.

    * ``auto`` — usa o LLM se responder dentro do timeout, senão segue determinístico.
    * ``on``   — exige o LLM; se indisponível, retorna erro estruturado.
    * ``off``  — força modo puramente determinístico (rollback sem rede).
    """
    raw = os.getenv("PRECOSBOT_AGENT_LLM", "auto").strip().lower()
    if raw in _VALID_MODES:
        return raw
    logger.warning(
        f"[agents] PRECOSBOT_AGENT_LLM tem valor inválido '{raw}'; usando 'auto'."
    )
    return "auto"


def agent_max_iterations() -> int:  # noqa: D401 -- reads env with fallback
    """``PRECOSBOT_AGENT_MAX_ITERATIONS``, default ``2``.

    Cap de re-scrapes no loop de feedback (Analista → Scraper). O primeiro scrape
    já é a iteração 0; este valor limita *re*-execuções adicionais do scraper.
    """
    raw = os.getenv("PRECOSBOT_AGENT_MAX_ITERATIONS", "2")
    try:
        n = int(raw)
    except ValueError:
        logger.warning(
            f"[agents] PRECOSBOT_AGENT_MAX_ITERATIONS inválido '{raw}'; usando 2."
        )
        return 2
    if n < 0 or n > 10:  # saneia para evitar loop infinito por config errada
        logger.warning(f"[agents] PRECOSBOT_AGENT_MAX_ITERATIONS {n} fora do range; clamp a [1,10].")
        return max(1, min(n, 10))
    return n


def llm_base_url() -> str:
    return os.getenv("PRECOSBOT_LLM_BASE_URL", "http://127.0.0.1:11434/v1")


def llm_model() -> str:
    return os.getenv("PRECOSBOT_LLM_MODEL", "qwen2.5:3b")


def llm_api_key() -> str:
    return os.getenv("PRECOSBOT_LLM_API_KEY", "ollama")


def llm_timeout() -> float:
    raw = os.getenv("PRECOSBOT_LLM_TIMEOUT", "60")
    try:
        t = float(raw)
    except ValueError:
        logger.warning(f"[agents] PRECOSBOT_LLM_TIMEOUT inválido; usando 60.")
        return 60.0
    return max(5.0, min(t, 300.0))


def llm_num_predict() -> int:
    raw = os.getenv("PRECOSBOT_LLM_NUM_PREDICT", "2048")
    try:
        n = int(raw)
    except ValueError:
        logger.warning(f"[agents] PRECOSBOT_LLM_NUM_PREDICT inválido; usando 2048.")
        return 2048
    return max(64, min(n, 131072))
