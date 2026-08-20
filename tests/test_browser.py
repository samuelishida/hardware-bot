"""
tests/test_browser.py — Unit tests para core/browser.py (Inc 3).

Usa um CDPClient fake (sem rede) que registra comandos e retorna respostas
programadas. Cobre: setup do browser context, goto/wait_until, evaluate,
content/title, query_selector (incl. :has-text), interação (click/fill/keyboard/
mouse), cookies, route, screenshot.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from core.browser import LightpandaBrowser, Page, ElementHandle, Route


class FakeCDPClient:
    """CDPClient fake: registra sends e responde conforme programado."""

    def __init__(self):
        self.sent: list[tuple[str, dict]] = []
        self.responses: dict[str, dict] = {}
        self.handlers: dict[str, list] = {}
        self.closed = False

    async def connect(self):
        pass

    async def close(self):
        self.closed = True

    async def send(self, method, params=None, timeout=30.0):
        self.sent.append((method, params or {}))
        # respostas por método (default vazio)
        return self.responses.get(method, {})

    async def wait_event(self, method, timeout=30.0):
        # goto espera frameNavigated; retorna imediatamente
        return {"frame": {"id": "FID-1"}}

    def on(self, method, handler):
        self.handlers.setdefault(method, []).append(handler)

    # helpers
    def set_response(self, method, result):
        self.responses[method] = result


@pytest.fixture
def fake_cdp():
    return FakeCDPClient()


async def _make_browser(fake_cdp) -> LightpandaBrowser:
    browser = LightpandaBrowser(executable="lightpanda")
    browser._client = fake_cdp
    browser._ws = AsyncMock()
    return browser


class TestBrowserContext:
    @pytest.mark.asyncio
    async def test_new_context_does_setup_flow(self, fake_cdp):
        fake_cdp.set_response("Target.createBrowserContext", {"browserContextId": "BID-1"})
        fake_cdp.set_response("Target.createTarget", {"targetId": "TID-1"})
        fake_cdp.set_response("Target.attachToTarget", {"sessionId": "SID-1"})

        browser = await _make_browser(fake_cdp)
        ctx = await browser.new_context(user_agent="UA", viewport={"width": 1920, "height": 1080})

        methods = [m for m, _ in fake_cdp.sent]
        assert "Target.createBrowserContext" in methods
        assert "Target.createTarget" in methods
        assert "Target.attachToTarget" in methods
        # attach com flatten
        attach = [p for m, p in fake_cdp.sent if m == "Target.attachToTarget"][0]
        assert attach["flatten"] is True
        assert ctx._session_id == "SID-1"
        await browser.close()

    @pytest.mark.asyncio
    async def test_new_context_applies_opts(self, fake_cdp):
        fake_cdp.set_response("Target.createBrowserContext", {"browserContextId": "BID-1"})
        fake_cdp.set_response("Target.createTarget", {"targetId": "TID-1"})
        fake_cdp.set_response("Target.attachToTarget", {"sessionId": "SID-1"})

        browser = await _make_browser(fake_cdp)
        ctx = await browser.new_context(
            user_agent="UA", locale="pt-BR",
            extra_http_headers={"X-Custom": "1"},
            viewport={"width": 1366, "height": 768},
        )
        page = await ctx.new_page()

        methods = [m for m, _ in fake_cdp.sent]
        assert "Network.setUserAgentOverride" in methods
        assert "Network.setExtraHTTPHeaders" in methods
        assert "Emulation.setDeviceMetricsOverride" in methods
        # todos os comandos de página incluem sessionId
        for m, p in fake_cdp.sent:
            if m.startswith(("Network.", "Emulation.")):
                assert p.get("sessionId") == "SID-1"
        await browser.close()


class TestPage:
    @pytest.mark.asyncio
    async def test_goto_sends_session_id_and_returns_response(self, fake_cdp):
        fake_cdp.set_response("Page.navigate", {})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")

        resp = await page.goto("https://example.com/", wait_until="domcontentloaded")

        assert resp is not None
        nav = [p for m, p in fake_cdp.sent if m == "Page.navigate"][0]
        assert nav["url"] == "https://example.com/"
        assert nav["sessionId"] == "SID-1"
        await browser.close()

    @pytest.mark.asyncio
    async def test_goto_returns_none_on_error(self, fake_cdp):
        fake_cdp.set_response("Page.navigate", {"errorText": "net::ERR_FAILED"})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")
        resp = await page.goto("https://example.com/")
        assert resp is None
        await browser.close()

    @pytest.mark.asyncio
    async def test_evaluate_with_arg(self, fake_cdp):
        fake_cdp.set_response("Runtime.evaluate", {"result": {"value": 5}})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")

        # padrão real dos scrapers: arrow function SEM parênteses externos
        val = await page.evaluate("(arg) => arg.x + arg.y", {"x": 2, "y": 3})

        assert val == 5
        expr = [p for m, p in fake_cdp.sent if m == "Runtime.evaluate"][0]["expression"]
        assert expr == "((arg) => arg.x + arg.y)({\"x\": 2, \"y\": 3})"
        await browser.close()

    @pytest.mark.asyncio
    async def test_evaluate_without_arg(self, fake_cdp):
        fake_cdp.set_response("Runtime.evaluate", {"result": {"value": "ok"}})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")
        val = await page.evaluate("() => 'ok'")
        assert val == "ok"
        expr = [p for m, p in fake_cdp.sent if m == "Runtime.evaluate"][0]["expression"]
        assert expr == "(() => 'ok')()"
        await browser.close()

    @pytest.mark.asyncio
    async def test_content(self, fake_cdp):
        fake_cdp.set_response("Runtime.evaluate", {"result": {"value": "<html><body>x</body></html>"}})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")
        assert await page.content() == "<html><body>x</body></html>"
        await browser.close()

    @pytest.mark.asyncio
    async def test_title(self, fake_cdp):
        fake_cdp.set_response("Runtime.evaluate", {"result": {"value": "Título"}})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")
        assert await page.title() == "Título"
        await browser.close()

    @pytest.mark.asyncio
    async def test_query_selector_found(self, fake_cdp):
        fake_cdp.set_response("DOM.getDocument", {"root": {"nodeId": 1}})
        fake_cdp.set_response("DOM.querySelector", {"nodeId": 7})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")

        el = await page.query_selector("a[href*='/produto/']")

        assert isinstance(el, ElementHandle)
        # getDocument chamado antes de querySelector
        methods = [m for m, _ in fake_cdp.sent]
        assert methods.index("DOM.getDocument") < methods.index("DOM.querySelector")
        await browser.close()

    @pytest.mark.asyncio
    async def test_query_selector_not_found(self, fake_cdp):
        fake_cdp.set_response("DOM.getDocument", {"root": {"nodeId": 1}})
        fake_cdp.set_response("DOM.querySelector", {})  # sem nodeId
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")
        assert await page.query_selector("span.nope") is None
        await browser.close()

    @pytest.mark.asyncio
    async def test_query_selector_has_text(self, fake_cdp):
        # :has-text → usa Runtime.evaluate, não DOM.querySelector
        fake_cdp.set_response("Runtime.evaluate", {"result": {"value": True}})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")

        el = await page.query_selector("button:has-text('Aceitar cookies')")

        assert isinstance(el, ElementHandle)
        methods = [m for m, _ in fake_cdp.sent]
        assert "DOM.querySelector" not in methods
        await browser.close()

    @pytest.mark.asyncio
    async def test_element_inner_text(self, fake_cdp):
        fake_cdp.set_response("Runtime.evaluate", {"result": {"value": "R$ 1.234,56"}})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")
        el = ElementHandle(page, "span.price")
        assert await el.inner_text() == "R$ 1.234,56"
        await browser.close()

    @pytest.mark.asyncio
    async def test_element_click(self, fake_cdp):
        fake_cdp.set_response("Runtime.evaluate", {"result": {"value": True}})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")
        el = ElementHandle(page, "button")
        await el.click()
        expr = [p for m, p in fake_cdp.sent if m == "Runtime.evaluate"][0]["expression"]
        assert "el.click()" in expr
        await browser.close()

    @pytest.mark.asyncio
    async def test_element_fill_react_compatible(self, fake_cdp):
        fake_cdp.set_response("Runtime.evaluate", {"result": {"value": True}})
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")
        el = ElementHandle(page, "input[type='email']")
        await el.fill("user@example.com")
        expr = [p for m, p in fake_cdp.sent if m == "Runtime.evaluate"][0]["expression"]
        assert "dispatchEvent(new Event('input'" in expr
        assert "user@example.com" in expr
        await browser.close()

    @pytest.mark.asyncio
    async def test_keyboard_press(self, fake_cdp):
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")
        await page._keyboard_press("Enter")
        methods = [m for m, _ in fake_cdp.sent]
        assert methods.count("Input.dispatchKeyEvent") == 2  # keyDown + keyUp
        await browser.close()

    @pytest.mark.asyncio
    async def test_mouse_wheel(self, fake_cdp):
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")
        await page._mouse_wheel(0, 300)
        wheel = [p for m, p in fake_cdp.sent if m == "Input.dispatchMouseEvent"][0]
        assert wheel["type"] == "mouseWheel"
        assert wheel["deltaY"] == 300
        await browser.close()


class TestCookiesAndRoute:
    @pytest.mark.asyncio
    async def test_add_cookies_maps_fields(self, fake_cdp):
        browser = await _make_browser(fake_cdp)
        ctx = _ctx(browser, "SID-1")
        await ctx.add_cookies([{"name": "a", "value": "1", "domain": "example.com", "path": "/"}])
        setc = [p for m, p in fake_cdp.sent if m == "Network.setCookies"][0]
        assert setc["cookies"][0]["name"] == "a"
        assert setc["cookies"][0]["domain"] == "example.com"
        assert setc["sessionId"] == "SID-1"
        await browser.close()

    @pytest.mark.asyncio
    async def test_cookies(self, fake_cdp):
        fake_cdp.set_response("Network.getCookies", {"cookies": [{"name": "a"}]})
        browser = await _make_browser(fake_cdp)
        ctx = _ctx(browser, "SID-1")
        assert await ctx.cookies() == [{"name": "a"}]
        await browser.close()

    @pytest.mark.asyncio
    async def test_route_intercepts_and_aborts(self, fake_cdp):
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")

        async def handler(route):
            if route.request.resource_type in ("image", "media", "font"):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", handler)
        # dispara o handler via Fetch.requestPaused
        paused = {"requestId": "REQ-1", "resourceType": "image"}
        for h in fake_cdp.handlers.get("Fetch.requestPaused", []):
            await h(paused)

        fail = [p for m, p in fake_cdp.sent if m == "Fetch.failRequest"]
        assert fail and fail[0]["requestId"] == "REQ-1"
        assert fail[0]["errorReason"] == "BlockedByClient"
        await browser.close()

    @pytest.mark.asyncio
    async def test_route_continues(self, fake_cdp):
        browser = await _make_browser(fake_cdp)
        page = Page(browser, "SID-1")

        async def handler(route):
            await route.continue_()

        await page.route("**/*", handler)
        for h in fake_cdp.handlers.get("Fetch.requestPaused", []):
            await h({"requestId": "REQ-2", "resourceType": "document"})

        cont = [p for m, p in fake_cdp.sent if m == "Fetch.continueRequest"]
        assert cont and cont[0]["requestId"] == "REQ-2"
        await browser.close()


def _ctx(browser, session_id):
    from core.browser import Context
    return Context(browser, session_id, {"_bc_id": "BID-1"})
