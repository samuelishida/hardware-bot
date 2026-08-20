"""MCP server do PreçoBot — Inc 9.

Servidor MCP (FastMCP, transport stdio) que expõe o MAS e o toolkit como tools.
É **fachada**: cada tool delega para o código existente (``run_agent_pipeline`` /
``toolkit.get_latest`` / ``toolkit.get_history`` / ``selector_repo.get_all_overrides``)
sem nova lógica de negócio.

Contrato de erro idêntico ao ``agent_api``: em vez de lançar, cada tool retorna
``{"success": false, "error": "..."}``.

Execução::

    python -m agents.mcp_server          # sobe em stdio

As funções tool são registradas explicitamente (``mcp.tool()(fn)``) para que o
nome de módulo continue sendo a função plain — assim os testes chamam as tools
diretamente, sem transport.
"""

from __future__ import annotations

import dataclasses
import functools
import logging

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("precobot")


def _handle_errors(label: str):
    """Envolve uma tool MCP: em vez de lançar, retorna ``{"success": false, "error": ...}``.

    Colapsa o try/except duplicado das 4 tools numa única fachada de erro.
    """

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                logger.warning(f"[mcp] {label} falhou: {e}")
                return {"success": False, "error": f"{label} falhou: {e}"}

        return wrapper

    return decorator


@_handle_errors("agent pipeline")
async def run_agent(product: str, target_price: float | None = None) -> dict:
    """Roda o pipeline MAS completo (scrape → validação → veredito de oferta).

    Retorna o mesmo JSON do comando ``agent`` (``AgentResult.to_dict()``).
    """
    from agents.orchestrator import run_agent_pipeline

    result = await run_agent_pipeline(product, target_price=target_price)
    return result.to_dict()


@_handle_errors("get_latest")
async def get_latest(product: str) -> dict | list[dict]:
    """Últimos preços em cache (DB), mais barato primeiro."""
    from toolkit import get_latest as toolkit_get_latest

    records = await toolkit_get_latest(product)
    return [dataclasses.asdict(r) for r in records]


@_handle_errors("get_history")
async def get_history(product: str, days: int = 7) -> dict | list[dict]:
    """Histórico de preços (DB) em todas as lojas, ordenado por tempo."""
    from toolkit import get_history as toolkit_get_history

    records = await toolkit_get_history(product, days=days)
    return [dataclasses.asdict(r) for r in records]


@_handle_errors("self_healing_status")
async def self_healing_status() -> dict | list[dict]:
    """Lista os overrides de seletor ativos (self-healing)."""
    from db.repositories.selector_repo import get_all_overrides

    return await get_all_overrides()


# Registro explícito: mantém o nome de módulo como função plain (testável sem transport).
mcp.tool()(run_agent)
mcp.tool()(get_latest)
mcp.tool()(get_history)
mcp.tool()(self_healing_status)


def main() -> None:
    """Sobe o servidor MCP em stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
