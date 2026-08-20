"""core/cdp.py — Cliente CDP mínimo sobre websockets (Inc 2).

Fala com o CDP server do Lightpanda (`lightpanda serve`). Correlaciona
``id``→resposta, despacha eventos por método e expõe ``send``/``wait_event``/``on``.

Descoberta do spike (Inc 1): o CDP do Lightpanda exige um setup obrigatório
(``Target.createBrowserContext`` → ``Target.createTarget`` → ``Target.attachToTarget``)
e **todos** os comandos de página devem incluir ``sessionId`` no payload. Esse setup
vive no facade ``core/browser.py`` (Inc 3); este cliente é agnóstico a isso — o
caller passa o ``sessionId`` nos params quando necessário.

Consumido por: ``core/browser.py`` (Inc 3). Sem dependência de rede nos testes
(websocket fake).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# Timeout padrão por comando CDP (s).
DEFAULT_TIMEOUT = 30.0


class CDPError(Exception):
    """Erro retornado pelo CDP (resposta com ``error``) ou de conexão."""


class CDPClient:
    """Cliente CDP async sobre um websocket.

    - ``send(method, params)`` envia um comando e aguarda a resposta correlacionada
      por ``id`` (timeout → ``asyncio.TimeoutError``).
    - ``wait_event(method, timeout)`` aguarda o próximo evento CDP do método.
    - ``on(method, handler)`` registra um handler assíncrono para eventos.
    """

    def __init__(self, ws: Any):
        self._ws = ws
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._handlers: dict[str, list[Callable[[dict], Awaitable[None]]]] = {}
        self._event_waiters: dict[str, list[asyncio.Future]] = {}
        self._pump_task: asyncio.Task | None = None
        self._closed = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Inicia o pump de mensagens (deve ser chamado após o websocket conectar)."""
        if self._pump_task is None:
            self._pump_task = asyncio.create_task(self._pump())

    async def close(self) -> None:
        """Fecha o cliente e cancela o pump."""
        self._closed = True
        if self._pump_task is not None:
            self._pump_task.cancel()
            try:
                await self._pump_task
            except (asyncio.CancelledError, Exception):
                pass
            self._pump_task = None
        # Falha pendentes
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(CDPError("conexão fechada"))
        self._pending.clear()

    # ------------------------------------------------------------------
    # Comandos
    # ------------------------------------------------------------------

    async def send(self, method: str, params: dict | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Envia um comando CDP e retorna o ``result`` (dict).

        Raises:
            CDPError: resposta com ``error`` ou conexão fechada.
            asyncio.TimeoutError: sem resposta dentro de ``timeout``.
        """
        if self._closed:
            raise CDPError("cliente CDP fechado")
        self._id += 1
        msg_id = self._id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        payload = {"id": msg_id, "method": method}
        if params:
            payload["params"] = params
        try:
            await self._ws.send(json.dumps(payload))
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise
        except Exception as e:
            self._pending.pop(msg_id, None)
            if isinstance(e, CDPError):
                raise
            raise CDPError(f"falha ao enviar {method}: {e}") from e

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------

    async def wait_event(self, method: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Aguarda o próximo evento CDP do ``method`` e retorna seus ``params``.

        Raises:
            asyncio.TimeoutError: evento não chegou dentro de ``timeout``.
        """
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._event_waiters.setdefault(method, []).append(fut)
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            waiters = self._event_waiters.get(method, [])
            if fut in waiters:
                waiters.remove(fut)

    def on(self, method: str, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Registra um handler assíncrono chamado para cada evento do ``method``."""
        self._handlers.setdefault(method, []).append(handler)

    # ------------------------------------------------------------------
    # Pump
    # ------------------------------------------------------------------

    async def _pump(self) -> None:
        """Lê mensagens do websocket: resolve pendentes e despacha eventos."""
        try:
            async for raw in self._ws:
                if self._closed:
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("CDP: mensagem não-JSON ignorada")
                    continue
                if "id" in msg:
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        if "error" in msg:
                            fut.set_exception(CDPError(msg["error"]))
                        else:
                            fut.set_result(msg.get("result", {}))
                else:
                    method = msg.get("method")
                    params = msg.get("params", {})
                    # waiters
                    for waiter in self._event_waiters.get(method, []):
                        if not waiter.done():
                            waiter.set_result(params)
                    # handlers
                    for handler in self._handlers.get(method, []):
                        try:
                            await handler(params)
                        except Exception as e:  # handler não deve derrubar o pump
                            logger.warning(f"CDP: handler de {method} falhou: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not self._closed:
                logger.warning(f"CDP: pump encerrado: {e}")
                # Falha pendentes
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(CDPError(f"conexão encerrada: {e}"))
                self._pending.clear()


__all__ = ["CDPClient", "CDPError", "DEFAULT_TIMEOUT"]
