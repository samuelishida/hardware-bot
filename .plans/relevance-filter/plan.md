# Relevance Filter & Self-Healing for Search Results

## Context

Buscando **"PS5"**, o PreçoBot retornou da KaBuM! um **"Adaptador USB Sony PS Link"**
(R$ 119,00) em vez do console (R$ 4.799,90 na Amazon). O agente teve que sinalizar
manualmente que o resultado era um acessório, não o produto.

Causa raiz (verificada no código):

1. **`ScrapeResult` não carrega o título do produto casado.** Os scrapers extraem o
   nome internamente (KaBuM `p["name"]`, Amazon `p["name"]`, Pichau `name`, etc.) mas
   **descartam** ao montar o `ScrapeResult` — que só tem `store_id, price, available,
   stock_label, url`. O Analista não tem como julgar relevância: vê só preço e URL.
2. **Listas de exclusão inconsistentes por scraper.** Amazon tem `SYSTEM_EXCLUSIONS`
   rica (`adaptador`, `cabo`, `acessório`, `suporte`, `cooler`...); KaBuM/Pichau/Terabyte
   só têm termos de PC/sistema. Por isso a Amazon filtrou o acessório e a KaBuM não.
3. **O Analista só valida plausibilidade de preço**, nunca relevância do produto.
4. **Self-healing só conserta seletores CSS**, não relevância.

Resultado pretendido: o pipeline rejeita acessórios/irrelevantes de forma determinística
na origem (scraper), com um gate de relevância do agente (LLM) para casos ambíguos, e
**aprende** exclusões persistentes (self-healing) para rodadas futuras — sem depender do
LLM toda vez.

## Architectural decisions

- **Decision: filtro em camadas (scraper determinístico + gate do agente no Analista).**
  Rationale: o scraper rejeita o óbvio (termos de acessório) sem custo de LLM; o Analista
  cobre o ambíguo e aprende. Alternativas rejeitadas: só no scraper (não "usa os agentes"),
  só no Analista (depende do LLM sempre, caro e lento).
- **Decision: o filtro de relevância roda em Python, não no JS do browser.**
  Rationale: o JS já devolve candidatos com `name`; aplicar `is_relevant` em Python evita
  injetar termos no JS e mantém a lista compartilhada num único lugar. O JS continua como
  pré-filtro de candidatos (keyword match), o Python é o filtro autoritativo.
- **Decision: `relevance_overrides` por store (aprendido) + `ACCESSORY_TERMS` compartilhado
  (baseline em código).** Rationale: baseline forte para todas as lojas + aprendizado
  específico por loja. `UNIQUE(store_id, term)`.
- **Decision: self-healing de relevância reusa o padrão de seletores** — "override é
  otimização, nunca requisito". Qualquer falha (LLM fora, termo inválido, DB fora) → no-op
  com log; o resultado original é preservado.
- **Decision: persistir o título casado em `price_history.data`.** Rationale: observabilidade
  — dá para auditar por que um resultado foi aceito/rejeitado. Barato (JSON data já existe).

## Assumptions and answers from code

- Decision: `ScrapeResult` é o ponto de entrada do título. Source: code @ `scrapers/base.py:117`.
- Decision: o Analista já tem o hook LLM (`_llm_validate_one`) para estender com relevância.
  Source: code @ `agents/nodes/analyst_node.py:196`.
- Decision: `is_relevant` vive em `scrapers/relevance.py` (camada scrapers, como `errors.py`),
  importável pelo Analista sem ciclo. Source: padrão de `scrapers/errors.py` re-exportado em
  `agents/errors.py`.
- Decision: o loop de feedback (Analista → Scraper) já existe e pode aproveitar o termo
  aprendido na mesma rodada. Source: code @ `agents/orchestrator.py:118` (`_route_after_analyst`).
- Decision: `self_healing_status` MCP mantém contrato (lista de seletores); relevância ganha
  tool nova `relevance_status`. Source: code @ `agents/mcp_server.py:78`.
- Decision: `is_relevant` exige todos os keywords significativos (len>=2) no título — mesmo
  comportamento dos scrapers atuais (sem regressão). Source: code @ `scrapers/kabum.py:78`.

## Risks accepted

- **Over-filtering**: `is_relevant` exigir todos os keywords pode rejeitar produto válido
  (ex.: busca "RTX 4060 Ti" casando um "RTX 4060" sem o "Ti"). Mitigação: mesmo
  comportamento dos scrapers atuais; o gate LLM do Analista pode reverter (LLM nunca
  *aprova* rejeição determinística, mas o scraper pode ser permissivo). Aceito; revisitar
  se houver falso-negativo.
- **Título ausente** (fallback de scraper sem nome): `is_relevant` retorna `True` (não julga)
  e o gate LLM não tem título para julgar. Aceito; degrada para o comportamento atual.
- **Custo de LLM no Analista**: uma chamada extra por store validada com título. Mitigação:
  só para stores com título; `auto` degrada para determinístico se o LLM não responder.
- **Churn de testes**: refatorar 6 scrapers + Analista + repos quebra testes existentes.
  Mitigação: cada incremento atualiza seus testes; `pytest` é o gate.

## Increment DAG

- Inc 1 — Title plumbing (S) — depends on: none — unblocks: 2, 6
- Inc 2 — Relevance module + repo + KaBuM/Amazon (M) — depends on: 1 — unblocks: 3, 4
- Inc 3 — Relevance in Pichau/Terabyte/OLX/Enjoei (M) — depends on: 2 — unblocks: 4
- Inc 4 — Analyst relevance gate (M) — depends on: 2, 3 — unblocks: 5
- Inc 5 — Self-healing learns exclusions (M) — depends on: 4 — unblocks: none
- Inc 6 — Persist title + observability (S) — depends on: 1 — unblocks: none

## Increments

### Inc 1 — Title plumbing (S)
**Status: done**
**Depends on:** none
**Unblocks:** 2, 6
**Done criteria:** `ScrapeResult`, `ValidatedPrice` e `AgentResult` carregam `title`
(default `None`); `agent_api` serializa `title`; testes verdes.

> Nota: nesta fase o `title` flui como `None` até `AgentResult.to_dict()` — o Analista
> só passa a popular `title` no dict validado no Inc 4. O critério de done é o campo
> existir e serializar, não estar preenchido.

#### Files to touch

##### scrapers/base.py
- What changes: adiciona campo `title` ao dataclass `ScrapeResult`.
- Data shapes: `title: Optional[str] = None` (após `url`).
- Integration points: todos os `ScrapeResult(...)` continuam válidos (default `None`).
- Error paths: nenhum — campo opcional.

##### agents/nodes/analyst_node.py
- What changes: adiciona `title: str | None = None` ao dataclass `ValidatedPrice`.
- Data shapes: campo novo opcional.
- Integration points: `_to_validated_price` no orquestrador lê `title` do dict validado.

##### agents/orchestrator.py
- What changes: `_to_validated_price` copia `title` do dict validado para `ValidatedPrice`.
- Function(s): `_to_validated_price(v: dict) -> ValidatedPrice`.
- Data shapes: `title=v.get("title")`.

##### agent_api.py
- What changes: `_store_dict` inclui `title` (de `ScrapeResult`/`PriceRecord`).
- Function(s): `_store_dict(r, *, with_scraped_at=False)`.
- Data shapes: `d["title"] = getattr(r, "title", None)`.

#### Edge cases
- `title` ausente em resultados legados (DB) → `None`, serializa como `null`.

#### Verification
- Run: `python3 -m pytest tests/test_analyst_node.py tests/test_scraper_node.py tests/test_embeds.py -q`
- Tests to add/update: assert `title` default `None` em `ScrapeResult`/`ValidatedPrice`;
  `_store_dict` inclui `title`.
- Done: testes verdes; `title` flui até `AgentResult.to_dict()`.

### Inc 2 — Relevance module + repo + KaBuM/Amazon (M)
**Status: done**
**Depends on:** 1
**Unblocks:** 3, 4
**Done criteria:** `scrapers/relevance.py` existe com `ACCESSORY_TERMS` + `is_relevant`;
`relevance_repo.py` + tabela `relevance_overrides` criados; KaBuM e Amazon setam `title`
e rejeitam acessórios via `is_relevant`; testes verdes.

> O repo e a tabela de relevância são criados **aqui** (não no Inc 5) porque os scrapers
> já os consomem nesta fase. O Inc 5 fica só com a superfície de observabilidade
> (MCP `relevance_status` + `agent_api relevance-status`) e os testes de aprendizado.

#### Files to touch

##### db/database.py
- What changes: cria tabela `relevance_overrides` no `init_db`.
- Data shapes:
  ```sql
  CREATE TABLE IF NOT EXISTS relevance_overrides (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      store_id   TEXT NOT NULL,
      term       TEXT NOT NULL,
      source     TEXT NOT NULL DEFAULT 'llm',
      created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
      UNIQUE(store_id, term)
  );
  ```

##### db/repositories/relevance_repo.py (novo)
- What changes: CRUD de termos de relevância.
- Function(s):
  - `get_terms(store_id: str) -> list[str]`
  - `add_term(store_id: str, term: str, source: str = "llm") -> None`
  - `get_all_terms() -> list[dict]`
- Data shapes: `get_terms` → lista de termos; `add_term` → `INSERT ... ON CONFLICT DO NOTHING`.
- Error paths: DB fora → `[]`/no-op com log (override é otimização, nunca requisito).

##### scrapers/relevance.py (novo)
- What changes: módulo compartilhado de relevância.
- Function(s):
  - `is_relevant(title: str | None, search_term: str, extra_terms: list[str] | None = None) -> bool`
  - `ACCESSORY_TERMS: list[str]` (consolidado da `SYSTEM_EXCLUSIONS` da Amazon + termos de
    acessório: `adaptador`, `cabo`, `acessório`, `suporte`, `base`, `cooler`, `ventoinha`,
    `dissipador`, `pasta térmica`, `conector`, `bracket`, `protetor`, `capa`, `riser`,
    `extensão`, `extensor`, `water block`, `backplate`, `fonte`, `gabinete`, `pastilha`,
    `compatível com`, `para hdmi`, `cabo displayport`, `cabo hdmi`, `fibra ótica`, ...).
- Data shapes: `is_relevant` → `False` se `title` vazio? Não — `title` vazio → `True`
  (não julga). `False` se qualquer termo de acessório em `title`; `False` se nem todos os
  keywords significativos (len>=2) de `search_term` estão em `title`; senão `True`.
- Integration points: importado por scrapers e pelo Analista (Inc 4).
- Error paths: `title=None` → `True` (degrade).

> Nota: a checagem de keywords do `is_relevant` é redundante com o pré-filtro JS dos
> scrapers (todos já exigem `matchKws.every(...)`). O comportamento **novo** é a checagem
> de termos de acessório; a checagem de keywords fica como rede de segurança para o
> Analista (Inc 4), que recebe candidatos já filtrados.

##### scrapers/kabum.py
- What changes: após o JS devolver `products`, filtra por `is_relevant(p["name"], ...)`
  com os termos de `relevance_overrides` da store; seta `title=p["name"]` no `ScrapeResult`.
- Function(s): `scrape()` — no trecho de "pick best".
- Data shapes: `ScrapeResult(..., title=name)`.
- Integration points: busca termos via `relevance_repo.get_terms("kabum")` (async, antes de
  escolher o produto).
- Error paths: DB fora → termos vazios (filtra só com `ACCESSORY_TERMS`); nenhum relevante →
  `NOT_FOUND`.

##### scrapers/amazon.py
- What changes: idem KaBuM — filtra `products` por `is_relevant(p["name"], ...)`, seta
  `title=p["name"]`.
- Function(s): `_browser_attempt()` — trecho de "pick best".
- Data shapes: `ScrapeResult(..., title=name)`.
- Integration points: `relevance_repo.get_terms("amazon")`.
- Error paths: idem KaBuM.

#### Edge cases
- `products` vazio após filtro de relevância → `NOT_FOUND` (não retorna acessório).
- `title` ausente em algum candidato → `is_relevant` retorna `True` (não filtra).

#### Verification
- Run: `python3 -m pytest tests/test_scrapers.py tests/test_antibot.py -q`
- Tests to add/update: `is_relevant` unit tests (acessório rejeitado, keyword faltante
  rejeitado, título válido aceito, `title=None` aceito); scraper KaBuM/Amazon rejeita
  acessório e seta `title`.
- Done: testes verdes; KaBuM não retorna "Adaptador USB Sony PS Link" para "PS5".

### Inc 3 — Relevance in Pichau/Terabyte/OLX/Enjoei (M)
**Status: done**
**Depends on:** 2
**Unblocks:** 4
**Done criteria:** Pichau, Terabyte, OLX e Enjoei setam `title` e aplicam `is_relevant`;
testes verdes.

#### Files to touch

##### scrapers/pichau.py
- What changes: no loop de `scored`, filtra por `is_relevant(name, ...)`; seta `title=name`.
- Function(s): `scrape()`.
- Data shapes: `ScrapeResult(..., title=name)`.
- Integration points: `relevance_repo.get_terms("pichau")`.

##### scrapers/terabyte.py
- What changes: filtra `products` por `is_relevant(p["name"], ...)`; seta `title=p["name"]`.
- Function(s): `_browser_attempt()`.
- Data shapes: `ScrapeResult(..., title=name)`.
- Integration points: `relevance_repo.get_terms("terabyte")`.

##### scrapers/olx.py
- What changes: `_pick_best` filtra por `is_relevant(o["title"], ...)`; seta `title=o["title"]`.
- Function(s): `_pick_best(offers, fallback_url, extra_terms=None)` — **mantém sync**;
  os termos são buscados no `scrape()` (async) e passados como argumento.
- Data shapes: `ScrapeResult(..., title=title)`.
- Integration points: `scrape()` chama `relevance_repo.get_terms("olx")` (async) e repassa
  a `_pick_best`; `_pick_best` usa `is_relevant(title, search_term, extra_terms)`.

##### scrapers/enjoei.py
- What changes: `_pick_best` filtra por `is_relevant(o["title"], ...)`; seta `title=o["title"]`.
- Function(s): `_pick_best(offers, fallback_url, extra_terms=None)` — **mantém sync**;
  os termos são buscados no `scrape()` (async) e passados como argumento.
- Data shapes: `ScrapeResult(..., title=title)`.
- Integration points: `scrape()` chama `relevance_repo.get_terms("enjoei")` (async) e
  repassa a `_pick_best`; `_pick_best` usa `is_relevant(title, search_term, extra_terms)`.

#### Edge cases
- OLX/Enjoei são usados (C2C): `is_relevant` pode rejeitar anúncios com título genérico.
  Mitigação: `title` ausente → `True`; o gate LLM do Analista (Inc 4) cobre o ambíguo.

#### Verification
- Run: `python3 -m pytest tests/test_scrapers.py tests/test_olx.py tests/test_enjoei.py -q`
- Tests to add/update: cada scraper seta `title` e rejeita acessório.
- Done: testes verdes; todos os 6 scrapers aplicam `is_relevant`.

### Inc 4 — Analyst relevance gate (M)
**Status: done**
**Depends on:** 2, 3
**Unblocks:** 5
**Done criteria:** Analista rejeita título irrelevante (determinístico + LLM); LLM pode
retornar `offending_term`; testes verdes.

#### Files to touch

##### agents/nodes/analyst_node.py
- What changes: adiciona checagem de relevância determinística (fallback) + gate LLM.
- Function(s):
  - `run()` — lê `search_term = state.get("search_term")` e `title = getattr(o.result, "title", None)`
    do `ScrapeResult`; após as regras de preço, se `title` presente e
    `not is_relevant(title, search_term, terms)` → `suspicious` com `reason="produto irrelevante"`,
    `source="deterministic"`. O dict validado ganha `title` (copiado de `o.result.title`).
  - `_llm_validate_one()` — adiciona `title` e `search_term` ao payload; **atualiza o system
    prompt** para pedir `{"valid", "reason", "confidence", "offending_term"}`; LLM retorna
    `offending_term`.
  - `_llm_pass()` — se `valid=false` e `offending_term` presente → persiste via
    `relevance_repo.add_term(store_id, offending_term)` (self-healing) e move para `suspicious`.
- Data shapes: dict validado ganha `title` (fonte: `o.result.title`); `ValidatedPrice` já tem
  `title` (Inc 1).
- Integration points: `scrapers.relevance.is_relevant`; `relevance_repo.get_terms`/`add_term`.
- Error paths: `relevance_repo` fora → termos vazios / `add_term` loga e segue; LLM fora →
  mantém decisão determinística.

##### agents/state.py
- What changes: `GRAPH_KEYS` e `AgentResult` já carregam `title` via `ValidatedPrice` (Inc 1);
  sem mudança estrutural. Confirmar `title` no dict validado trafega pelo grafo.

#### Edge cases
- `title=None` → pula checagem determinística e gate LLM (não julga).
- LLM rejeita com `confidence < 0.6` → mantém validada (mesma regra de preço).
- `offending_term` vazio/curto (<2 chars) → não persiste (evita ruído).

#### Verification
- Run: `python3 -m pytest tests/test_analyst_node.py tests/test_orchestrator.py -q`
- Tests to add/update: Analista rejeita título com termo de acessório; LLM rejeita e persiste
  `offending_term`; LLM fora → mantém validada.
- Done: testes verdes; Analista rejeita "Adaptador USB Sony PS Link" para "PS5".

### Inc 5 — Self-healing learns exclusions (M)
**Status: done**
**Depends on:** 4
**Unblocks:** none
**Done criteria:** superfície de observabilidade do aprendizado — MCP `relevance_status` +
`agent_api relevance-status`; testes de aprendizado de ponta a ponta; testes verdes.

> O repo e a tabela `relevance_overrides` já foram criados no Inc 2; o aprendizado
> (`add_term` no Analista) já existe no Inc 4. Este incremento expõe o estado aprendido
> e cobre o fluxo de aprendizado com testes.

#### Files to touch

##### agents/mcp_server.py
- What changes: nova tool `relevance_status()` → `relevance_repo.get_all_terms()`.
- Function(s): `relevance_status() -> dict | list[dict]`.
- Integration points: registrada via `mcp.tool()(relevance_status)`.

##### agent_api.py
- What changes: novo comando `relevance-status` → `relevance_repo.get_all_terms()`.
- Function(s): `cmd_relevance_status()`.

#### Edge cases
- Termo aprendido duplicado → `ON CONFLICT DO NOTHING` (idempotente, já no Inc 2).
- `relevance_overrides` ausente em DB antigo → `init_db` cria; leitura degrada para `[]`.

#### Verification
- Run: `python3 -m pytest tests/test_mcp_server.py tests/test_agent_api.py tests/test_analyst_node.py -q`
- Tests to add/update: MCP `relevance_status`; `agent_api relevance-status`; teste de
  aprendizado (Analista rejeita acessório → `add_term` → `get_terms` retorna o termo).
- Done: testes verdes; termo aprendido persiste e filtra rodadas futuras.

### Inc 6 — Persist title + observability (S)
**Status: done**
**Depends on:** 1
**Unblocks:** none
**Done criteria:** `insert_price` persiste `title` em `price_history.data`; `PriceRecord` lê
`title`; trace registra decisões de relevância; testes verdes.

#### Files to touch

##### db/repositories/price_repo.py
- What changes: `insert_price` adiciona `title` ao `json_object`; `_COLS` extrai `title`;
  `PriceRecord` ganha campo `title`.
- Function(s): `insert_price(...)`, `_to_record(r)`.
- Data shapes: `json_object('search_term', ?, 'stock_label', ?, 'url', ?, 'title', ?)`;
  `json_extract(data, '$.title') AS title`.
- Integration points: `toolkit.scrape_and_store` passa `title=r.title`.
- **Compatibilidade**: `title` é **opcional** (`title: str | None = None`) — callers legados
  (`scripts/import_local_data.py`, testes existentes) continuam válidos sem o parâmetro.

##### toolkit.py
- What changes: `scrape_and_store` passa `title=r.title` ao `insert_price`.
- Function(s): `scrape_and_store(product)`.

##### agents/nodes/analyst_node.py
- What changes: trace do Analista registra `n_irrelevant` e `irrelevant_stores`.
- Data shapes: entrada de trace com `n_irrelevant` (contagem de `suspicious` com
  `reason == "produto irrelevante"`) e `irrelevant_stores` (lista de `store_id` desses).

##### agent_api.py
- What changes: `_store_dict` já inclui `title` (Inc 1); `cmd_history`/`cmd_latest` incluem
  `title` no JSON.

#### Edge cases
- Linhas legadas sem `title` no data JSON → `json_extract` retorna `NULL` → `title=None`.

#### Verification
- Run: `python3 -m pytest tests/test_repositories.py tests/test_embeds.py tests/test_integration.py -q`
- Tests to add/update: `insert_price` persiste `title`; `PriceRecord.title` lido do DB;
  trace do Analista tem `n_irrelevant`.
- Done: testes verdes; título persiste e é auditável.

## Cross-cutting verification

Após o Inc 5, rodar o pipeline MAS de ponta a ponta para **"PS5"** e confirmar que:
- KaBuM não retorna o "Adaptador USB Sony PS Link" (filtro determinístico no scraper).
- Se um acessório novo passar, o gate LLM do Analista o rejeita e aprende o termo
  (`relevance-status` mostra o override).
- `agent_api.py agent "PS5"` retorna só produtos relevantes; `agent_api.py relevance-status`
  lista os termos aprendidos.

## Standards / common-mistakes referenced

- `.agents/learnings/mas-review-fixes.md` — aplica a: `agents/orchestrator.py` (mutação de
  estado), `agents/nodes/analyst_node.py` (baseline), `agents/llm.py` (payload Ollama),
  `agent_api.py` (parsing CLI). Revisar antes de editar esses arquivos.
- `.agents/learnings/remove-mercadolivre.md` — aplica a: `scrapers/__init__.py`, `config.py`
  (registry). Não estamos removendo store, mas o padrão de inventariar referências vale para
  `SYSTEM_EXCLUSIONS` (consolidar em `ACCESSORY_TERMS` sem perder termos).

## Open questions (CONSIDER from review)

- **Rollback do schema**: se o Inc 6 for revertido, linhas legadas de `price_history` com
  `title` no data JSON são lidas por um `PriceRecord` sem o campo → `getattr(r, "title", None)`
  tolera. Não há migração destrutiva; confirmar que `_store_dict` usa `getattr` (Inc 1) como
  rede de segurança.
- **`n_irrelevant` no trace**: definido como contagem de `suspicious` com
  `reason == "produto irrelevante"` (ver Inc 6). Confirmar que o Analista não mistura com
  suspeitas de preço no mesmo contador.
- **`is_relevant` keyword check é redundante com o JS**: os scrapers já filtram por
  `matchKws.every(...)`; a checagem de keywords em Python é rede de segurança para o
  Analista (que recebe candidatos já filtrados), não comportamento novo. Aceito.

## Out of scope

- Não alterar o loop de feedback do orquestrador (re-scrape) além do que o termo aprendido
  já aproveita.
- Não adicionar ranking de relevância por score (apenas filtro binário relevante/irrelevante).
- Não migrar `SYSTEM_EXCLUSIONS` de OLX/Enjoei para `ACCESSORY_TERMS` se houver termos
  específicos de C2C que não se aplicam a lojas novas — manter separados se necessário.
- Não tocar no `hermes`/Discord toolset (fora do escopo do toolkit).
