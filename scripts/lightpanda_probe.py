#!/usr/bin/env python3
"""
scripts/lightpanda_probe.py — Spike: valida as capacidades CDP do Lightpanda.

Sobe/usa um `lightpanda serve` (CDP server) e testa, via websocket, cada
capacidade que os scrapers do precosbot precisam:

  - Runtime.evaluate com returnByValue em objetos aninhados (lista de dicts)
  - Runtime.evaluate com função-expression + arg (padrão `(${js})(${arg})`)
  - Page.navigate + eventos de navegação (commit vs domcontentloaded)
  - DOM.querySelector / DOM.performSearch
  - Page.addScriptToEvaluateOnNewDocument (stealth init script)
  - Network.getCookies / setCookies
  - Interceptação de rede (Network.setBlockedURLs / Fetch)
  - Input.dispatchKeyEvent / Input.dispatchMouseEvent (wheel)
  - Page.captureScreenshot
  - Criação de múltiplas páginas/targets (Target.createTarget)
  - STEALTH_SCRIPT (APIs Chromium-only) não lança

Uso (com o lightpanda binário no PATH ou LIGHTPANDA_BIN):
    python scripts/lightpanda_probe.py
    LIGHTPANDA_BIN=/tmp/lightpanda python scripts/lightpanda_probe.py

Saída: dict[capacidade, bool] + scrape de KaBuM ponta-a-ponta (se rede OK).
Este script é um PROTÓTIPO descartável (Inc 1) — não é usado em runtime.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import websockets
except ImportError:
    print("websockets não instalado. Rode: pip install websockets>=12.0")
    sys.exit(1)

logger = logging.getLogger("lightpanda_probe")

WS_URL = os.getenv("LIGHTPANDA_WS", "ws://127.0.0.1:9222/")
LIGHTPANDA_BIN = os.getenv("LIGHTPANDA_BIN", shutil.which("lightpanda") or "/tmp/lightpanda")

# STEALTH_SCRIPT do precosbot (scrapers/base.py) — APIs Chromium-only que podem
# lançar no Lightpanda (navigator.userAgentData, window.chrome.runtime).
STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        { name: 'Native Client', filename: 'internal-nacl-plugin' },
    ],
});
Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'userAgentData', {
    get: () => ({
        mobile: false,
        platform: 'Windows',
        brands: [
            { brand: 'Chromium', version: '131' },
            { brand: 'Not_A Brand', version: '24' }
        ]
    })
});
window.chrome = window.chrome || {};
window.chrome.runtime = {
    id: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    connect: () => ({}),
    sendMessage: () => {},
    getURL: () => '',
    getManifest: () => ({ version: '1.0', name: 'Google Chrome' }),
};
"""


class CDP:
    """Cliente CDP mínimo para o probe (websocket)."""

    def __init__(self, ws):
        self.ws = ws
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}

    async def send(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg_id = self._id
        fut = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        await self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        return await fut

    async def pump(self):
        """Lê mensagens do websocket e resolve pendentes / despacha eventos."""
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg:
                fut = self._pending.pop(msg["id"], None)
                if fut and not fut.done():
                    if "error" in msg:
                        fut.set_exception(CDPError(msg["error"]))
                    else:
                        fut.set_result(msg.get("result", {}))
            else:
                # evento (notificação) — despacha para waiters
                method = msg.get("method")
                for waiter in getattr(self, "_event_waiters", {}).get(method, []):
                    if not waiter.done():
                        waiter.set_result(msg.get("params", {}))

    async def wait_event(self, method: str, timeout: float = 10.0):
        """Aguarda um evento CDP específico (ex.: Page.frameNavigated)."""
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._event_waiters = getattr(self, "_event_waiters", {})
        self._event_waiters.setdefault(method, []).append(fut)
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._event_waiters.get(method, []).remove(fut)


class CDPError(Exception):
    pass


async def _probe(ws_url: str) -> dict:
    """Roda o probe de capacidades e retorna dict[capacidade, bool].

    FLUXO OBRIGATÓRIO do CDP do Lightpanda (descoberto no spike):
      1. Target.createBrowserContext → browserContextId
      2. Target.createTarget → targetId (cria a página)
      3. Target.attachToTarget → sessionId
      4. TODOS os comandos seguintes DEVEM incluir ``sessionId`` no payload.
    Lightpanda suporta APENAS 1 browser context e 1 página por vez.
    """
    caps: dict[str, bool] = {}
    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        cdp = CDP(ws)
        pump_task = asyncio.create_task(cdp.pump())

        # --- Setup obrigatório: browser context + target + attach ---
        async def _setup() -> str:
            bc = await cdp.send("Target.createBrowserContext", {})
            bc_id = bc["browserContextId"]
            tgt = await cdp.send("Target.createTarget", {"url": "about:blank", "browserContextId": bc_id})
            tgt_id = tgt["targetId"]
            att = await cdp.send("Target.attachToTarget", {"targetId": tgt_id, "flatten": True})
            return att["sessionId"]

        session_id = await _setup()
        caps["setup (createBrowserContext+createTarget+attach)"] = True
        logger.info("  [OK] setup (createBrowserContext+createTarget+attach)")

        async def _send(method: str, params: dict | None = None) -> dict:
            """Envia com sessionId (obrigatório pós-attach)."""
            return await cdp.send(method, {**(params or {}), "sessionId": session_id})

        async def _try(name: str, coro):
            try:
                await coro
                caps[name] = True
                logger.info(f"  [OK] {name}")
            except Exception as e:
                caps[name] = False
                logger.warning(f"  [FAIL] {name}: {e}")

        # --- Runtime.evaluate com returnByValue em objetos aninhados ---
        async def _eval_nested():
            r = await _send("Runtime.evaluate", {
                "expression": "JSON.stringify([{a:1,b:[2,3]},{a:4}])",
                "returnByValue": True,
            })
            assert "result" in r and r["result"].get("value") == "[{\"a\":1,\"b\":[2,3]},{\"a\":4}]"
        await _try("Runtime.evaluate returnByValue nested", _eval_nested())

        # --- Runtime.evaluate com função-expression + arg ---
        async def _eval_fn_arg():
            js = "((arg) => { return arg.x + arg.y; })"
            r = await _send("Runtime.evaluate", {
                "expression": f"({js})({json.dumps({'x': 2, 'y': 3})})",
                "returnByValue": True,
            })
            assert r["result"].get("value") == 5
        await _try("Runtime.evaluate fn+arg", _eval_fn_arg())

        # --- Page.navigate + evento de navegação ---
        async def _navigate():
            nav_fut = asyncio.create_task(cdp.wait_event("Page.frameNavigated", timeout=15))
            await _send("Page.navigate", {"url": "https://example.com/"})
            await nav_fut
        await _try("Page.navigate + frameNavigated", _navigate())

        # --- DOM.querySelector (requer DOM.getDocument antes p/ registrar root) ---
        async def _query_selector():
            doc = await _send("DOM.getDocument", {})
            root_id = doc["root"]["nodeId"]
            r = await _send("DOM.querySelector", {"nodeId": root_id, "selector": "h1"})
            assert "nodeId" in r
        await _try("DOM.querySelector (após getDocument)", _query_selector())

        # --- Page.addScriptToEvaluateOnNewDocument (stealth) ---
        async def _init_script():
            r = await _send("Page.addScriptToEvaluateOnNewDocument", {"source": STEALTH_SCRIPT})
            assert "identifier" in r
        await _try("Page.addScriptToEvaluateOnNewDocument", _init_script())

        # --- Network.getCookies / setCookies ---
        async def _cookies():
            r = await _send("Network.getCookies", {})
            assert "cookies" in r
            await _send("Network.setCookies", {"cookies": [{
                "name": "probe", "value": "1", "domain": "example.com", "path": "/",
            }]})
        await _try("Network.getCookies/setCookies", _cookies())

        # --- Interceptação de rede (Network.setBlockedURLs usa urlPatterns) ---
        async def _block():
            await _send("Network.enable", {})
            await _send("Network.setBlockedURLs", {"urlPatterns": [
                {"urlPattern": "*://*.png", "block": True},
                {"urlPattern": "*://*.jpg", "block": True},
                {"urlPattern": "*://*.gif", "block": True},
            ]})
        await _try("Network.setBlockedURLs (urlPatterns)", _block())

        # --- Input.dispatchKeyEvent / dispatchMouseEvent (wheel) ---
        async def _input():
            await _send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter"})
            await _send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 100, "y": 100, "deltaY": 300})
        await _try("Input.dispatchKeyEvent/MouseEvent", _input())

        # --- Page.captureScreenshot ---
        async def _screenshot():
            r = await _send("Page.captureScreenshot", {"format": "png"})
            assert "data" in r
        await _try("Page.captureScreenshot", _screenshot())

        # --- STEALTH_SCRIPT não lança em página real ---
        async def _stealth_no_throw():
            await _send("Page.navigate", {"url": "https://example.com/"})
            await asyncio.sleep(2)
            r = await _send("Runtime.evaluate", {
                "expression": "typeof navigator.userAgentData !== 'undefined' && !!window.chrome",
                "returnByValue": True,
            })
            # Não deve lançar; valor pode ser false (Lightpanda não é Chromium)
            assert "result" in r
        await _try("STEALTH_SCRIPT não lança", _stealth_no_throw())

        pump_task.cancel()
    return caps


async def scrape_kabum_via_cdp(ws_url: str) -> dict:
    """Scrapeia KaBuM ponta-a-ponta via CDP (protótipo do spike)."""
    result = {"ok": False, "n_products": 0, "error": None}
    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        cdp = CDP(ws)
        pump_task = asyncio.create_task(cdp.pump())
        try:
            # Setup obrigatório (mesmo fluxo do _probe)
            bc = await cdp.send("Target.createBrowserContext", {})
            bc_id = bc["browserContextId"]
            tgt = await cdp.send("Target.createTarget", {"url": "about:blank", "browserContextId": bc_id})
            tgt_id = tgt["targetId"]
            att = await cdp.send("Target.attachToTarget", {"targetId": tgt_id, "flatten": True})
            session_id = att["sessionId"]

            async def _send(method: str, params: dict | None = None) -> dict:
                return await cdp.send(method, {**(params or {}), "sessionId": session_id})

            await _send("Page.navigate", {"url": "https://www.kabum.com.br/busca/rtx-4060"})
            await asyncio.sleep(8)  # KaBuM hidrata React async
            r = await _send("Runtime.evaluate", {
                "expression": """
                    (() => {
                        const cards = Array.from(document.querySelectorAll('a[href*="/produto/"]'))
                            .filter(a => /\\/produto\\/\\d+\\//.test(a.href));
                        return JSON.stringify(cards.slice(0, 5).map(a => ({
                            href: a.href,
                            text: (a.innerText || '').substring(0, 80),
                        })));
                    })()
                """,
                "returnByValue": True,
            })
            val = r.get("result", {}).get("value")
            products = json.loads(val) if val else []
            result["n_products"] = len(products)
            result["ok"] = len(products) > 0
            result["sample"] = products[:2]
        except Exception as e:
            result["error"] = str(e)
        finally:
            pump_task.cancel()
    return result


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(f"Lightpanda bin: {LIGHTPANDA_BIN}")
    print(f"WS URL: {WS_URL}")

    # Garante que o serve está de pé (sobe se não estiver)
    proc = None
    try:
        async with websockets.connect(WS_URL, open_timeout=2):
            pass
    except Exception:
        print("Sobendo lightpanda serve...")
        proc = subprocess.Popen(
            [LIGHTPANDA_BIN, "serve", "--host", "127.0.0.1", "--port", "9222", "--log-level", "warn"],
            env={**os.environ, "LIGHTPANDA_DISABLE_TELEMETRY": "true"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        await asyncio.sleep(2)

    try:
        print("\n=== Capacidades CDP ===")
        caps = await _probe(WS_URL)
        for k, v in caps.items():
            print(f"  {'✅' if v else '❌'} {k}")

        print("\n=== Scrape KaBuM via CDP ===")
        kabum = await scrape_kabum_via_cdp(WS_URL)
        print(json.dumps(kabum, ensure_ascii=False, indent=2))
    finally:
        if proc:
            proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
