# 🤖 PreçoBot — Monitor de Preços de Hardware BR

Bot de Discord + toolkit agentico para monitorar preços e disponibilidade de produtos de hardware nas principais lojas brasileiras. Agora também monitora **produtos usados** via OLX e Enjoei.

---

## Funcionalidades

- **Busca dinâmica** — busca qualquer produto em 6 lojas (novos e usados)
- **Monitoramento contínuo** — varreduras automáticas via cron
- **Alerta de queda de preço** — notifica quando o preço cai ≥ 5%
- **Alerta de restoque** — avisa quando o produto volta ao estoque
- **Histórico de preços** — log persistente em `HISTORY.md`
- **Multi-produto** — monitore vários produtos simultaneamente
- **Modo Agente** — via `agent_api.py` para integração com Hermes Agent

---

## Lojas monitoradas

| Loja | Tipo | Método |
|---|---|---|
| KaBuM! | Novo | Lightpanda (browser) |
| Pichau | Novo | Lightpanda + SSR parsing |
| Terabyte Shop | Novo | Lightpanda |
| Amazon BR | Novo | Lightpanda |
| **OLX** | **Usado** | **Lightpanda + __NEXT_DATA__** |
| **Enjoei** | **Usado** | **Lightpanda + SSR DOM** |

---

## Modo Agente (Hermes Skill)

O `agent_api.py` permite que o Hermes Agent (ou qualquer CLI) execute buscas:

```bash
cd /home/ubuntu/precosbot
python agent_api.py check "rx 7900 xtx"       # Live scrape + DB store
python agent_api.py latest "rx 7900 xtx"      # Cached prices
python agent_api.py history "rx 7900 xtx" 7    # 7-day history
python agent_api.py analysis "rx 7900 xtx" 30  # Stats
python agent_api.py best-deal "rx 7900 xtx"    # Cheapest available
python agent_api.py db-stats                   # DB overview
python agent_api.py list-tracked               # Tracked products
python agent_api.py agent "rx 7900 xtx" -- 8000   # Full MAS pipeline (validated + deal verdict)
python agent_api.py agent-traces 10            # Recent MAS runs
```

Results are JSON — machine parseable.

---

## Multi-Agent System (MAS)

Pipeline LangGraph em `agents/` que transforma o scrape linear em um sistema de
agentes especializados. Orquestração **determinística** com LLM (Ollama) apenas nos
pontos de decisão — se o LLM não responder a tempo, tudo degrada para o modo
determinístico (nunca veta uma aprovação nem aprova uma rejeição determinística).

```
START → scraper → analyst ─┬─(ok)──────────────→ deal → END
                           └─(re-scrape, ≤ N)──→ scraper   (loop de feedback)
```

| Agente | Papel |
|---|---|
| **Scraper** | Scrape live em todas as lojas (1 browser compartilhado) |
| **Analista/Validador** | Valida preço/disponibilidade contra o histórico; LLM opcional para casos ambíguos |
| **Caçador de Ofertas** | Veredito de oferta: desconto vs. média histórica + `target_price` opcional |

**Self-healing**: seletores quebrados geram override em `selector_overrides`
("override é otimização, nunca requisito" — qualquer falha → no-op com log).

**Observabilidade**: cada run grava 1 linha em `agent_runs`; `agent-traces` lista os
últimos (runs abortados aparecem como `incomplete`).

### Configuração (env vars)

| Var | Default | Descrição |
|---|---|---|
| `PRECOSBOT_AGENT_LLM` | `auto` | `auto` \| `on` (exige LLM) \| `off` (determinístico) |
| `PRECOSBOT_AGENT_MAX_ITERATIONS` | `2` | Cap de re-scrapes no loop de feedback |
| `PRECOSBOT_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Endpoint OpenAI-compatible (Ollama) |
| `PRECOSBOT_LLM_MODEL` | `qwen2.5:3b` | Modelo Ollama |
| `PRECOSBOT_LLM_API_KEY` | `ollama` | API key |
| `PRECOSBOT_LLM_TIMEOUT` | `60` | Timeout por chamada (s) |
| `PRECOSBOT_LLM_NUM_PREDICT` | `2048` | Máx. tokens por resposta |

Dependências extras: `langgraph`, `fastmcp`, `mcp` (já no `requirements.txt`).

### MCP server

`python -m agents.mcp_server` expõe o pipeline como servidor MCP (stdio) com 4 tools
— fachada fina sobre o mesmo código: `run_agent`, `get_latest`, `get_history`,
`self_healing_status`. Contrato de erro igual ao `agent_api`
(`{"success": false, "error": ...}`).

> **VM 1 GB RAM:** não rodar `agent` (hermes) e o MCP server em paralelo para o
> mesmo produto — 2 browsers simultâneos estouram RAM.

---

## Pré-requisitos

- Python 3.12+
- Lightpanda (binário headless, CDP server) — sem binário Windows; dev em Windows via WSL2
- SQLite (built-in)

---

## Instalação

```bash
# 1. Clone/copy project
cd /home/ubuntu/precosbot

# 2. Virtualenv
python3 -m venv venv
source venv/bin/activate

# 3. Dependencies
pip install -r requirements.txt

# 4. Lightpanda (binário)
curl -sL -o /usr/local/bin/lightpanda \
  https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux
chmod +x /usr/local/bin/lightpanda
```

---

## Configuração

Copy `.env.example` to `.env`:

```env
# Discord bot (optional — only for Discord mode)
DISCORD_TOKEN=cole_seu_token_aqui
DISCORD_GUILD_ID=123456789012345678
ALERT_CHANNEL_ID=123456789012345678

# Intervals
SCRAPE_INTERVAL_MINUTES=15
PRICE_DROP_THRESHOLD_PCT=5
```

---

## Como rodar

### Modo Agente (CLI)
```bash
source venv/bin/activate
python agent_api.py check "RTX 4060 Ti"
```

### Modo Discord (full bot)
```bash
source venv/bin/activate
python main.py
```

---

## Estrutura do projeto

```
precosbot/
├── agent_api.py                # CLI bridge for hermes-agent integration
├── main.py                     # Discord bot entry point (optional)
├── config.py                   # Env vars, store URLs, display names
├── requirements.txt
├── .env.example
├── HISTORY.md                  # Persistent scrape log (append-only)
│
├── agents/                     # Multi-Agent System (LangGraph + Ollama)
│   ├── orchestrator.py         # Graph: scraper → analyst → deal
│   ├── state.py                # AgentResult / ValidatedPrice / DealResult
│   ├── config.py               # MAS env knobs
│   ├── llm.py                  # Ollama client (httpx)
│   ├── self_healing.py         # Selector self-healing
│   ├── mcp_server.py           # MCP server (FastMCP, stdio)
│   └── nodes/                  # scraper_node / analyst_node / deal_node
│
├── core/
│   └── product_manager.py      # Product name normalization, URL generation
│
├── db/
│   ├── database.py             # SQLite async setup (aiosqlite)
│   ├── queries.py              # Backward compat layer
│   └── repositories/           # Repository pattern
│       ├── price_repo.py
│       ├── alert_repo.py
│       ├── tracking_repo.py
│       └── run_repo.py         # agent_runs (observabilidade MAS)
│
├── scrapers/
│   ├── __init__.py             # Scraper registry (BROWSER_SCRAPERS)
│   ├── base.py                 # BaseScraper + ScrapeResult + STEALTH_SCRIPT
│   ├── kabum.py                # KaBuM! scraper (Lightpanda)
│   ├── pichau.py               # Pichau scraper (Lightpanda + SSR)
│   ├── terabyte.py             # Terabyte scraper (Lightpanda)
│   ├── amazon.py               # Amazon BR scraper (Lightpanda)
│   ├── olx.py                  # OLX Brasil (Lightpanda + __NEXT_DATA__)
│   └── enjoei.py               # Enjoei (Lightpanda + SSR DOM)
│
├── utils/
│   ├── formatters.py           # Price formatting utilities
│   └── history_logger.py       # HISTORY.md writer
│
└── tests/
    ├── test_all.py             # Quick validation runner
    ├── test_product_manager.py # Unit tests
    ├── test_repositories.py    # DB repository tests (in-memory SQLite)
    ├── test_formatters.py      # Formatter tests
    ├── test_executor.py        # Executor tests (mocked)
    ├── test_olx.py             # OLX pure-function tests
    └── test_enjoei.py          # Enjoei pure-function tests
```

---

## `HISTORY.md` — Jornal de Scrapes

Append-only markdown log generated by `utils/history_logger.py`. Every `scrape_and_store()` call writes one line:

```markdown
| 2026-05-02 02:50:03 UTC | olx | rx 7900 xtx | R$ 4.400,00 | ✅ | https://mg.olx.com.br/... |
| 2026-05-02 02:50:03 UTC | kabum | rx 7900 xtx | — | ❌ | https://www.kabum.com.br/... |
```

This serves as a **git-less audit trail** — durable, human-readable, and machine-parseable.

---

## Como adicionar uma nova loja

**1.** Create `scrapers/novaloja.py` inheriting `BaseScraper`:

```python
from .base import BaseScraper, ScrapeResult

class NovaLojaScraper(BaseScraper):
    store_id = "novaloja"
    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term
    async def scrape(self) -> ScrapeResult:
        # ... Lightpanda (facade) or HTTP logic
        return ScrapeResult(self.store_id, price, available, label, url)
```

**2.** Register in `scrapers/__init__.py`:
```python
from scrapers.novaloja import NovaLojaScraper
BROWSER_SCRAPERS = [..., NovaLojaScraper]
```

**3.** Add to `config.py`:
```python
STORE_URL_TEMPLATES["novaloja"] = "https://novaloja.com.br/busca?q={query}"
STORE_DISPLAY_NAMES["novaloja"] = "Nova Loja"
STORE_COLORS["novaloja"] = 0xABCDEF
```

**4.** Write tests in `tests/test_novaloja.py`.

---

## Testes

```bash
# Quick validation (no pytest required)
python tests/test_all.py

# Unit tests (requires pytest)
python -m pytest tests/test_product_manager.py -v
python -m pytest tests/test_repositories.py -v
python -m pytest tests/test_formatters.py -v
python -m pytest tests/test_olx.py -v
python -m pytest tests/test_enjoei.py -v
```

---

## Dependências

| Pacote | Versão mínima | Uso |
|---|---|---|
| `discord.py` | 2.3.0 | Bot Discord (optional) |
| `websockets` | 12.0 | Cliente CDP (Lightpanda) |
| `aiosqlite` | 0.20.0 | SQLite async |
| `apscheduler` | 3.10.0 | Periodic scraping (Discord mode) |
| `httpx` | 0.27.0 | HTTP fallback |
| `python-dotenv` | 1.0.0 | `.env` loading |
| `pytest` | 8.0.0 | Unit tests |
| `pytest-asyncio` | 0.23.0 | Async test support |

---

## Licença

MIT
