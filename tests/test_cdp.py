"""
tests/test_cdp.py — Unit tests para core/cdp.py (Inc 2).

Usa um websocket fake (sem rede) que responde a ``send``, emite eventos e simula
erro/timeout. Cobre: correlação id→resposta, eventos fora de ordem, wait_event,
on/handler, erro CDP, timeout, conexão fechada.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from core.cdp import CDPClient, CDPError


class FakeWS:
    """Websocket fake: fila de mensagens recebidas + fila de respostas a enviar."""

    def __init__(self):
        self.sent: list[dict] = []  # mensagens que o cliente enviou
        self._inbox: asyncio.Queue = asyncio.Queue()  # mensagens que o fake envia
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def recv(self) -> str:
        return await self._inbox.get()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.closed and self._inbox.empty():
            raise StopAsyncIteration
        return await self._inbox.get()

    # helpers de teste
    def push(self, msg: dict) -> None:
        self._inbox.put_nowait(json.dumps(msg))

    def respond(self, msg_id: int, result: dict | None = None, error: dict | None = None) -> None:
        msg = {"id": msg_id}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result or {}
        self.push(msg)

    def emit(self, method: str, params: dict | None = None) -> None:
        self.push({"method": method, "params": params or {}})


@pytest.fixture
def fake_ws() -> FakeWS:
    return FakeWS()


async def _make_client(fake_ws: FakeWS) -> CDPClient:
    client = CDPClient(fake_ws)
    await client.connect()
    return client


class TestSend:
    @pytest.mark.asyncio
    async def test_send_correlates_id_to_response(self, fake_ws):
        client = await _make_client(fake_ws)
        # Auto-responde a cada comando enviado, com resultado distinto por id.
        # O pump resolve cada future pelo id — mesmo que as respostas cheguem
        # em ordem diferente da dos comandos, cada send recebe o seu result.
        async def _auto_respond():
            while True:
                if len(fake_ws.sent) > 0:
                    last = fake_ws.sent[-1]
                    fake_ws.respond(last["id"], {"ok": f"resp-{last['id']}"})
                await asyncio.sleep(0.01)

        responder = asyncio.create_task(_auto_respond())
        r1 = await client.send("Runtime.evaluate", {"expression": "1"})
        r2 = await client.send("Runtime.evaluate", {"expression": "2"})
        responder.cancel()

        assert r1 == {"ok": "resp-1"}
        assert r2 == {"ok": "resp-2"}
        # payloads enviados com id incremental
        assert fake_ws.sent[0]["id"] == 1
        assert fake_ws.sent[1]["id"] == 2
        assert fake_ws.sent[0]["method"] == "Runtime.evaluate"
        assert fake_ws.sent[0]["params"] == {"expression": "1"}
        await client.close()

    @pytest.mark.asyncio
    async def test_send_without_params(self, fake_ws):
        client = await _make_client(fake_ws)
        fake_ws.respond(1, {})
        await client.send("Network.enable")
        assert fake_ws.sent[0]["method"] == "Network.enable"
        assert "params" not in fake_ws.sent[0]
        await client.close()

    @pytest.mark.asyncio
    async def test_send_error_raises_cdperror(self, fake_ws):
        client = await _make_client(fake_ws)
        fake_ws.respond(1, error={"code": -31998, "message": "BrowserContextNotLoaded"})
        with pytest.raises(CDPError) as exc:
            await client.send("Page.navigate", {"url": "x"})
        assert "BrowserContextNotLoaded" in str(exc.value)
        await client.close()

    @pytest.mark.asyncio
    async def test_send_timeout(self, fake_ws):
        client = await _make_client(fake_ws)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(client.send("Page.navigate", {"url": "x"}, timeout=0.05), 1)
        await client.close()

    @pytest.mark.asyncio
    async def test_send_after_close_raises(self, fake_ws):
        client = await _make_client(fake_ws)
        await client.close()
        with pytest.raises(CDPError):
            await client.send("Page.navigate", {"url": "x"})


class TestEvents:
    @pytest.mark.asyncio
    async def test_wait_event_returns_params(self, fake_ws):
        client = await _make_client(fake_ws)
        task = asyncio.create_task(client.wait_event("Page.frameNavigated", timeout=1))
        await asyncio.sleep(0)  # deixa o waiter registrar
        fake_ws.emit("Page.frameNavigated", {"frame": {"id": "FID-1"}})
        params = await task
        assert params == {"frame": {"id": "FID-1"}}
        await client.close()

    @pytest.mark.asyncio
    async def test_wait_event_timeout(self, fake_ws):
        client = await _make_client(fake_ws)
        with pytest.raises(asyncio.TimeoutError):
            await client.wait_event("Page.loadEventFired", timeout=0.05)
        await client.close()

    @pytest.mark.asyncio
    async def test_on_handler_called(self, fake_ws):
        client = await _make_client(fake_ws)
        received = []

        async def handler(params):
            received.append(params)

        client.on("Network.requestWillBeSent", handler)
        fake_ws.emit("Network.requestWillBeSent", {"requestId": "REQ-1"})
        await asyncio.sleep(0.05)
        assert received == [{"requestId": "REQ-1"}]
        await client.close()

    @pytest.mark.asyncio
    async def test_event_does_not_confuse_response_correlation(self, fake_ws):
        client = await _make_client(fake_ws)
        # Evento chega antes da resposta do mesmo comando
        fake_ws.emit("Page.frameNavigated", {"frame": {}})
        fake_ws.respond(1, {"ok": True})
        r = await client.send("Page.navigate", {"url": "x"})
        assert r == {"ok": True}
        await client.close()


class TestClose:
    @pytest.mark.asyncio
    async def test_close_fails_pending(self, fake_ws):
        client = await _make_client(fake_ws)
        task = asyncio.create_task(client.send("Page.navigate", {"url": "x"}, timeout=5))
        await asyncio.sleep(0)
        await client.close()
        with pytest.raises(CDPError):
            await task
