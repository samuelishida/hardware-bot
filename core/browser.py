"""core/browser.py — Facade Page/ElementHandle/Context sobre o CDP do Lightpanda (Inc 3).

Espelha a superfície da API Playwright que os scrapers usam, mas fala com o CDP
server do Lightpanda via ``core/cdp.py``. Isola todo o protocolo CDP em 2 arquivos
(``cdp.py`` + ``browser.py``); os scrapers trocam ``page.*``/``context.*`` por esta
facade com churn mecânico.

Descobertas do spike (Inc 1) aplicadas aqui:
- Setup obrigatório: ``Target.createBrowserContext`` → ``Target.createTarget`` →
  ``Target.attachToTarget`` (retorna ``sessionId``); **todos** os comandos de página
  incluem ``sessionId``.
- Lightpanda suporta **1 browser context + 1 página por vez** → ``new_context``
  descarta o contexto anterior (scraping sequencial).
- ``Network.setBlockedURLs`` usa ``urlPatterns`` (não ``urls``).
- ``DOM.querySelector`` requer ``DOM.getDocument`` antes (cacheia o root nodeId).
- ``:has-text('X')`` (ML) não é CSS válido → traduz para query JS por ``textContent``.
- ``wait_until`` mapeado: commit→``frameNavigated``, domcontentloaded→+espera,
  load→``loadEventFired``, networkidle→``lifecycleEvent``/espera fixa.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Awaitable

from core.cdp import CDPClient, CDPError

logger = logging.getLogger(__name__)

# Timeout padrão de navegação (ms) — espelha o Playwright.
DEFAULT_NAV_TIMEOUT = 30_000

# Regex para :has-text('...') (pseudo-classe do Playwright usada pelo ML).
_HAS_TEXT_RE = re.compile(r":has-text\('([^']*)'\)")


def _translate_has_text(sel: str) -> str | None:
    """Traduz ``base:has-text('X')`` para uma expressão JS que retorna bool.

    ``DOM.querySelector`` não entende ``:has-text()``. Retorna uma expressão JS
    que verifica se existe um elemento ``base`` cujo ``textContent`` contém ``X``
    (case-insensitive, espelhando o ``:has-text`` do Playwright). ``None`` se o
    seletor não tiver ``:has-text``.
    """
    m = _HAS_TEXT_RE.search(sel)
    if not m:
        return None
    text = m.group(1)
    base = sel[: m.start()].strip() or "*"
    return (
        "(() => {"
        f"const els = Array.from(document.querySelectorAll({json.dumps(base)}));"
        f"const t = {json.dumps(text)}.toLowerCase();"
        "return els.some(el => (el.textContent || '').toLowerCase().includes(t));"
        "})()"
    )


class Response:
    """Resposta de ``Page.goto`` — espelha o mínimo que o pichau usa (``.text()``)."""

    def __init__(self, page: "Page"):
        self._page = page

    async def text(self) -> str:
        return await self._page.content()


class ElementHandle:
    """Handle de um elemento — re-consulta o seletor a cada operação.

    O CDP do Lightpanda não mantém handles persistentes de forma simples; guardamos
    o seletor e re-executamos a query JS quando necessário.
    """

    def __init__(self, page: "Page", selector: str):
        self._page = page
        self._selector = selector

    async def inner_text(self) -> str:
        return await self._page._eval_selector_text(self._selector)

    async def click(self) -> None:
        await self._page._eval_selector_click(self._selector)

    async def fill(self, text: str) -> None:
        await self._page._eval_selector_fill(self._selector, text)


class Route:
    """Rota interceptada (``Fetch.requestPaused``) — espelha o ``route`` do Playwright.

    O ML aborta image/media/font e continua o resto.
    """

    def __init__(self, page: "Page", request_id: str, resource_type: str):
        self.request = SimpleNamespace(resource_type=resource_type)
        self._page = page
        self._request_id = request_id
        self._handled = False

    async def abort(self) -> None:
        if self._handled:
            return
        self._handled = True
        await self._page._send(
            "Fetch.failRequest",
            {"requestId": self._request_id, "errorReason": "BlockedByClient"},
        )

    async def continue_(self) -> None:
        if self._handled:
            return
        self._handled = True
        await self._page._send("Fetch.continueRequest", {"requestId": self._request_id})


class Page:
    """Página Lightpanda — espelha a superfície Playwright usada pelos scrapers."""

    def __init__(self, browser: "LightpandaBrowser", session_id: str):
        self._browser = browser
        self._client = browser._client
        self._session_id = session_id
        self._root_node_id: int | None = None
        self._url_cache: str = ""
        self.context = SimpleNamespace(close=self._close_context)
        self.keyboard = SimpleNamespace(press=self._keyboard_press)
        self.mouse = SimpleNamespace(wheel=self._mouse_wheel)

    # ------------------------------------------------------------------
    # Comandos CDP (com sessionId)
    # ------------------------------------------------------------------

    async def _send(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        return await self._client.send(method, {**(params or {}), "sessionId": self._session_id}, timeout=timeout)

    async def _close_context(self) -> None:
        await self._browser._dispose_context()

    # ------------------------------------------------------------------
    # Navegação
    # ------------------------------------------------------------------

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = DEFAULT_NAV_TIMEOUT) -> Response | None:
        """Navega e aguarda o estado ``wait_until``. Retorna um ``Response``."""
        timeout_s = timeout / 1000.0
        nav_fut = asyncio.create_task(
            self._client.wait_event("Page.frameNavigated", timeout=timeout_s)
        )
        try:
            result = await self._send("Page.navigate", {"url": url}, timeout=timeout_s)
        except Exception as e:
            logger.warning(f"[browser] Page.navigate falhou: {e}")
            return None
        if result.get("errorText"):
            logger.warning(f"[browser] navegação falhou: {result['errorText']}")
            return None
        try:
            await nav_fut  # commit alcançado
        except asyncio.TimeoutError:
            logger.warning(f"[browser] timeout aguardando frameNavigated para {url}")
            return None
        self._root_node_id = None  # DOM mudou; re-obter root
        try:
            await self._refresh_url()
        except Exception:
            pass

        if wait_until == "load":
            try:
                await self._client.wait_event("Page.loadEventFired", timeout=timeout_s)
            except asyncio.TimeoutError:
                pass
        elif wait_until == "domcontentloaded":
            await asyncio.sleep(0.5)  # deixa o DOM assentar
        elif wait_until == "networkidle":
            try:
                await self._client.wait_event("Page.lifecycleEvent", timeout=timeout_s)
            except asyncio.TimeoutError:
                await asyncio.sleep(3)  # fallback determinístico
        return Response(self)

    async def wait_for_timeout(self, ms: int) -> None:
        await asyncio.sleep(ms / 1000.0)

    async def wait_for_selector(self, selector: str, timeout: int = 30_000) -> ElementHandle | None:
        """Polla o seletor até resolver ou estourar o timeout."""
        deadline = asyncio.get_event_loop().time() + timeout / 1000.0
        while True:
            el = await self.query_selector(selector)
            if el is not None:
                return el
            if asyncio.get_event_loop().time() >= deadline:
                return None
            await asyncio.sleep(0.2)

    # ------------------------------------------------------------------
    # Conteúdo / avaliação
    # ------------------------------------------------------------------

    async def content(self) -> str:
        r = await self._send(
            "Runtime.evaluate",
            {"expression": "document.documentElement.outerHTML", "returnByValue": True},
        )
        return r.get("result", {}).get("value", "")

    async def title(self) -> str:
        r = await self._send(
            "Runtime.evaluate",
            {"expression": "document.title", "returnByValue": True},
        )
        return r.get("result", {}).get("value", "")

    @property
    def url(self) -> str:
        # url é lido via evaluate (propriedade síncrona no Playwright; aqui é async
        # mas os scrapers usam ``page.url`` como atributo — retornamos o último
        # conhecido ou lemos sob demanda via evaluate).
        return self._url_cache

    async def _refresh_url(self) -> str:
        r = await self._send(
            "Runtime.evaluate",
            {"expression": "location.href", "returnByValue": True},
        )
        self._url_cache = r.get("result", {}).get("value", "")
        return self._url_cache

    async def evaluate(self, js: str, arg: Any = None) -> Any:
        """Avalia uma função-expression JS, opcionalmente com ``arg`` serializado.

        Padrão dos scrapers: ``(${js})(${json.dumps(arg)})``. Sem arg: ``(${js})()``.
        """
        if arg is None:
            expression = f"({js})()"
        else:
            expression = f"({js})({json.dumps(arg)})"
        r = await self._send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
        )
        if "exceptionDetails" in r:
            raise RuntimeError(f"evaluate falhou: {r['exceptionDetails']}")
        return r.get("result", {}).get("value")

    # ------------------------------------------------------------------
    # Seletores
    # ------------------------------------------------------------------

    async def _get_document_root(self) -> int:
        if self._root_node_id is None:
            doc = await self._send("DOM.getDocument", {})
            self._root_node_id = doc["root"]["nodeId"]
        return self._root_node_id

    async def query_selector(self, selector: str) -> ElementHandle | None:
        """Retorna um ``ElementHandle`` ou ``None`` se o seletor não resolver."""
        has_text_js = _translate_has_text(selector)
        if has_text_js is not None:
            r = await self._send(
                "Runtime.evaluate",
                {"expression": has_text_js, "returnByValue": True},
            )
            if r.get("result", {}).get("value"):
                return ElementHandle(self, selector)
            return None
        try:
            root_id = await self._get_document_root()
            r = await self._send("DOM.querySelector", {"nodeId": root_id, "selector": selector})
        except CDPError:
            return None
        if "nodeId" in r:
            return ElementHandle(self, selector)
        return None

    # ------------------------------------------------------------------
    # Ações em elementos (via JS)
    # ------------------------------------------------------------------

    async def _eval_selector_text(self, selector: str) -> str:
        js = _translate_has_text(selector)
        if js is not None:
            # :has-text → retorna o textContent do primeiro match
            m = _HAS_TEXT_RE.search(selector)
            text = m.group(1)
            base = selector[: m.start()].strip() or "*"
            expr = (
                "(() => {"
                f"const els = Array.from(document.querySelectorAll({json.dumps(base)}));"
                f"const t = {json.dumps(text)}.toLowerCase();"
                "const el = els.find(e => (e.textContent || '').toLowerCase().includes(t));"
                "return el ? (el.innerText || '') : '';"
                "})()"
            )
        else:
            expr = (
                "(() => {"
                f"const el = document.querySelector({json.dumps(selector)});"
                "return el ? (el.innerText || '') : '';"
                "})()"
            )
        r = await self._send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return r.get("result", {}).get("value", "")

    async def _eval_selector_click(self, selector: str) -> None:
        js = _translate_has_text(selector)
        if js is not None:
            m = _HAS_TEXT_RE.search(selector)
            text = m.group(1)
            base = selector[: m.start()].strip() or "*"
            expr = (
                "(() => {"
                f"const els = Array.from(document.querySelectorAll({json.dumps(base)}));"
                f"const t = {json.dumps(text)}.toLowerCase();"
                "const el = els.find(e => (e.textContent || '').toLowerCase().includes(t));"
                "if (el) { el.click(); return true; } return false;"
                "})()"
            )
        else:
            expr = (
                "(() => {"
                f"const el = document.querySelector({json.dumps(selector)});"
                "if (el) { el.click(); return true; } return false;"
                "})()"
            )
        await self._send("Runtime.evaluate", {"expression": expr, "returnByValue": True})

    async def _eval_selector_fill(self, selector: str, text: str) -> None:
        """Preenche um input de forma React-compatível (setter nativo + evento input)."""
        expr = (
            "(() => {"
            f"const el = document.querySelector({json.dumps(selector)});"
            "if (!el) return false;"
            "const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;"
            "const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;"
            f"setter.call(el, {json.dumps(text)});"
            "el.dispatchEvent(new Event('input', {bubbles: true}));"
            "el.dispatchEvent(new Event('change', {bubbles: true}));"
            "return true;"
            "})()"
        )
        await self._send("Runtime.evaluate", {"expression": expr, "returnByValue": True})

    # ------------------------------------------------------------------
    # Teclado / mouse
    # ------------------------------------------------------------------

    async def _keyboard_press(self, key: str) -> None:
        code = _KEY_CODES.get(key, key)
        await self._send("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": code})
        await self._send("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": code})

    async def _mouse_wheel(self, dx: int, dy: int) -> None:
        await self._send(
            "Input.dispatchMouseEvent",
            {"type": "mouseWheel", "x": 0, "y": 0, "deltaX": dx, "deltaY": dy},
        )

    # ------------------------------------------------------------------
    # Headers / interceptação / screenshot
    # ------------------------------------------------------------------

    async def set_extra_http_headers(self, headers: dict) -> None:
        await self._send("Network.setExtraHTTPHeaders", {"headers": headers})

    async def route(self, pattern: str, handler: Callable[[Route], Awaitable[None]]) -> None:
        """Intercepta requisições via ``Fetch.enable`` (padrão Playwright suportado)."""
        await self._send(
            "Fetch.enable",
            {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]},
        )

        async def _on_paused(params: dict) -> None:
            request_id = params.get("requestId")
            resource_type = params.get("resourceType", "other")
            if not request_id:
                return
            route = Route(self, request_id, resource_type)
            try:
                await handler(route)
            except Exception as e:
                logger.warning(f"[browser] handler de route falhou: {e}")
                await route.continue_()

        self._client.on("Fetch.requestPaused", _on_paused)

    async def screenshot(self, path: str, full_page: bool = False) -> None:
        r = await self._send("Page.captureScreenshot", {"format": "png"})
        data = r.get("data")
        if not data:
            raise RuntimeError("captureScreenshot sem dados")
        Path(path).write_bytes(base64.b64decode(data))


# Mapa de teclas comuns para Input.dispatchKeyEvent
_KEY_CODES = {
    "Enter": "Enter",
    "Tab": "Tab",
    "Escape": "Escape",
    "ArrowDown": "ArrowDown",
    "ArrowUp": "ArrowUp",
    "Backspace": "Backspace",
    "Delete": "Delete",
}


class Context:
    """Browser context Lightpanda — 1 página por vez (restrição do CDP)."""

    def __init__(self, browser: "LightpandaBrowser", session_id: str, opts: dict):
        self._browser = browser
        self._client = browser._client
        self._session_id = session_id
        self._opts = opts
        self._bc_id = opts.get("_bc_id")
        self._page: Page | None = None

    async def _send(self, method: str, params: dict | None = None) -> dict:
        return await self._client.send(method, {**(params or {}), "sessionId": self._session_id})

    async def new_page(self) -> Page:
        if self._page is None:
            self._page = Page(self._browser, self._session_id)
            await self._apply_opts()
        return self._page

    async def _apply_opts(self) -> None:
        """Aplica user_agent / extra_http_headers / viewport do ``new_context``."""
        opts = self._opts
        try:
            if opts.get("user_agent"):
                await self._send("Network.setUserAgentOverride", {"userAgent": opts["user_agent"]})
        except Exception as e:
            logger.debug(f"[browser] setUserAgentOverride falhou: {e}")
        try:
            extra = dict(opts.get("extra_http_headers") or {})
            if opts.get("locale"):
                extra.setdefault("Accept-Language", f"{opts['locale']},{opts['locale']};q=0.9,en;q=0.8")
            if extra:
                await self._send("Network.setExtraHTTPHeaders", {"headers": extra})
        except Exception as e:
            logger.debug(f"[browser] setExtraHTTPHeaders falhou: {e}")
        try:
            vp = opts.get("viewport")
            if vp:
                await self._send(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": vp.get("width", 1920), "height": vp.get("height", 1080), "deviceScaleFactor": 1, "mobile": False},
                )
        except Exception as e:
            logger.debug(f"[browser] setDeviceMetricsOverride falhou: {e}")

    async def add_init_script(self, js: str) -> None:
        await self._send("Page.addScriptToEvaluateOnNewDocument", {"source": js})

    async def add_cookies(self, cookies: list) -> None:
        mapped = []
        for c in cookies:
            item = {
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
            }
            if c.get("expires"):
                item["expires"] = c["expires"]
            if c.get("secure"):
                item["secure"] = True
            if c.get("httpOnly"):
                item["httpOnly"] = True
            mapped.append(item)
        if mapped:
            await self._send("Network.setCookies", {"cookies": mapped})

    async def cookies(self) -> list:
        r = await self._send("Network.getCookies", {})
        return r.get("cookies", [])

    async def close(self) -> None:
        await self._browser._dispose_context()


class LightpandaBrowser:
    """Gerencia o subprocesso ``lightpanda serve`` + 1 browser context compartilhado.

    Espelha o design atual de "1 browser compartilhado" (RAM da VM). ``new_context``
    descarta o contexto anterior (Lightpanda suporta 1 por vez).
    """

    def __init__(self, executable: str | None = None, host: str = "127.0.0.1", port: int = 9222):
        self.executable = executable or os.getenv("LIGHTPANDA_BIN") or shutil.which("lightpanda") or "lightpanda"
        self.host = host
        self.port = port
        self.ws_url = f"ws://{host}:{port}/"
        self._proc: subprocess.Popen | None = None
        self._ws: Any = None
        self._client: CDPClient | None = None
        self._context: Context | None = None

    async def start(self) -> None:
        """Sobe o subprocesso (se preciso) e conecta o websocket."""
        if self._client is not None:
            return
        if self._proc is None:
            env = {**os.environ, "LIGHTPANDA_DISABLE_TELEMETRY": "true"}
            self._proc = subprocess.Popen(
                [self.executable, "serve", "--host", self.host, "--port", str(self.port), "--log-level", "warn"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        import websockets

        for _ in range(100):
            try:
                # ping_interval=None: desativa o keepalive do websockets. O CDP do
                # Lightpanda não responde a pings durante cargas pesadas (ex.: SPA
                # de e-commerce), e o default de 20s derruba a conexão com
                # "keepalive ping timeout" (erro 1011) no meio do scrape.
                self._ws = await websockets.connect(
                    self.ws_url,
                    open_timeout=1,
                    max_size=64 * 1024 * 1024,
                    ping_interval=None,
                )
                self._client = CDPClient(self._ws)
                await self._client.connect()
                return
            except Exception:
                await asyncio.sleep(0.2)
        raise RuntimeError(f"lightpanda serve não subiu em {self.ws_url}")

    async def new_context(self, **opts) -> Context:
        """Cria um browser context + target + attach. Descarta o anterior."""
        if self._client is None:
            await self.start()
        if self._context is not None:
            await self._context.close()
        bc = await self._client.send("Target.createBrowserContext", {})
        bc_id = bc["browserContextId"]
        tgt = await self._client.send("Target.createTarget", {"url": "about:blank", "browserContextId": bc_id})
        tgt_id = tgt["targetId"]
        att = await self._client.send("Target.attachToTarget", {"targetId": tgt_id, "flatten": True})
        session_id = att["sessionId"]
        opts = dict(opts)
        opts["_bc_id"] = bc_id
        self._context = Context(self, session_id, opts)
        return self._context

    async def _dispose_context(self) -> None:
        if self._context is not None:
            try:
                await self._client.send("Target.disposeBrowserContext", {"browserContextId": self._context._bc_id})
            except Exception:
                pass
            self._context = None

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None

    async def close(self) -> None:
        await self.stop()


__all__ = ["LightpandaBrowser", "Context", "Page", "ElementHandle", "Route", "Response"]
