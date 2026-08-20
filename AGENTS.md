# AGENTS.md — PreçoBot

Agentic scraping toolkit for Brazilian hardware stores (KaBuM, Pichau, Terabyte, Amazon BR).
Consumed by hermes-agent via subprocess bridge (`agent_api.py`). No Discord bot, no scheduler.

## Architecture

```
toolkit.py                  # Main async Python API (scrape, get_latest, get_history, ...)
agent_api.py                # CLI subprocess bridge for hermes-agent
config.py                   # Store config (URL templates, display names, colors)
.env                        # Optional env vars (PRICE_DROP_THRESHOLD_PCT)
agents/                     # Multi-Agent System (LangGraph + Ollama)
  orchestrator.py           # LangGraph graph: scraper → analyst → deal
  state.py                  # AgentResult / ValidatedPrice / DealResult dataclasses
  config.py                 # MAS env knobs (LLM mode, iterations, Ollama settings)
  llm.py                    # Ollama OpenAI-compatible client (httpx)
  self_healing.py           # Selector self-healing (override é otimização, nunca requisito)
  mcp_server.py             # MCP server (FastMCP, stdio): run_agent/get_latest/get_history/self_healing_status
  nodes/
    scraper_node.py         # Node: live scrape via executor
    analyst_node.py         # Node: valida preços (determinístico + LLM opcional)
    deal_node.py            # Node: veredito de oferta (determinístico + LLM opcional)
core/
  product_manager.py        # Product name normalization, search URL generation
  cdp.py                    # Cliente CDP mínimo (websocket) p/ Lightpanda
  browser.py                # Facade Page/ElementHandle/Context sobre CDP (Lightpanda)
  executor.py               # Lightpanda scraper execution engine (1-browser shared session)
db/
  database.py               # SQLite setup (aiosqlite), init_db, get_db context manager
  repositories/
    price_repo.py           # Price history CRUD
    alert_repo.py           # User price alert CRUD
    tracking_repo.py        # Tracked products CRUD
    run_repo.py             # agent_runs CRUD (observabilidade MAS)
scrapers/
  base.py                   # BaseScraper, ScrapeResult dataclass
  kabum.py                  # KaBuM! (Lightpanda)
  pichau.py                 # Pichau (Lightpanda)
  terabyte.py               # Terabyte Shop (Lightpanda)
  amazon.py                 # Amazon BR (Lightpanda)
utils/
  formatters.py             # format_price_brl, format_store_name, normalize_search_term
tests/
  test_all.py               # Quick validation runner
  test_product_manager.py   # ProductManager unit tests
  test_repositories.py      # Repository unit tests (in-memory SQLite)
  test_executor.py          # Executor unit tests (mocked Lightpanda facade)
  test_cdp.py               # CDP client unit tests (websocket fake)
  test_browser.py           # Facade unit tests (CDP fake)
  test_embeds.py            # Toolkit unit tests
  test_integration.py       # Integration tests (data flow)
```

## Toolkit API (toolkit.py)

```python
await scrape(product)                    # Live scrape, returns list[ScrapeResult]
await scrape_and_store(product)          # Live scrape + persist to DB
await get_latest(product)               # Latest cached prices from DB
await get_history(product, days=7)      # Price history, all stores, sorted by time
await best_deal(product, live=False)    # Cheapest available PriceRecord (live=True re-scrapes)
await compare(["RTX 4060", "RTX 4070"]) # dict[product, list[PriceRecord]]
await get_analysis(product, days=30)    # {per_store: {min/max/avg/n}, overall_min}
```

## agent_api.py commands

```
python agent_api.py check <product>                Live scrape + store (30-120s)
python agent_api.py latest <product>               Latest cached prices
python agent_api.py history <product> [days]       Price history (default 7 days)
python agent_api.py analysis <product> [days]      Per-store stats (default 30 days)
python agent_api.py best-deal <product>            Cheapest cached price
python agent_api.py compare <p1> | <p2> | ...     Multi-product comparison
python agent_api.py scrape-and-store <product>     Alias for check
python agent_api.py list-tracked                   List tracked products in DB
python agent_api.py db-stats                       DB row counts and size
python agent_api.py agent <product> [-- <target_price>]  Full MAS pipeline (30-180s)
python agent_api.py agent-traces [limit]           Recent MAS runs (default 10)
python agent_api.py relevance-status               Learned relevance exclusions
```

All commands output JSON to stdout. Exit 1 with `{"success": false, "error": "..."}` on error.

## Multi-Agent System (MAS)

Pipeline LangGraph em `agents/` — orquestração determinística com LLM (Ollama) apenas nos
pontos de decisão. O LLM **nunca** veta uma aprovação determinística nem aprova uma
rejeição determinística; se indisponível, tudo degrada para o modo determinístico.

```
START → scraper → analyst ─┬─(ok)──────────────→ deal → END
                           └─(re-scrape, ≤ N)──→ scraper   (loop de feedback)
```

- **Scraper** — scrape live via `core/executor.py` (todas as lojas, 1 browser).
- **Analista/Validador** — valida preço/disponibilidade contra histórico; LLM opcional
  para casos ambíguos (ex.: "R$ 2.999" vs "29990").
- **Caçador de Ofertas** — veredito de oferta: desconto vs. média histórica e
  `target_price` opcional; LLM opcional para o resumo.
- **Self-healing** — seletores quebrados geram override em `selector_overrides`;
  "override é otimização, nunca requisito" — qualquer falha → no-op com log.
- **Observabilidade** — cada `run_agent_pipeline` grava 1 linha em `agent_runs`
  (`run_repo.py`). Falha de gravação → log, **nunca** propaga. Run abortado
  (`finished_at` nulo) aparece como `status="incomplete"` em `agent-traces`.
- **Relevância** — `scrapers/relevance.py` (`is_relevant` + `ACCESSORY_TERMS`)
  rejeita acessórios na origem (todos os scrapers) e no Analista. Termos aprendidos
  vivem em `relevance_overrides` (`relevance_repo.py`); `relevance-status` lista.
  "Override é otimização, nunca requisito" — DB/LLM fora → no-op com log.

### Env vars (MAS)

| Var | Default | Descrição |
|-----|---------|-----------|
| `PRECOSBOT_AGENT_LLM` | `auto` | `auto` (LLM se responder a tempo) \| `on` (exige LLM) \| `off` (determinístico) |
| `PRECOSBOT_AGENT_MAX_ITERATIONS` | `2` | Cap de re-scrapes no loop de feedback (clamp [1,10]) |
| `PRECOSBOT_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | Endpoint OpenAI-compatible (Ollama) |
| `PRECOSBOT_LLM_MODEL` | `qwen2.5:3b` | Modelo Ollama |
| `PRECOSBOT_LLM_API_KEY` | `ollama` | API key (qualquer valor no Ollama) |
| `PRECOSBOT_LLM_TIMEOUT` | `60` | Timeout por chamada (s, clamp [5,300]) |
| `PRECOSBOT_LLM_NUM_PREDICT` | `2048` | Máx. tokens por resposta |

### Deploy (MAS)

```bash
# Dependências extras: langgraph, fastmcp, mcp (já no requirements.txt)
ssh -i $SSH_KEY $VM "cd $REMOTE && git pull && pip install -r requirements.txt"
# Arquivos novos do MAS: agents/, db/repositories/run_repo.py, agent_api.py
# Ollama precisa estar rodando na VM (ou PRECOSBOT_AGENT_LLM=off)
```

### MCP server (Inc 9)

`python -m agents.mcp_server` sobe um servidor MCP (FastMCP, transport stdio) com
4 tools — fachada fina, sem lógica nova:

| Tool | Delega para |
|------|-------------|
| `run_agent(product, target_price?)` | `agents.orchestrator.run_agent_pipeline` (mesmo JSON do comando `agent`) |
| `get_latest(product)` | `toolkit.get_latest` |
| `get_history(product, days=7)` | `toolkit.get_history` |
| `self_healing_status()` | `selector_repo.get_all_overrides` |

Contrato de erro igual ao `agent_api`: cada tool retorna `{"success": false, "error": ...}`
em vez de lançar.

> **VM 1 GB RAM:** `run_agent` via MCP roda o mesmo pipeline Lightpanda do comando
> `agent`. Não rodar `agent` (hermes) e MCP em paralelo para o mesmo produto —
> escrita no SQLite é serializada (segura), mas 2 browsers simultâneos estouram RAM.

## Key Patterns

- **Scrapers**: Subclass `BaseScraper`, implement `async scrape() -> ScrapeResult`. Always instantiate with kwargs: `cls(browser=b, search_term=term)`.
- **Executor**: `scrape_product(BROWSER_SCRAPERS, HTTP_SCRAPERS, search_term)` — runs all scrapers sequentially sharing one Lightpanda browser (facade CDP em `core/browser.py`). Per-scraper timeout: 90s.
- **Python 3.12**: OCI VM runs Ubuntu 24.04 + Python 3.12. Use `from __future__ import annotations` for `X | Y` unions.
- **SQLite**: `precobot.db` at project root. WAL mode. Tables: `price_history`, `user_alerts`, `tracked_products`, `scheduler_locks`, `selector_overrides`, `agent_runs`.

## OCI Deployment

```bash
SSH_KEY=~/.ssh/oci_yvy
VM=ubuntu@137.131.159.91
REMOTE=/home/ubuntu/precosbot

# Deploy full toolkit
ssh -i $SSH_KEY $VM "cd $REMOTE && git pull && pip install -r requirements.txt"

# Or deploy single file
scp -i $SSH_KEY toolkit.py $VM:$REMOTE/toolkit.py
scp -i $SSH_KEY agent_api.py $VM:$REMOTE/agent_api.py

# Restart hermes (the service that calls precosbot)
ssh -i $SSH_KEY $VM "sudo systemctl restart hermes"

# Logs
ssh -i $SSH_KEY $VM "journalctl -u hermes -f"
ssh -i $SSH_KEY $VM "journalctl -u hermes -n 100 --no-pager"
```

### Services on VM

| Service | File | Role |
|---------|------|------|
| `hermes.service` | `/etc/systemd/system/hermes.service` | hermes-agent Discord gateway |
| ~~`precosbot.service`~~ | deleted | replaced by hermes |

hermes.service:
```ini
[Unit]
Description=Hermes Agent Gateway
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu
EnvironmentFile=/home/ubuntu/.hermes/.env
ExecStart=/home/ubuntu/.hermes/hermes-agent/venv/bin/hermes gateway run --accept-hooks
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### hermes config (`~/.hermes/config.yaml`)

```yaml
model:
  base_url: http://localhost:11434/v1
  default: minimax-m2.5:cloud
  provider: auto
skills:
  config:
    precosbot:
      path: /home/ubuntu/precosbot
```

### hermes env (`~/.hermes/.env`)

```
OPENAI_API_KEY=ollama
DISCORD_BOT_TOKEN=<token>
DISCORD_HOME_CHANNEL=<channel_id>
GATEWAY_ALLOW_ALL_USERS=true
```

## hermes Tool Registration

Tool: `~/.hermes/hermes-agent/tools/precosbot.py` (or `E:\Code\hermes-agent\tools\precosbot.py`)
Skill: `~/.hermes/skills/shopping/precosbot/SKILL.md`
Core tools: `precosbot_check`, `precosbot_latest`, `precosbot_history`, `precosbot_list_tracked`, `precosbot_db_stats`, `precosbot_agent`

## Adding a New Store

1. Create `scrapers/novaloja.py` inheriting `BaseScraper`
2. Add to `config.py`: `STORE_URL_TEMPLATES`, `STORE_DISPLAY_NAMES`, `STORE_COLORS`
3. Register in `scrapers/__init__.py` (`BROWSER_SCRAPERS` or `HTTP_SCRAPERS`)
4. Deploy + restart hermes

## Local Dev

```bash
pip install -r requirements.txt
# Lightpanda (binário) — sem binário Windows; dev em Windows via WSL2
curl -sL -o /usr/local/bin/lightpanda \
  https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux
chmod +x /usr/local/bin/lightpanda
python tests/test_all.py
python agent_api.py db-stats
```

## OCI VM Notes

- 1 GB RAM micro instance. Lightpanda pico ~123 MB, hermes ~131 MB at rest.
- After memory pressure: OCI `RESET` to clear, then add 2 GB swap.
- OCI serial console needs RSA public key (ed25519 rejected).
- Python venv: `/home/ubuntu/precosbot/venv/bin/python`

## OCI API Key

```ini
tenancy_ocid=ocid1.tenancy.oc1..aaaaaaaa5vfmx4xoxmfv577ibav5fk3ablvy56yo4arls7lvyrtbvcsohjha
user_ocid=ocid1.user.oc1..aaaaaaaagx367raaxizktk2dzvwhirftnwhcpsm72gw5iblbwqwpwpwktl3a
fingerprint=04:73:54:2c:b2:2b:4d:77:b7:f3:d9:17:02:3f:43:44
region=sa-saopaulo-1
ssh_public_key_path=/c/Users/samue/.ssh/oci_yvy.pub
private_key_path=/c/Users/samue/.ssh/oci_yvy
```
