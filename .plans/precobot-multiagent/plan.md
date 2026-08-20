# PreçoBot Multi-Agente (MAS) — LangGraph + Ollama

## Context

O precosbot hoje é um pipeline linear: `hermes tool → agent_api.py (JSON CLI) → toolkit.py → executor.scrape_product (1 browser Playwright, sequencial, 90s/scraper) → 8 scrapers → SQLite`. Não há LLM nem código de agente no repo — o LLM vive no hermes-agent (repo separado).

Objetivo: transformar o precosbot em um **Sistema Multi-Agente** com um orquestrador (LangGraph) e agentes especialistas — Rastreador (scraping), Analista (validação/histórico), Caçador de Ofertas (gatilho de alerta + resumo) — mais **self-healing de seletores** (LLM lê HTML bruto quando o seletor falha) e um **MCP server** expondo as tools do MAS. O MAS é um módulo novo (`agents/`) dentro do precosbot; o hermes continua sendo o host LLM externo e chama o MAS via `agent_api.py`.

Restrições duras:
- VM OCI com **1 GB RAM** → scraping sequencial com 1 browser compartilhado (não relaxar); LLM local (Ollama) com modelo pequeno e chamadas sempre degradáveis.
- **SQLite WAL, single-process** → o grafo roda in-process (não agentes multi-processo).
- Python 3.12, `from __future__ import annotations`.
- Backwards compat: os 7 funções do `toolkit.py` e os comandos existentes do `agent_api.py` permanecem intactos; o MAS é aditivo.

## Architectural decisions

- **Decision: LangGraph para o grafo.** Rationale: controle explícito de estado e ciclos — necessário para o loop de feedback (Analista marca preço suspeito → re-scrape, com cap de iterações) e para o self-healing. Alternatives rejected: CrewAI (pessoas/tarefas, controle fraco de ciclos — confirmado pelo usuário que prefere LangGraph); grafo próprio em Python puro (zero deps, mas menos visível no portfólio e mais código de estado manual).
- **Decision: MAS in-process em `agents/`, chamado via `agent_api.py`.** Rationale: SQLite assume single-process; 1 GB RAM não suporta agentes multi-processo; mantém o contrato JSON/exit-code já consumido pelo hermes. Alternatives rejected: agentes como subprocessos (custo de memória, serialização); MAS dentro do hermes-agent (acopla a outro repo, sai do escopo do precosbot).
- **Decision: estilo híbrido — scraping/DB determinísticos, LLM só em pontos de decisão.** Rationale: confiabilidade e custo na VM; o LLM pode *adicionar* suspeita (Analista) ou *gerar* texto (resumo, self-healing), mas nunca *veta* o que a regra determinística aprovou nem *aprovar* o que a regra rejeitou. Alternatives rejected: agentes 100% LLM com tools (caro, lento, não-determinístico demais para validação de preço).
- **Decision: LLM via Ollama OpenAI-compatible (127.0.0.1:11434/v1), configurável por env, com fallback determinístico em todo ponto de uso.** Rationale: o hermes já usa esse endpoint na VM; offline; modelo pequeno. Alternatives rejected: API externa (custo + rede na VM); abstração multi-provedor (YAGNI — o cliente é OpenAI-compatible, trocar de provedor = trocar `base_url`).
- **Decision: self-healing valida o seletor candidato AO VIVO antes de persistir, com feedback de sucesso/falha e invalidação automática.** Rationale: persistir seletor não validado corromperia o scraping; a validação live (`page.query_selector` + `_parse_price` no texto) é barata e determinística. Alternatives rejected: auto-aplicar sem validação (risco alto); healing apenas em memória (sem ganho entre runs).
- **Decision: MCP server (SDK oficial `mcp`, FastMCP, stdio) como incremento final, expondo `run_agent`, `get_latest`, `get_history`, `self_healing_status`.** Rationale: padroniza como agentes externos consomem o MAS (destaque de portfólio pedido pelo usuário). Alternatives rejected: HTTP/SSE transport (stdio é o padrão para consumo local por hermes/Claude).
- **Decision: feature knob `PRECOSBOT_AGENT_LLM` = `auto` (default) | `on` | `off`.** Rationale: `auto` usa LLM se responder no timeout, senão segue determinístico; `off` força modo determinístico (rollback sem rede); `on` exige LLM (erro estruturado se indisponível). Alternatives rejected: flag booleana (não cobre o modo "exigir").

## Assumptions and answers from code

- **Entry points que o MAS envolve:** `toolkit.py:27-91` (7 funções async; `scrape_and_store` é o único caminho de escrita). Source: code @ toolkit.py:27,33,57,62,73,85,91.
- **Executor:** `scrape_product` em `core/executor.py:36` — 1 `async_playwright()`, 1 chromium headless, loop sequencial, `asyncio.wait_for(..., 90)` por scraper, falhas são logadas e **descartadas** (sem taxonomia de erro). Source: code @ core/executor.py:16,36.
- **Shapes de dados:** `ScrapeResult{store_id, price, available, stock_label, url}` @ scrapers/base.py:59; `PriceRecord` = `ScrapeResult` + `scraped_at, product_name, search_term` @ db/repositories/price_repo.py:21.
- **Schema SQLite:** `price_history(id, store_id, product_name, price, available, scraped_at, data JSON)`, `user_alerts`, `tracked_products` @ db/database.py:38-81. `scheduler_locks` é documentado mas **nunca criado** — não depender dele; tabelas novas entram aditivas em `init_db`.
- **Sem LLM/agent framework no repo** (grep `openai|langchain|langgraph|crewai|anthropic|ollama|litellm` → só docs). `httpx` já é dependency → cliente LLM sem nova dep de HTTP. Source: code @ requirements.txt.
- **Contrato hermes:** `hermes/tools/precosbot.py:56-88` (`_run_api`, subprocess + JSON + timeouts por comando: check=150s); 5 tools registradas; `hermes/toolsets.py:68-70` (`_HERMES_CORE_TOOLS`). Source: code.
- **Check command:** `python -m pytest tests/ -v` (README:213-224); sem CI, sem lint. `pytest.ini`: `asyncio_mode = auto`.
- **Patterns de teste a seguir:** mock de Playwright via `patch("core.executor.async_playwright")` + fake scrapers duck-typed (tests/test_executor.py:26-38); DB in-memory `aiosqlite.connect(":memory:")` + patch de `get_db` por módulo repo (tests/test_repositories.py:37-95); mock de LLM via `patch(..., new=AsyncMock(...))` (padrão de tests/test_embeds.py:22).
- **Anti-bot:** stealth em `scrapers/base.py:21-60` + `_new_page(retry=2)`; ML com cookies (`ml_cookies.json`) e login wall — store mais frágil, candidata natural a re-scrape pelo loop do Analista.
- **User-confirmed (question gate):** LangGraph; módulo `agents/` no precosbot; Ollama local configurável; estilo híbrido; manter hermes/Discord (Telegram+fila fora de escopo); self-healing **e** MCP entram neste plano.

## Risks accepted

- **Ollama em VM de 1 GB RAM** (modelo + hermes + Playwright): chamadas LLM podem ser lentas ou pressionar memória. Mitigação: modelo ≤3B Q4, `num_predict` sempre explícito (2048 default), timeout 60s por chamada, LLM degradável em todo ponto de uso, `PRECOSBOT_AGENT_LLM=off` como rollback. Accept; revisit se OOM — mover Ollama para endpoint remoto via `PRECOSBOT_LLM_BASE_URL`.
- **Falsa rejeição do LLM no Analista:** preço válido marcado suspeito. Mitigação: regra determinística tem precedência (LLM só adiciona suspeita, nunca remove); cap de 2 re-scrapes; suspeita por LLM com `confidence` baixo é logada mas não bloqueia. Accept.
- **Self-healing persistir seletor errado:** Mitigação: validação live obrigatória antes de persistir; contadores de sucesso/falha; `failure_count > success_count` → invalida (delete). Accept; revisit se overrides acumularem ruído (adicionar TTL).
- **Churn de API do LangGraph** (lib em evolução rápida): pinar versão em requirements; todo o uso do LangGraph isolado em `agents/orchestrator.py` (troca de lib = 1 arquivo). Accept.
- **Escrita concorrente no SQLite** (run_repo + price_repo no mesmo run): WAL + single-process + writes serializados já cobrem; não introduzir concorrência de escrita. Accept.
- **`check` legado e `agent` divergirem** (mesmo scraper, dois caminhos): o Inc 2 refatora o executor para `scrape_product_detailed` e `scrape_product` vira wrapper — um único caminho de scraping para os dois. Mitigação: tests do executor existentes devem passar sem mudança.

## Increment DAG

- Inc 1 — Foundation: cliente LLM + estado + config (S) — depends on: none — unblocks: 2, 3, 4
- Inc 2 — Agente Rastreador: node de scraping + taxonomia de erros (S) — depends on: 1 — unblocks: 5
- Inc 3 — Agente Analista: validação determinística + LLM (M) — depends on: 1 — unblocks: 5
- Inc 4 — Agente Caçador de Ofertas: gatilho + resumo (M) — depends on: 1 — unblocks: 5
- Inc 5 — Orquestrador: grafo LangGraph + loop de feedback (M) — depends on: 2, 3, 4 — unblocks: 6, 7, 8
- Inc 6 — Self-healing de seletores (L) — depends on: 5 — unblocks: 7
- Inc 7 — Integração: `agent_api.py agent` + tool hermes (S) — depends on: 5, 6 — unblocks: 9
- Inc 8 — Observabilidade: `agent_runs` + traces + docs (S) — depends on: 5 — unblocks: 9
- Inc 9 — MCP server (M) — depends on: 7, 8 — unblocks: demo de portfólio

Caminho crítico: 1 → 2 → 5 → 6 → 7 → 9. Paralelizável: 2/3/4 (após 1); 6/8 (após 5).

## Increments

### Inc 1 — Foundation: cliente LLM + estado + config (S)
**Depends on:** none
**Unblocks:** 2, 3, 4
**Done criteria:** `python -m pytest tests/test_llm_client.py tests/test_agent_state.py -v` passa; `get_llm_client()` responde a um chat JSON contra Ollama local (ou degrada com `LLMUnavailable` se o endpoint estiver fora).

#### Files to touch

##### agents/__init__.py
- What changes: novo pacote; exporta `AgentState`, `get_llm_client`, `LLMError`, `LLMUnavailable`.
- Integration points: todos os increments seguintes.

##### agents/state.py
- What changes: estado do grafo + payloads tipados.
- Function(s):
  ```python
  class AgentState(TypedDict, total=False):
      product: str
      search_term: str
      target_price: float | None
      raw_results: list[ScrapeResult]
      outcomes: list[StoreOutcome]          # Inc 2
      validated: list[ValidatedPrice]       # Inc 3
      suspicious: list[SuspiciousPrice]     # Inc 3
      analysis: dict                        # Inc 3
      deal: DealResult                      # Inc 4
      summary: str                          # Inc 4
      iteration: int
      errors: list[str]
      trace: list[dict]                     # {node, started_at, duration_ms, status}

  @dataclass
  class AgentResult:
      product: str
      status: str            # "ok" | "partial" | "error"
      results: list[ValidatedPrice]
      deal: DealResult | None
      summary: str | None
      trace: list[dict]
      duration_ms: int
  ```
- Data shapes: `StoreOutcome`/`ValidatedPrice`/`SuspiciousPrice`/`DealResult` ficam nos módulos dos increments que os criam (2/3/4); `state.py` importa via `TYPE_CHECKING` para evitar ciclo.
- Error paths: `AgentState` é `total=False` — nodes retornam partial updates (padrão LangGraph).

##### agents/llm.py
- What changes: cliente LLM async OpenAI-compatible sobre `httpx` (dep existente).
- Function(s):
  ```python
  class LLMError(Exception): ...
  class LLMUnavailable(LLMError): ...

  class LLMClient:
      def __init__(self, base_url: str | None = None, model: str | None = None,
                   api_key: str | None = None, timeout: float = 60.0,
                   num_predict: int = 2048) -> None: ...
      async def chat(self, system: str, user: str, *, json_mode: bool = False) -> str: ...
      async def chat_json(self, system: str, user: str, *, retries: int = 1) -> dict: ...

  def get_llm_client() -> LLMClient: ...   # singleton; lê env
  ```
- Data shapes: env — `PRECOSBOT_LLM_BASE_URL` (default `http://127.0.0.1:11434/v1`), `PRECOSBOT_LLM_MODEL` (default `qwen2.5:3b`), `PRECOSBOT_LLM_API_KEY` (default `ollama`), `PRECOSBOT_LLM_TIMEOUT` (default 60), `PRECOSBOT_LLM_NUM_PREDICT` (default 2048). `chat_json` pede `"response_format": {"type": "json_object"}` quando `json_mode` e faz `json.loads` com 1 retry em parse falho (reenviando o erro de parse no prompt).
- Integration points: todos os nodes (3, 4, 6) via `get_llm_client()`.
- Error paths: connection error/timeout/HTTP ≥500 → `LLMUnavailable`; resposta com `content` vazio e `thinking` longo (modelo thinking) → retry com `num_predict * 2` uma vez, senão `LLMUnavailable`; JSON inválido após retries → `LLMError`. **Regra Ollama:** sempre enviar `num_predict` em `options` (previne resposta vazia e runaway).

##### agents/config.py
- What changes: knobs do MAS.
- Function(s):
  ```python
  def agent_llm_mode() -> str        # PRECOSBOT_AGENT_LLM: "auto"|"on"|"off", default "auto"
  def agent_max_iterations() -> int  # PRECOSBOT_AGENT_MAX_ITERATIONS, default 2
  ```
- Error paths: valor inválido → log + default.

##### requirements.txt
- What changes: adiciona `langgraph>=0.2.0` (pinar patch após instalar na VM).

##### tests/test_llm_client.py, tests/test_agent_state.py
- What changes: novos. Mock `httpx.AsyncClient` (padrão `patch(..., new=AsyncMock)`); casos: chat ok, chat_json ok, JSON inválido → retry → `LLMError`, timeout → `LLMUnavailable`, content vazio + thinking → retry com num_predict maior; `AgentState`/`AgentResult` construction.

#### Edge cases
- Ollama fora do ar no primeiro deploy (VM): `auto` degrada silenciosamente com 1 log warning — o pipeline não pode quebrar por causa do LLM.
- Modelo thinking (ex.: minimax) com `num_predict` pequeno → content vazio: coberto pelo retry com budget dobrado.

#### Verification
- Run: `python -m pytest tests/test_llm_client.py tests/test_agent_state.py -v`
- Tests to add/update: os 2 novos acima.
- Done: todos verdes + `python -c "from agents.llm import get_llm_client"` sem erro de import.

### Inc 2 — Agente Rastreador: node de scraping + taxonomia de erros (S)
**Depends on:** 1
**Unblocks:** 5
**Done criteria:** `python -m pytest tests/test_scraper_node.py tests/test_executor.py -v` passa (executor legado intacto); `scraper_node` retorna `outcomes` com `kind` correto para sucesso, timeout e antibot (mocks).

#### Files to touch

##### core/executor.py
- What changes: extrai o loop para `scrape_product_detailed`; `scrape_product` vira wrapper (backwards compat).
- Function(s):
  ```python
  async def scrape_product_detailed(browser_scraper_classes, http_scraper_classes,
                                    search_term: str) -> list[StoreOutcome]: ...
  async def scrape_product(browser_scraper_classes, http_scraper_classes,
                           search_term: str) -> list[ScrapeResult]:
      # wrapper: [o.result for o in await scrape_product_detailed(...) if o.kind is OK and o.result]
  ```
- Data shapes: `StoreOutcome{store_id: str, result: ScrapeResult | None, kind: ScrapeErrorKind, detail: str}` (definido em `agents/errors.py`).
- Integration points: `toolkit.scrape`/`scrape_and_store` (sem mudança de comportamento); `scraper_node` (novo).
- Error paths: `TimeoutError` → `kind=TIMEOUT`; `stock_label` contendo "Cloudflare"/"captcha" (case-insensitive) → `ANTI_BOT`; `result.price is None and not available` → `NOT_FOUND`; outra `Exception` → `UNKNOWN` com `detail=str(exc)`. Mantém 1 browser, sequencial, 90s/scraper.

##### agents/errors.py
- What changes: taxonomia de erros (preenche o gap "falhas são logadas e descartadas").
- Function(s):
  ```python
  class ScrapeErrorKind(str, Enum):
      OK = "ok"; TIMEOUT = "timeout"; ANTI_BOT = "antibot"
      NOT_FOUND = "not_found"; PARSE_ERROR = "parse_error"; UNKNOWN = "unknown"

  @dataclass
  class StoreOutcome:
      store_id: str
      result: ScrapeResult | None
      kind: ScrapeErrorKind
      detail: str = ""
  ```

##### agents/nodes/__init__.py
- What changes: pacote de nodes; exporta `scraper_node`.

##### agents/nodes/scraper_node.py
- What changes: node do Agente Rastreador.
- Function(s):
  ```python
  async def scraper_node(state: AgentState) -> dict:
      # 1. scrape_product_detailed(BROWSER_SCRAPERS, HTTP_SCRAPERS, state["search_term"])
      # 2. append {node: "scraper", iteration, outcomes summary} em trace
      # 3. return {"raw_results": [...], "outcomes": [...], "iteration": state["iteration"] + 1, "trace": [...]}
  ```
- Data shapes: input `AgentState{product, search_term, iteration}`; output partial update acima.
- Integration points: `core.executor.scrape_product_detailed`; grafo (Inc 5).
- Error paths: exceção do executor inteiro (browser crash) → `errors.append`, `outcomes=[]`, node não lança (grafo decide).

##### tests/test_scraper_node.py
- What changes: novo. Reusa o padrão `patch("core.executor.async_playwright")` + fake scrapers duck-typed de tests/test_executor.py:26-38; casos: todos OK, 1 timeout, 1 antibot (stock_label="Cloudflare"), browser crash → `outcomes=[]` + `errors`.

#### Edge cases
- `scrape_product` legado: os tests existentes de executor/toolkit devem passar **sem alteração** (wrapper idêntico em comportamento).
- Store com `price=None` mas `available=True` (raro): `kind=PARSE_ERROR`, não `NOT_FOUND`.

#### Verification
- Run: `python -m pytest tests/test_scraper_node.py tests/test_executor.py tests/test_embeds.py -v`
- Tests to add/update: `test_scraper_node.py` (novo).
- Done: verdes, incluindo os tests legados.

### Inc 3 — Agente Analista: validação determinística + LLM (M)
**Depends on:** 1
**Unblocks:** 5
**Done criteria:** `python -m pytest tests/test_analyst_node.py -v` passa; com DB in-memory populado, preço 100× abaixo da média histórica é marcado `suspicious` (determinístico) e o LLM mockado só consegue *adicionar* suspeita, nunca remover.

#### Files to touch

##### agents/nodes/analyst_node.py
- What changes: node do Agente Analista.
- Function(s):
  ```python
  @dataclass
  class ValidatedPrice:
      store_id: str; price: float; available: bool
      url: str | None; stock_label: str | None
      reason: str; history_avg: float | None; history_min: float | None

  @dataclass
  class SuspiciousPrice:
      store_id: str; price: float
      reason: str; source: str   # "deterministic" | "llm"

  async def analyst_node(state: AgentState) -> dict: ...
  ```
- Data shapes: para cada `StoreOutcome` com `kind=OK` e `price is not None`: busca `get_price_history(store_id, product, days=30)`; regras determinísticas (ordem de avaliação):
  1. `price <= 0` → SUSPICIOUS ("preço não positivo")
  2. `n >= 3 and price < 0.05 * avg` → SUSPICIOUS ("erro de leitura provável: X% da média")
  3. `n >= 3 and price > 10 * avg` → SUSPICIOUS ("acima do plausível")
  4. senão → VALIDATED (com `history_avg`/`history_min`; sem histórico → `reason="sem histórico de baseline"`)
  Passo LLM (somente `agent_llm_mode() != "off"` e LLM disponível): envia JSON compacto `{store, price, avg, min, n, stock_label}` por store validada → LLM responde `{valid: bool, reason: str, confidence: float}`; se `valid=false` → move para `suspicious` com `source="llm"` (e `confidence < 0.6` → loga mas mantém validada). **LLM nunca reverte rejeição determinística nem aprova suspeita determinística.**
  Output: `{"validated": [...], "suspicious": [...], "analysis": {per_store: {avg, min, n}, overall_min}, "trace": [...]}`.
- Integration points: `db.repositories.price_repo.get_price_history`; `agents.llm.get_llm_client`; grafo (Inc 5).
- Error paths: `LLMUnavailable` → pula passo LLM (log); erro de query DB → store vira `suspicious` com `reason="erro de consulta"` (não derruba o run).

##### tests/test_analyst_node.py
- What changes: novo. Fixture DB in-memory (padrão tests/test_repositories.py:37-95) + `patch("agents.llm.get_llm_client")` com `AsyncMock`; casos: preço normal validado, preço 1% da média rejeitado, preço 20× a média rejeitado, sem histórico → validado com baseline nulo, LLM rejeita → `source="llm"`, LLM fora → degrada, LLM tenta "aprovary" rejeição determinística → ignorado.

#### Edge cases
- `n < 3` (pouco histórico): só regra 1 aplica (evita falso positivo com baseline fraco).
- Store com `available=False`: não entra em validação (passa adiante em `raw_results` para o resumo mostrar "indisponível").

#### Verification
- Run: `python -m pytest tests/test_analyst_node.py -v`
- Tests to add/update: `test_analyst_node.py` (novo).
- Done: verdes.

### Inc 4 — Agente Caçador de Ofertas: gatilho + resumo (M)
**Depends on:** 1
**Unblocks:** 5
**Done criteria:** `python -m pytest tests/test_deal_node.py -v` passa; com `target_price` e preço abaixo dela, `deal.is_deal=true` com `savings_pct` correto e resumo gerado (LLM mockado ou template fallback).

#### Files to touch

##### agents/nodes/deal_node.py
- What changes: node do Agente Caçador.
- Function(s):
  ```python
  @dataclass
  class DealResult:
      is_deal: bool
      best_store_id: str | None
      best_price: float | None
      target_price: float | None
      discount_pct: float | None   # vs média histórica
      savings_pct: float | None    # vs target_price
      summary: str

  async def deal_node(state: AgentState) -> dict: ...
  ```
- Data shapes: gatilho (OR):
  1. `target_price` fornecida e `best_price <= target_price` → deal;
  2. sem target: `best_price <= history_avg * (1 - PRICE_DROP_THRESHOLD_PCT/100)` (config.py:14, default 5) → deal.
  `best_price` = mínimo entre `validated` com `available=True`. Resumo: LLM gera texto persuasivo pt-BR com os números (economia em R$ e %, store, URL); fallback determinístico (template) se LLM indisponível/`off`. Se nenhum preço validado → `is_deal=false`, `summary` explica (ex.: "nenhum preço confiável nesta rodada; stores com erro: ...").
- Integration points: `config.PRICE_DROP_THRESHOLD_PCT`; `agents.llm`; grafo (Inc 5).
- Error paths: `validated` vazio → `DealResult(is_deal=False, ...)` sem exceção; LLM falha → template.

##### tests/test_deal_node.py
- What changes: novo. Casos: abaixo do target, abaixo do threshold sem target, acima de ambos, `validated` vazio, LLM fora → template, `discount_pct`/`savings_pct` aritmética.

#### Edge cases
- `history_avg=None` (sem histórico) e sem target: `is_deal=false` com `summary` indicando falta de baseline (não inventar desconto).
- Várias stores com o mesmo melhor preço: `best_store_id` = primeira em ordem de `STORE_DISPLAY_NAMES` (determinístico).

#### Verification
- Run: `python -m pytest tests/test_deal_node.py -v`
- Tests to add/update: `test_deal_node.py` (novo).
- Done: verdes.

### Inc 5 — Orquestrador: grafo LangGraph + loop de feedback (M)
**Depends on:** 2, 3, 4
**Unblocks:** 6, 7, 8
**Done criteria:** `python -m pytest tests/test_orchestrator.py -v` passa; com nodes fake, o grafo executa scraper→analista→deal, e com preço suspeito reexecuta o scraper até o cap de iterações antes de seguir para deal.

#### Files to touch

##### agents/orchestrator.py
- What changes: grafo LangGraph + API pública do MAS.
- Function(s):
  ```python
  def build_graph() -> CompiledGraph: ...
  async def run_agent_pipeline(product: str,
                               target_price: float | None = None) -> AgentResult: ...
  ```
- Data shapes: grafo:
  ```
  START → scraper → analyst → [conditional]
      suspicious não vazio and iteration < agent_max_iterations() → scraper
      senão → deal → END
  ```
  `run_agent_pipeline`: `parse_product_name` (core/product_manager) → estado inicial `{product, search_term, target_price, iteration: 0, ...}` → `graph.ainvoke` → monta `AgentResult` (`status`: "ok" se ≥1 validado e sem errors; "partial" se ≥1 validado com errors ou só LLM-degraded; "error" se zero validados).
- Integration points: `scraper_node`, `analyst_node`, `deal_node`; `core.product_manager.parse_product_name`; (Inc 8) run_repo.
- Error paths: exceção em qualquer node → capturada, `errors.append`, `status="error"`, `AgentResult` ainda retornado (nunca lança para o caller); timeout por node via `asyncio.wait_for` (scraper 150s, demais 60s) → tratado como erro do node.
- Nota: todo o uso da API LangGraph fica **apenas** neste arquivo (decisão de churn).

##### tests/test_orchestrator.py
- What changes: novo. Monkeypatch os 3 nodes com fakes (sem Playwright, sem LLM, sem DB): fluxo happy path; loop de feedback (1ª iteração suspeito → 2ª ok → deal); cap de iterações (sempre suspeito → para em `agent_max_iterations()`); node lança → `status="error"`; `AgentResult.duration_ms` presente.

#### Edge cases
- `iteration` começa em 0 e incrementa no scraper_node — o conditional lê o valor **pós-update** (cuidado com o estado do LangGraph: a condição roda sobre o estado atualizado).
- Re-scrape reexecuta **todas** as stores (não só as suspeitas) — mais simples e o browser já é sequencial; custo aceito (mitigação futura: filtrar stores, fora de escopo).

#### Verification
- Run: `python -m pytest tests/test_orchestrator.py -v`
- Tests to add/update: `test_orchestrator.py` (novo).
- Done: verdes.

### Inc 6 — Self-healing de seletores (L)
**Depends on:** 5
**Unblocks:** 7
**Done criteria:** `python -m pytest tests/test_self_healing.py tests/test_selector_repo.py -v` passa; com um seletor "quebrado" (mock) e LLM mockado propondo um seletor válido, o override é validado ao vivo, persistido e usado no scrape seguinte; override com mais falhas que sucessos é invalidado.

#### Files to touch

##### db/database.py
- What changes: tabela aditiva em `init_db`.
- Data shapes:
  ```sql
  CREATE TABLE IF NOT EXISTS selector_overrides (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      store_id TEXT NOT NULL,
      element TEXT NOT NULL,            -- 'price' | 'title' | 'stock'
      selector TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'self_healing',
      validated_at TEXT NOT NULL,
      success_count INTEGER NOT NULL DEFAULT 0,
      failure_count INTEGER NOT NULL DEFAULT 0,
      UNIQUE(store_id, element)
  );
  ```

##### db/repositories/selector_repo.py
- What changes: novo repo.
- Function(s):
  ```python
  async def get_override(store_id: str, element: str) -> dict | None: ...
  async def upsert_override(store_id: str, element: str, selector: str) -> None: ...
  async def record_outcome(store_id: str, element: str, success: bool) -> None: ...
  async def invalidate_if_unreliable(store_id: str, element: str) -> None:
      # DELETE onde failure_count > success_count
  async def get_all_overrides() -> list[dict]: ...
  ```
- Integration points: `BaseScraper` (via `_resolve_selector`); self-healing; (Inc 7) `self_healing_status`.
- Error paths: DB error → `None`/no-op com log (override é otimização, nunca requisito).

##### scrapers/base.py
- What changes: hook de seletor resolvido (comportamento default inalterado sem override).
- Function(s):
  ```python
  class BaseScraper:
      SELECTORS: dict[str, str] = {}     # subclasses declaram {'price': "...", ...}
      async def _resolve_selector(self, element: str) -> str:
          # 1. SELECTORS[element] (default)
          # 2. override do selector_repo (cache em memória por instância)
          #    → se usar override e o scrape falhar, caller chama record_outcome(False)
  ```
- Integration points: subclasses de scraper passam a declarar `SELECTORS` para o elemento de preço (migrar o seletor hardcoded de cada `scrape()` para `SELECTORS` — mudança mecânica, 1 store por commit se necessário); `record_outcome` chamado no sucesso/falha do scrape.
- Error paths: `SELECTORS` sem a chave → comportamento legado exato (sem override, sem log de erro).

##### agents/self_healing.py
- What changes: lógica de healing.
- Function(s):
  ```python
  async def attempt_self_heal(store_id: str, element: str, page) -> str | None:
      # 1. html = await page.content() (truncar ~50KB no prompt, manter contexto do preço)
      # 2. LLM chat_json: system="Você propõe um seletor CSS..." user={html, element, store}
      #    → {"selector": str, "confidence": float, "reasoning": str}
      # 3. validação AO VIVO: el = await page.query_selector(selector)
      #    → el and _parse_price(await el.inner_text()) is not None (para element='price')
      # 4. válido → upsert_override + return selector; inválido/LLM falha → None
  ```
- Data shapes: prompt de entrada `{store_id, element, html_snippet, expected: "preço BRL"}`; saída JSON acima.
- Integration points: `scraper_node`/scrapers (chamado quando `kind in {PARSE_ERROR, NOT_FOUND}` e a página ainda está aberta — requer que o scraper exponha o ponto de falha com a page; ver Edge cases); `selector_repo`; `agents.llm`.
- Error paths: LLM indisponível → `None` (sem healing); seletor inválido → `None` + log; `page` já fechada → `None`.

##### agents/nodes/scraper_node.py
- What changes: integra healing — quando um outcome é `PARSE_ERROR`/`NOT_FOUND` e o scraper expõe a page no momento da falha, chama `attempt_self_heal` e, se retornar seletor, re-tenta a extração uma vez com o override.
- Error paths: healing falha → outcome original preservado.

##### tests/test_self_healing.py, tests/test_selector_repo.py
- What changes: novos. `test_self_healing`: fake `page` (AsyncMock com `content()`, `query_selector()`, `inner_text()`), LLM mockado; casos: seletor válido → persistido; inválido → `None`; LLM fora → `None`; HTML truncado. `test_selector_repo`: DB in-memory; upsert/get/record_outcome/invalidation.

#### Edge cases
- **Ponto de falha com page aberta:** hoje o scraper fecha a page no `finally`. Especificação: cada scraper que adotar `SELECTORS` deve, no caminho de falha de extração, chamar `self._on_extract_failure(page)` (hook no `BaseScraper`, no-op por default) — o hook é onde o healing é acionado. Sem o hook, healing não roda para aquela store (degradação limpa).
- Healing em store com antibot (`kind=ANTI_BOT`): **não** aciona healing (o problema não é o seletor).
- Override para `element='price'` validado por `_parse_price` — para `title`/`stock` a validação é só `el is not None and inner_text().strip()`.

#### Verification
- Run: `python -m pytest tests/test_self_healing.py tests/test_selector_repo.py tests/test_scrapers.py -v`
- Tests to add/update: 2 novos + tests de scrapers existentes (migração `SELECTORS` não quebra nada).
- Done: verdes.

### Inc 7 — Integração: `agent_api.py agent` + tool hermes (S)
**Depends on:** 5, 6
**Unblocks:** 9
**Done criteria:** `python agent_api.py agent "RTX 4060"` imprime JSON `{"success": true, ...}` com `results`, `deal`, `summary`, `trace`; tool `precosbot_agent` registrada no hermes e listada em `toolsets`.

#### Files to touch

##### agent_api.py
- What changes: novo comando `agent <product> [target_price]`.
- Function(s):
  ```python
  # em main(): "agent" → run_agent_pipeline(product, target_price)
  # saída: {"success": true, "product", "status", "results": [...], "deal": {...},
  #         "summary": str, "trace": [...], "duration_ms": int}
  # erro: _err(...) (exit 1) — mesmo contrato dos demais comandos
  ```
- Data shapes: `target_price` opcional (float, parse com erro amigável).
- Integration points: `agents.orchestrator.run_agent_pipeline`; `init_db()` (já chamado em `main`).
- Error paths: `AgentResult.status="error"` → ainda `success: true` com `status` (o pipeline rodou; o resultado é negativo) — exceto exceção não tratada → `_err`.

##### hermes/tools/precosbot.py
- What changes: registra `precosbot_agent` → `agent <product> [target]`, timeout 180s.
- Integration points: `_run_api` (padrão existente, hermes/tools/precosbot.py:56-88).

##### hermes/toolsets.py
- What changes: `precosbot_agent` em `_HERMES_CORE_TOOLS` (hermes/toolsets.py:68-70).

##### hermes/skills/shopping/precosbot/SKILL.md
- What changes: documenta `precosbot_agent` (pipeline completo com validação + resumo) vs `precosbot_check` (scrape bruto); quando usar cada um.

##### tests/test_agent_api.py
- What changes: novo. `patch("agent_api.run_agent_pipeline")` (import lazy dentro do handler); casos: sucesso, target_price parse, exceção → exit 1 + JSON de erro.

#### Edge cases
- `agent` com produto sem histórico e LLM fora: deve retornar `status="ok"`/`"partial"` com resumo de template — nunca crash.
- Timeout do hermes (180s) menor que o pior caso do pipeline (scrape 120s + LLM): o `duration_ms` no JSON permite ao hermes avisar o usuário.

#### Verification
- Run: `python -m pytest tests/test_agent_api.py -v` + `python agent_api.py agent "RTX 4060"` (VM, smoke manual).
- Tests to add/update: `test_agent_api.py` (novo).
- Done: verdes + smoke JSON válido.

### Inc 8 — Observabilidade: `agent_runs` + traces + docs (S)
**Depends on:** 5
**Unblocks:** 9
**Done criteria:** cada `run_agent_pipeline` grava 1 linha em `agent_runs`; `python agent_api.py agent-traces 10` lista os últimos runs; `db-stats` inclui contagem de runs.

#### Files to touch

##### db/database.py
- What changes: tabela aditiva.
- Data shapes:
  ```sql
  CREATE TABLE IF NOT EXISTS agent_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      product TEXT NOT NULL,
      started_at TEXT NOT NULL,
      finished_at TEXT,
      status TEXT NOT NULL,          -- ok | partial | error
      nodes_json TEXT,               -- trace serializado
      error TEXT,
      duration_ms INTEGER
  );
  CREATE INDEX IF NOT EXISTS idx_agent_runs_started ON agent_runs(started_at DESC);
  ```

##### db/repositories/run_repo.py
- What changes: novo repo.
- Function(s):
  ```python
  async def start_run(run_id: str, product: str) -> None: ...
  async def finish_run(run_id: str, status: str, nodes: list[dict],
                       error: str | None, duration_ms: int) -> None: ...
  async def get_recent_runs(limit: int = 10) -> list[dict]: ...
  ```
- Error paths: falha de gravação → log, nunca propaga (observabilidade não derruba o run).

##### agents/orchestrator.py
- What changes: `run_agent_pipeline` chama `start_run`/`finish_run` (run_id = uuid4 hex curto) em try/finally.

##### agent_api.py
- What changes: estende `db-stats` (contagem de `agent_runs`) + novo comando `agent-traces [limit]` → `{"success": true, "runs": [...]}`.

##### AGENTS.md, README.md, CHANGELOG.md
- What changes: seção "Multi-Agent System" (arquitetura, env vars novas, comandos novos, fluxo de deploy); CHANGELOG com entrada do feature.
- Data shapes: env vars documentadas: `PRECOSBOT_LLM_BASE_URL`, `PRECOSBOT_LLM_MODEL`, `PRECOSBOT_LLM_API_KEY`, `PRECOSBOT_LLM_TIMEOUT`, `PRECOSBOT_LLM_NUM_PREDICT`, `PRECOSBOT_AGENT_LLM`, `PRECOSBOT_AGENT_MAX_ITERATIONS`.

##### tests/test_run_repo.py
- What changes: novo. DB in-memory; start/finish/get_recent; `finish_run` com erro não lança.

#### Edge cases
- Run abortado (Ctrl-C / timeout do hermes): `finished_at` nulo — `agent-traces` mostra como "incomplete" (não limpar automaticamente; limpeza futura via `purge_old_history`-like, fora de escopo).

#### Verification
- Run: `python -m pytest tests/test_run_repo.py -v` + `python agent_api.py agent-traces 5` (smoke).
- Tests to add/update: `test_run_repo.py` (novo).
- Done: verdes + docs atualizados.

### Inc 9 — MCP server (M)
**Depends on:** 7, 8
**Unblocks:** demo de portfólio
**Done criteria:** `python -m agents.mcp_server` sobe em stdio; um cliente MCP (test) chama `run_agent` e recebe o mesmo JSON do comando `agent`; `self_healing_status` lista overrides.

#### Files to touch

##### agents/mcp_server.py
- What changes: servidor MCP (FastMCP, SDK oficial `mcp`, transport stdio).
- Function(s):
  ```python
  mcp = FastMCP("precobot")

  @mcp.tool()
  async def run_agent(product: str, target_price: float | None = None) -> dict: ...
  @mcp.tool()
  async def get_latest(product: str) -> list[dict]: ...
  @mcp.tool()
  async def get_history(product: str, days: int = 7) -> list[dict]: ...
  @mcp.tool()
  async def self_healing_status() -> list[dict]: ...

  def main(): mcp.run()   # stdio
  ```
- Data shapes: tools delegam para `run_agent_pipeline` / `toolkit.get_latest` / `toolkit.get_history` / `selector_repo.get_all_overrides` — **sem nova lógica** (o MCP é fachada).
- Integration points: `agents.orchestrator`, `toolkit`, `db.repositories.selector_repo`.
- Error paths: cada tool retorna `{"success": false, "error": ...}` em vez de lançar (contrato igual ao `agent_api`).

##### requirements.txt
- What changes: adiciona `mcp>=1.0.0`.

##### tests/test_mcp_server.py
- What changes: novo. Chama as funções tool diretamente (sem transport) com mocks: `run_agent` delega, `self_healing_status` lista, erro → dict de erro.

#### Edge cases
- `run_agent` via MCP em VM de 1 GB: mesmo pipeline do comando `agent` — documentar no SKILL.md que não rodar `agent` (hermes) e MCP em paralelo para o mesmo produto (escrita serializada no SQLite já protege, mas RAM não).

#### Verification
- Run: `python -m pytest tests/test_mcp_server.py -v` + smoke: cliente MCP de teste (ex.: `mcp` inspector) conectando via stdio.
- Tests to add/update: `test_mcp_server.py` (novo).
- Done: verdes + smoke de conexão.

## Cross-cutting verification

- **Após Inc 5 (antes de expor):** `python -m pytest tests/ -v` completo — o MAS interno não pode regredir nada legado.
- **Após Inc 7 (VM):** `python agent_api.py agent "RTX 4060"` → JSON com `results` validados, `deal`, `summary` em pt-BR, `trace` com 3+ nodes; depois, via Discord/hermes, pedir "use o agente para verificar o preço do RTX 4060" e confirmar que a resposta vem do `precosbot_agent`.
- **Após Inc 6 (VM):** forçar falha de seletor (comentar o seletor de preço de 1 store em dev) → rodar `agent` → confirmar que `selector_overrides` ganhou linha e o próximo run usa o override; depois restaurar e confirmar `record_outcome`/invalidation.
- **Após Inc 8:** `agent-traces 10` mostra os runs dos testes anteriores com `status` e `duration_ms` plausíveis (scrape 30-120s).
- **Após Inc 9:** conectar o MCP server a um cliente (hermes ou Claude Desktop config) e rodar `run_agent("RTX 4060")` de fora do processo.
- **Rollback em qualquer ponto:** `PRECOSBOT_AGENT_LLM=off` (modo determinístico) ou simplesmente não usar o comando `agent` — o caminho legado (`check`/`latest`/...) nunca é tocado.

## Standards / common-mistakes referenced

- Nenhum `.agents/standards/` ou `.agents/common-mistakes/` existe no repo — convenções derivadas do próprio codebase:
  - `core/executor.py:1-4` — constraint de 1 GB RAM (sequencial, 1 browser): aplica a todos os increments.
  - `tests/test_executor.py:26-38` — padrão de mock de Playwright: aplica a Inc 2, 6.
  - `tests/test_repositories.py:37-95` — padrão de DB in-memory: aplica a Inc 3, 6, 8.
  - `agent_api.py:28` (`_err`) — contrato JSON/exit-code: aplica a Inc 7, 8, 9.
  - `db/database.py:38-81` — tabelas aditivas em `init_db`: aplica a Inc 6, 8.
  - Notas Ollama (thinking models / `num_predict`) — aplica a Inc 1 (`agents/llm.py`).

## Open questions (CONSIDER from review)

- (preenchido pelo self-review)

## Out of scope

- Telegram + fila (Celery/Redis) — interface futura; hermes/Discord permanece.
- Substituir o hermes pelo MAS como orquestrador de topo (o MAS orquestra o pipeline de preço, não o chat).
- Agentes multi-processo / distribuídos.
- Self-healing por visão computacional (screenshot) — apenas HTML bruto em texto.
- Adicionar novas stores.
- Re-scrape seletivo (só stores suspeitas) no loop de feedback — re-scrape total por iteração.
- TTL/limpeza automática de `selector_overrides` e `agent_runs` incompletos.
- CI/lint (repo não tem; manter status quo).
