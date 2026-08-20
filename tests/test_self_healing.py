"""
tests/test_self_healing.py — Unit tests para agents/self_healing.py (Inc 6).

Fake page (AsyncMock com content()/query_selector()/inner_text()) + LLM mockado.
Casos: seletor válido → persistido e retornado; inválido → None; LLM fora → None;
LLM mode off → None; HTML truncado no prompt.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.self_healing import attempt_self_heal, _truncate_html, MAX_HTML_CHARS


def _fake_page(html: str, selector_result: dict | None) -> AsyncMock:
    """Fake page Playwright.

    ``selector_result``: ``None`` → query_selector retorna None;
    senão ``{"selector": "<css>", "text": "<texto>"}`` → só esse seletor resolve.
    """
    page = AsyncMock()
    page.content = AsyncMock(return_value=html)

    async def _query_selector(sel: str):
        if selector_result and selector_result["selector"] == sel:
            el = AsyncMock()
            el.inner_text = AsyncMock(return_value=selector_result["text"])
            return el
        return None

    page.query_selector = AsyncMock(side_effect=_query_selector)
    return page


def _fake_llm(proposal: dict) -> AsyncMock:
    llm = AsyncMock()
    llm.chat_json = AsyncMock(return_value=proposal)
    return llm


@pytest.fixture(autouse=True)
def _pin_llm_mode_auto():
    """Põe ``agent_llm_mode`` em 'auto' para os testes não dependerem de env externa."""
    with patch("agents.self_healing.agent_llm_mode", return_value="auto"):
        yield


class TestAttemptSelfHeal:
    @pytest.mark.asyncio
    async def test_valid_price_selector_persisted_and_returned(self):
        page = _fake_page("<html><body>...</body></html>", {"selector": "span.novo-preco", "text": "R$ 1.234,56"})
        llm = _fake_llm({"selector": "span.novo-preco", "confidence": 0.9, "reasoning": "ok"})

        with patch("agents.self_healing.upsert_override", new=AsyncMock()) as upsert:
            selector = await attempt_self_heal("kabum", "price", page, llm_client=llm)

        assert selector == "span.novo-preco"
        upsert.assert_awaited_once_with("kabum", "price", "span.novo-preco")

    @pytest.mark.asyncio
    async def test_invalid_selector_returns_none(self):
        # LLM propõe um seletor que não resolve na página
        page = _fake_page("<html></html>", {"selector": "span.existe", "text": "R$ 100,00"})
        llm = _fake_llm({"selector": "span.nao-existe", "confidence": 0.8, "reasoning": "?"})

        with patch("agents.self_healing.upsert_override", new=AsyncMock()) as upsert:
            selector = await attempt_self_heal("kabum", "price", page, llm_client=llm)

        assert selector is None
        upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_price_selector_with_unparseable_text_returns_none(self):
        # Seletor resolve, mas o texto não é preço BRL → inválido para element='price'
        page = _fake_page("<html></html>", {"selector": "span.x", "text": "sem preço"})
        llm = _fake_llm({"selector": "span.x", "confidence": 0.7, "reasoning": "?"})

        with patch("agents.self_healing.upsert_override", new=AsyncMock()) as upsert:
            selector = await attempt_self_heal("kabum", "price", page, llm_client=llm)

        assert selector is None
        upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_title_element_validates_on_nonempty_text(self):
        page = _fake_page("<html></html>", {"selector": "h1.title", "text": "Placa RTX 4060"})
        llm = _fake_llm({"selector": "h1.title", "confidence": 0.85, "reasoning": "ok"})

        with patch("agents.self_healing.upsert_override", new=AsyncMock()) as upsert:
            selector = await attempt_self_heal("pichau", "title", page, llm_client=llm)

        assert selector == "h1.title"
        upsert.assert_awaited_once_with("pichau", "title", "h1.title")

    @pytest.mark.asyncio
    async def test_llm_unavailable_returns_none(self):
        from agents.llm import LLMUnavailable

        page = _fake_page("<html></html>", None)
        llm = AsyncMock()
        llm.chat_json = AsyncMock(side_effect=LLMUnavailable("ollama fora"))

        with patch("agents.self_healing.upsert_override", new=AsyncMock()) as upsert:
            selector = await attempt_self_heal("kabum", "price", page, llm_client=llm)

        assert selector is None
        upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_llm_mode_off_returns_none_without_calling_llm(self):
        page = _fake_page("<html></html>", None)
        llm = _fake_llm({"selector": "span.x", "confidence": 0.9, "reasoning": "?"})

        with patch("agents.self_healing.agent_llm_mode", return_value="off"):
            selector = await attempt_self_heal("kabum", "price", page, llm_client=llm)

        assert selector is None
        llm.chat_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_llm_client_fetched_when_not_injected(self):
        page = _fake_page("<html></html>", {"selector": "span.ok", "text": "R$ 999,00"})
        llm = _fake_llm({"selector": "span.ok", "confidence": 0.9, "reasoning": "ok"})

        with (
            patch("agents.self_healing.get_llm_client", return_value=llm) as get_client,
            patch("agents.self_healing.upsert_override", new=AsyncMock()),
        ):
            selector = await attempt_self_heal("kabum", "price", page)

        assert selector == "span.ok"
        get_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_page_content_failure_returns_none(self):
        page = AsyncMock()
        page.content = AsyncMock(side_effect=Exception("page fechada"))
        llm = _fake_llm({"selector": "span.x", "confidence": 0.9, "reasoning": "?"})

        selector = await attempt_self_heal("kabum", "price", page, llm_client=llm)
        assert selector is None
        llm.chat_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_html_truncated_in_prompt(self):
        big_html = "<html>" + "a" * (MAX_HTML_CHARS + 10_000) + "</html>"
        page = _fake_page(big_html, {"selector": "span.ok", "text": "R$ 10,00"})
        llm = _fake_llm({"selector": "span.ok", "confidence": 0.9, "reasoning": "ok"})

        with patch("agents.self_healing.upsert_override", new=AsyncMock()):
            await attempt_self_heal("kabum", "price", page, llm_client=llm)

        # o payload enviado ao LLM contém o HTML truncado (~50KB), não o integral
        _, user_payload = llm.chat_json.await_args.args
        assert len(user_payload) < len(big_html)
        assert "truncado" in user_payload


class TestTruncateHtml:
    def test_short_html_unchanged(self):
        assert _truncate_html("<html>ok</html>") == "<html>ok</html>"

    def test_long_html_truncated(self):
        html = "x" * (MAX_HTML_CHARS + 5)
        out = _truncate_html(html)
        assert len(out) < MAX_HTML_CHARS + 50
        assert out.startswith("x" * MAX_HTML_CHARS)
        assert "truncado" in out
