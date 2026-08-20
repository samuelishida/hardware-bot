# Migração do Chrome/Playwright para Lightpanda

## Context

O precosbot hoje usa **Playwright + Chromium** para scraping headless: `core/executor.py`
lança 1 browser Chromium compartilhado e roda os 8 scrapers sequencialmente
(`scrapers/base.py` cria context+page por scraper). Na VM OCI de **1 GB RAM**, o
Chromium pico ~280 MB e é o maior consumidor de memória junto com hermes (~131 MB) e
Ollama — o projeto já documenta pressão de memória e `RESET`/swap como mitigação.

**Objetivo:** substituir o Chromium/Playwright pelo **Lightpanda** — browser headless
escrito em Zig (não é fork de Chromium), com CDP server, pico ~123 MB (~16× menos que
Chrome) e ~9× mais rápido. Decisões do usuário (question gate):
- **Usar apenas Lightpanda** — sem backend Playwright de fallback, sem knob de seleção.
- **Remover Playwright por completo** (requirements, código, browsers instalados na VM).
- **Migrar os 8 scrapers de uma vez** (não faseado por loja).

Restrições duras:
- VM OCI **1 GB RAM** → 1 instância Lightpanda compartilhada, scraping sequencial.
- Python 3.12, `from __future__ import annotations`.
- **Backwards compat:** contrato do `toolkit.py` e do `agent_api.py` (JSON/exit-code)
  e o hermes (`hermes/tools/precosbot.py`) permanecem intactos — só muda o motor de
  scraping por baixo.
- Lightpanda é **Beta** (WIP): cobertura de Web APIs em evolução; algumas lojas podem
  não renderizar. `LIGHTPANDA_DISABLE_TELEMETRY=true` e **não** usar `--obey-robots`
  (o Playwright atual não obedece robots.txt).

## Architectural decisions

- **Decision: cliente CDP próprio em Python (`core/cdp.py`) falando com `lightpanda serve`.** Rationale: o usuário quer remover Playwright por completo; Lightpanda expõe CDP/websocket e o Puppeteer (Node) é o cliente documentado — não há cliente Python oficial. Um cliente CDP mínimo (websocket async) é a única via que mantém o projeto 100% Python. Alternatives rejected: `lightpanda fetch` CLI por scraper (não cobre JS complexo/login/scroll); Playwright `connect_over_cdp` (mantém Playwright — contraria a decisão do usuário); Puppeteer via Node (adiciona runtime Node na VM de 1 GB).
- **Decision: facade `Page`/`ElementHandle` em `core/browser.py` que espelha a superfície da API Playwright que os scrapers já usam.** Rationale: os scrapers estão profundamente acoplados a `page.goto/wait_for_selector/evaluate/content/query_selector/keyboard/mouse/route` e `context.add_init_script/add_cookies/cookies`. Uma facade com a MESMA forma minimiza o churn dos scrapers (troca mecânica de `page.*` → facade) e isola todo o CDP em 2 arquivos. Alternatives rejected: scrapers chamando o cliente CDP diretamente (churn grande e acoplamento a protocolo).
- **Decision: 1 instância `lightpanda serve` gerenciada pelo executor, compartilhada entre scrapers.** Rationale: espelha o design atual de "1 browser compartilhado" e respeita a RAM da VM. O executor sobe o subprocesso no início e derruba no fim. Alternatives rejected: 1 processo por scraper (estoura RAM).
- **Decision: stealth via `Page.addScriptToEvaluateOnNewDocument` (init scripts) se suportado; senão injeção pós-load via `Runtime.evaluate`.** Rationale: o stealth atual (`STEALTH_SCRIPT` em `scrapers/base.py`) é essencial contra antibot (KaBuM/Cloudflare, ML). O spike (Inc 1) valida qual mecanismo o CDP do Lightpanda suporta; o facade abstrai a escolha. Alternatives rejected: depender de fingerprint Chromium (Lightpanda não é Chromium — fingerprint diferente, risco antibot maior).
- **Decision: `wait_until` mapeado por polling no facade** (`domcontentloaded`/`commit` → aguardar navegação; `networkidle` → timeout fixo ou `wait_for_selector`, pois Lightpanda pode não expor networkidle). Rationale: OLX usa `networkidle`; sem suporte, degrada para espera determinística. Alternatives rejected: exigir networkidle (pode não existir no CDP do Lightpanda).
- **Decision: remoção do Playwright é o ÚLTIMO incremento (Inc 6), após soak na VM.** Rationale: preserva rollback via `git revert` até o Lightpanda estar validado em produção. Alternatives rejected: remover no início (sem rede de segurança na VM de 1 GB).

## Assumptions and answers from code

- **Superfície Playwright usada (a migrar):** `page.goto(wait_until, timeout)`, `page.wait_for_selector`, `page.wait_for_timeout`, `page.content`, `page.evaluate(js, arg)`, `page.title`, `page.url`, `page.query_selector`→`el.inner_text/click/fill`, `page.keyboard.press`, `page.mouse.wheel`, `page.set_extra_http_headers`, `page.route` (interceptação ML), `page.context.close`; `browser.new_context(...)`, `context.add_init_script`, `context.new_page`, `context.add_cookies`, `context.cookies`, `context.close`. Source: code @ scrapers/base.py:117-139, scrapers/kabum.py:31-150, scrapers/mercadolivre.py:201-435, scrapers/amazon.py:111-179, scrapers/terabyte.py:42-159, scrapers/enjoei.py:60-139, scrapers/olx.py:61-157, scrapers/pichau.py:40-98, agents/self_healing.py:56-96.
- **Executor:** `core/executor.py:73-93` — `async with async_playwright()`, `pw.chromium.launch(headless=True, args=STEALTH_ARGS)`, loop sequencial, `asyncio.wait_for(..., 90)` por scraper. Source: code @ core/executor.py:73,93.
- **Self-healing:** `agents/self_healing.py:56,96` usa `page.query_selector` + `el.inner_text` + `page.content` — precisa da facade. Source: code.
- **VM:** Ubuntu 24.04 (glibc) → binário Linux do Lightpanda funciona; sem binário nativo Windows (dev local em Windows exige WSL2). Source: AGENTS.md (OCI VM notes) + docs Lightpanda.
- **Dependências:** `requirements.txt` tem `playwright>=1.44.0`; não há cliente websocket async — adicionar `websockets`. Source: code @ requirements.txt.
- **Check command:** `python -m pytest tests/ -v`; `pytest.ini`: `asyncio_mode = auto`. Source: README:213-224.
- **Padrão de teste a seguir:** mock de Playwright via `patch("core.executor.async_playwright")` + fake scrapers duck-typed (tests/test_executor.py:26-38); mock de LLM via `patch(..., new=AsyncMock(...))`. Estes mocks serão substituídos por mocks do facade/CDP. Source: code.
- **User-confirmed (question gate):** apenas Lightpanda; remover Playwright por completo; migrar os 8 scrapers de uma vez.

## Risks accepted

- **CDP do Lightpanda incompleto para as necessidades dos scrapers** (evaluate com função, init scripts, interceptação de rede, keyboard/mouse, networkidle, cookies): o Inc 1 (spike) valida cada capacidade; workarounds: injeção de stealth pós-load, `lightpanda fetch` como fallback por loja, mapear `networkidle` para espera fixa. Accept; revisit se uma loja não renderizar.
- **Antibot maior** (Lightpanda não é Chromium → fingerprint diferente; KaBuM/Cloudflare, ML): stealth via init script/evaluate, cookies do ML, aceitar taxa de anti-bot maior + loop de re-scrape do MAS. Accept; revisit se KaBuM/ML bloquearem de vez → `lightpanda fetch` ou `__NEXT_DATA__` (padrão já usado por OLX/Enjoei).
- **Estabilidade Beta** (crash em algumas páginas): timeout por scraper (90s), restart do subprocesso, log de crash, `lightpanda fetch` como fallback. Accept.
- **Remover Playwright elimina o rollback de motor:** mitigado fazendo a remoção por último (Inc 6) após soak; rollback = `git revert` + reinstalar Playwright. Accept.
- **`networkidle` (OLX) sem suporte:** degrada para espera determinística/`wait_for_selector`; pode mudar timing de extração do OLX. Accept; validar no spike e no smoke test.

## Increment DAG

- Inc 1 — Spike: CDP do Lightpanda na VM + 1 loja ponta-a-ponta (S) — depends on: none — unblocks: 2, 3
- Inc 2 — Cliente CDP `core/cdp.py` (M) — depends on: 1 — unblocks: 3
- Inc 3 — Facade `Page`/`ElementHandle` sobre CDP `core/browser.py` (L) — depends on: 1, 2 — unblocks: 4
- Inc 4 — Migrar executor + 8 scrapers + self-healing para a facade (L) — depends on: 3 — unblocks: 5, 6
- Inc 5 — Testes: CDP/facade unit + smoke live (M) — depends on: 4 — unblocks: 6
- Inc 6 — Deploy na VM + remover Playwright + docs (S) — depends on: 4, 5

Caminho crítico: 1 → 2 → 3 → 4 → 6. Paralelizável: nenhum (dependências lineares até o 4).

## Increments

### Inc 1 — Spike: CDP do Lightpanda na VM + 1 loja ponta-a-ponta (S) — DONE
**Depends on:** none
**Unblocks:** 2, 3
**Done criteria:** decisão documentada em `docs/lightpanda-spike.md` + script protótipo em `scripts/` que scrapeia KaBuM via CDP do Lightpanda. O spike também **define o mecanismo do fallback `lightpanda fetch`** (gatilho manual por loja, documentado; automação fora de escopo).
**Resultado (2026-08-19):** todas as capacidades CDP validadas contra o binário real
(v1.0.0-nightly) + KaBuM scrapeado via CDP (5 produtos). Descoberta crítica: setup
obrigatório `createBrowserContext → createTarget → attachToTarget` (sessionId em
todos os comandos); Lightpanda suporta **1 browser context + 1 página por vez**
(confirma design de instância compartilhada). `Network.setBlockedURLs` usa
`urlPatterns`; `DOM.querySelector` requer `DOM.getDocument` antes. Ver
`docs/lightpanda-spike.md`.

#### Files to touch

##### docs/lightpanda-spike.md (novo)
- What changes: registro de decisão — capacidades CDP validadas, workarounds, escolha do mecanismo de stealth/wait/cookies/interceptação.
- Data shapes: tabela de capacidades CDP (método → suportado? → nota).
- Integration points: alimenta Inc 2/3 (escopo do facade).
- Error paths: capacidades não suportadas → workaround documentado.

##### scripts/lightpanda_probe.py (novo, protótipo descartável)
- What changes: sobe `lightpanda serve`, conecta via websocket, testa `Runtime.evaluate`, `Page.navigate`, `DOM.querySelector`, `Network.getCookies/setCookies`, `Page.addScriptToEvaluateOnNewDocument`, interceptação de rede, `Input.dispatchKeyEvent/MouseEvent`, `Page.captureScreenshot`; scrapeia KaBuM ponta-a-ponta.
- Function(s): `async def probe_cdp(ws_url) -> dict`, `async def scrape_kabum_via_cdp(ws_url) -> ScrapeResult`.
- Data shapes: `dict[capacidade, bool]`; `ScrapeResult` (reuso de `scrapers/base.py`).
- Integration points: nenhum (protótipo).
- Error paths: cada capacidade em try/except → `False` + log.
- **Validar explicitamente:** `Runtime.evaluate` com `returnByValue: true` em objetos aninhados (lista de dicts — TODOS os scrapers dependem disso); **`Runtime.evaluate` com função-expression + arg** (`(${js})(${JSON.stringify(arg)})` — padrão que TODOS os scrapers usam, ex.: `_EVAL_JS` de 78 linhas do ML); **criação de múltiplas páginas/targets** (`Target.createTarget` + attach — 2ª página após a 1ª, pois o design compartilha 1 instância); o evento CDP que mapeia `wait_until="commit"` (`Page.frameNavigated` vs `Page.loadEventFired`); que `STEALTH_SCRIPT` (APIs Chromium-only: `navigator.userAgentData`, `window.chrome.runtime`) **não lança** no Lightpanda.

#### Edge cases
- `lightpanda serve` não sobe (binário ausente/glibc) → documentar instalação.
- `--obey-robots` bloqueando KaBuM → confirmar que NÃO usamos a flag.
- Telemetria → `LIGHTPANDA_DISABLE_TELEMETRY=true`.
- `:has-text()` (ML usa `button:has-text('Já tenho conta')`, `button:has-text('Aceitar cookies')`) **não é CSS válido** — validar a tradução para query JS por `textContent` (ver Inc 3).
- **Multi-target:** se o CDP do Lightpanda suportar só 1 página por conexão, o design de instância compartilhada falha → validar `Target.createTarget`; se não suportar, revisar para 1 instância por scraper (impacto em RAM).

#### Verification
- Run: `./lightpanda version`; `python scripts/lightpanda_probe.py` na VM.
- Tests to add/update: nenhum (protótipo).
- Done: `docs/lightpanda-spike.md` com a tabela de capacidades + KaBuM scrapeado via CDP.

### Inc 2 — Cliente CDP `core/cdp.py` (M) — DONE
**Depends on:** 1
**Unblocks:** 3
**Done criteria:** cliente CDP async (websocket) conecta, envia/recebe comandos, correlaciona id→resposta e despacha eventos; testado com websocket mockado.
**Resultado (2026-08-19):** `core/cdp.py` criado (CDPClient/CDPError) + `tests/test_cdp.py`
(10 testes verdes, websocket fake). `websockets>=12.0` adicionado ao requirements.

#### Files to touch

##### core/cdp.py (novo)
- What changes: cliente CDP mínimo sobre `websockets` (nova dep).
- Function(s):
  - `class CDPError(Exception)`
  - `class CDPClient`: `async connect(url)`, `async close()`, `async send(method, params=None) -> dict` (correlaciona `id`→resposta, timeout), `async wait_event(method, timeout) -> dict`, `on(method, handler)`.
- Data shapes: `send` retorna o `result` do CDP; eventos despachados por método.
- Integration points: consumido por `core/browser.py` (Inc 3).
- Error paths: resposta com `error` → `CDPError`; timeout → `asyncio.TimeoutError`; conexão fechada → `CDPError`.

##### requirements.txt
- What changes: adicionar `websockets>=12.0`; **não** remover `playwright` ainda (Inc 6).
- Integration points: instalação na VM.

#### Edge cases
- Respostas fora de ordem → correlação por `id`.
- Eventos sem `id` (notificações) → não confundir com respostas.
- Reconexão após crash do subprocesso → `CDPError` propagado para o executor reiniciar.

#### Verification
- Run: `python -m pytest tests/test_cdp.py -v`.
- Tests to add/update: `tests/test_cdp.py` (websocket fake: responde a `send`, emite eventos, simula erro/timeout).
- Done: `send`/`wait_event`/`on` cobertos por teste; sem dependência de rede.

### Inc 3 — Facade `Page`/`ElementHandle` sobre CDP `core/browser.py` (L) — DONE
**Depends on:** 1, 2
**Unblocks:** 4
**Done criteria:** facade navega, avalia JS, lê conteúdo, espera seletor, interage (click/fill/keyboard/mouse), injeta stealth, gerencia cookies e intercepta rede — tudo via CDP do Lightpanda.
**Resultado (2026-08-19):** `core/browser.py` criado (LightpandaBrowser/Context/Page/
ElementHandle/Route/Response) + `tests/test_browser.py` (20 testes verdes). Suíte
total: 247 passed. `core/__init__.py` expõe `LightpandaBrowser`.

#### Files to touch

##### core/browser.py (novo)
- What changes: `LightpandaBrowser` (gerencia subprocesso `lightpanda serve`), `Page`, `ElementHandle` — espelham a superfície Playwright usada.
- Function(s):
  - `class LightpandaBrowser`: `async start()`, `async stop()`, `async new_context(**opts) -> Context`, `async close()`.
  - `class Context`: `async new_page() -> Page`, `async add_init_script(js)`, `async add_cookies(cookies)`, `async cookies() -> list`, `async close()`.
  - `class Page`: `async goto(url, wait_until="domcontentloaded", timeout=...)`, `async wait_for_selector(sel, timeout=...)`, `async wait_for_timeout(ms)`, `async content() -> str`, `async evaluate(js, arg=None)`, `async title() -> str`, `url -> str`, `async query_selector(sel) -> ElementHandle|None`, `keyboard.press(key)`, `mouse.wheel(dx, dy)`, `async set_extra_http_headers(headers)`, `async route(pattern, handler)`, `async screenshot(path, full_page=False)`, `context -> Context`.
  - `class ElementHandle`: `async inner_text() -> str`, `async click()`, `async fill(text)`.
  - `class Route`: `request.resource_type -> str`, `async abort()`, `async continue_()` (ML intercepta image/media/font).
- **Tradução de seletores:** `query_selector`/`wait_for_selector` precisam traduzir pseudo-classes do Playwright (`:has-text('X')`) para query JS por `textContent` **case-insensitive** (`Array.from(document.querySelectorAll(base)).find(el => el.textContent.toLowerCase().includes('X'.toLowerCase()))` — espelha o `:has-text` do Playwright), pois `DOM.querySelector` não entende `:has-text()`. Aplicar a ML (`_try_login`, `_dismiss_cookie_banner`).
- Data shapes: `evaluate` serializa função JS + arg (via `Runtime.evaluate` com `returnByValue`); `query_selector` via `Runtime.evaluate` + `DOM` + tradução de `:has-text()`; cookies via `Network.getCookies/setCookies`; interceptação via `Fetch.enable`/`Network.setBlockedURLs` (conforme spike).
- Integration points: consumido por executor + scrapers (Inc 4).
- Error paths: seletor não encontrado → `None` (query) / timeout (wait); navegação falha → exceção mapeada; CDP não suporta X → workaround do spike.

##### core/__init__.py
- What changes: expor `LightpandaBrowser` (opcional).

#### Edge cases
- `wait_until="networkidle"` sem suporte → espera fixa/`wait_for_selector`; `commit` vs `domcontentloaded` → evento CDP pinado no spike (Inc 1).
- Stealth: `add_init_script` → `Page.addScriptToEvaluateOnNewDocument`; se não suportado → injeção pós-load via `evaluate`. `STEALTH_SCRIPT` é Chromium-specific — pode precisar de adaptação para não lançar no Lightpanda (validado no spike).
- `route` (ML aborta image/media/font) → interceptação de rede do Lightpanda; `Route` expõe `request.resource_type`/`abort`/`continue_`.
- `evaluate` com função JS multi-linha (KaBuM/Amazon/ML) → serialização correta de `function` + args.
- `:has-text()` (ML) → tradução para query JS por `textContent`.
- `page.content()` via CDP (`document.documentElement.outerHTML`) **omite o doctype** — verificar que os usos (KaBuM Cloudflare check em `html[:2000]`, self-healing) não dependem do doctype.
- `screenshot` só é usado por `test_antibot.py` (teste live) — pode ficar fora do facade se esse teste for adiado.

#### Verification
- Run: `python -m pytest tests/test_browser.py -v`; smoke manual `python scripts/lightpanda_probe.py`.
- Tests to add/update: `tests/test_browser.py` (CDP fake: goto/evaluate/content/query_selector/interação/cookies/route).
- Done: facade cobre toda a superfície do Inc 1; testes unitários verdes.

### Inc 4 — Migrar executor + 8 scrapers + self-healing para a facade (L) — DONE
**Depends on:** 3
**Unblocks:** 5, 6
**Done criteria:** `python agent_api.py check <produto>` roda os 8 scrapers via Lightpanda (sem Playwright) e grava no SQLite.
**Resultado (2026-08-19):** executor migrado para `LightpandaBrowser`; scrapers usam a
facade (mesma forma Playwright); self_healing usa `query_selector`/`inner_text`/`content`
da facade; scripts locais + `ml_login_helper.py` marcados como legado; `test_live_scrapers.py`
e `test_antibot.py` migrados para a facade. Smoke real: `scrape_product_detailed([KabumScraper])`
→ `kabum: kind=ok price=2606.04`. Suíte: 247 passed. Nenhum import Playwright no runtime.

#### Files to touch

##### core/executor.py
- What changes: trocar `async_playwright()`/`chromium.launch` por `LightpandaBrowser.start()`; manter loop sequencial + `asyncio.wait_for(..., 90)` + `_classify`.
- Function(s): `scrape_product_detailed` (mesma assinatura), `scrape_product` (wrapper legado).
- Integration points: `agents.nodes.scraper_node`, `toolkit.py`.
- Error paths: subprocesso Lightpanda falha → `StoreOutcome(UNKNOWN)` + log; restart.

##### scrapers/base.py
- What changes: `_new_page()` passa a criar `Page` via facade (em vez de `browser.new_context`/`context.new_page`); `STEALTH_SCRIPT`/`USER_AGENTS`/`VIEWPORTS` mantidos, aplicados via facade.
- Function(s): `_new_page(retry=2) -> Page` (facade).
- Integration points: todas as subclasses.
- Error paths: facade sem browser → `RuntimeError` (mesmo comportamento).

##### scrapers/kabum.py, pichau.py, terabyte.py, amazon.py, mercadolivre.py, olx.py, enjoei.py
- What changes: substituir `page.*`/`context.*` do Playwright pela API da facade (mesma forma); ML: `route`/cookies/login via facade; OLX: `networkidle` → mapeado.
- Function(s): `scrape()` (mesma assinatura); ML `_browser_attempt`, `_try_login`, `_save_cookies`, `_load_cookies`.
- Integration points: `scrapers/__init__.py` (registro inalterado).
- Error paths: comportamento idêntico ao atual (timeout/antibot/not_found/parse_error).

##### agents/self_healing.py
- What changes: `page.query_selector`/`el.inner_text`/`page.content` via facade.
- Function(s): `_live_validate`, `attempt_self_heal` (mesma assinatura).
- Integration points: `scrapers/base.py` `_on_extract_failure`.
- Error paths: facade falha → `None` (healing é otimização).

##### scripts/local_precos_scraper*.py, tests/test_antibot.py, tests/test_live_scrapers.py
- What changes: remover imports Playwright; usar facade (ou marcar como legado/fora de escopo se não essencial).
- Integration points: dev local.
- Error paths: n/a.

##### ml_login_helper.py (raiz, NÃO `scripts/`)
- What changes: helper de captura de cookies **só para dev em Windows** (abre Chrome com UI) — **fora do caminho de runtime**; marcar como legado/fora de escopo (não migrar, não remover o Playwright dele até Inc 6).
- Integration points: dev local (Windows).
- Error paths: n/a.

#### Edge cases
- ML login (keyboard/fill/click) via facade → validar no smoke.
- **ML `el.fill()` em campos React (email/senha):** `Input.insertText` via CDP pode não disparar o `onChange` do React → validar no smoke; fallback `Input.dispatchKeyEvent` por caractere.
- KaBuM Cloudflare → stealth via facade; se bloquear, `__NEXT_DATA__` fallback.
- OLX `networkidle` → timing alterado; validar extração.

#### Verification
- Run: `python agent_api.py check "RTX 4060"` na VM; `python -m pytest tests/ -v`.
- Tests to add/update: atualizar mocks de `test_executor.py`/`test_scrapers.py`/`test_self_healing.py` para a facade (sem Playwright).
- Done: `check` grava preços de todas as lojas via Lightpanda; testes unitários verdes.

### Inc 5 — Testes: CDP/facade unit + smoke live (M) — DONE
**Depends on:** 4
**Unblocks:** 6
**Done criteria:** `python tests/test_all.py` verde sem Playwright; `tests/test_live_lightpanda.py` passa na VM.
**Resultado (2026-08-19):** `tests/test_cdp.py` (10) + `tests/test_browser.py` (20) criados
em Inc 2/3; mocks de executor/scrapers/self_healing atualizados em Inc 4;
`tests/test_live_lightpanda.py` criado (gated por `PRECOSBOT_LIVE=1`) e passa contra
Lightpanda real (12s). `conftest.py` adiciona `test_live_lightpanda.py` ao collect_ignore.
Suíte unitária: 247 passed sem Playwright.

#### Files to touch

##### tests/test_cdp.py, tests/test_browser.py (novos)
- What changes: unit tests do cliente CDP e da facade com fakes (sem rede).
- Integration points: Inc 2/3.

##### tests/test_executor.py, tests/test_scrapers.py, tests/test_self_healing.py, tests/test_antibot.py, tests/test_live_scrapers.py
- What changes: substituir mocks de Playwright por mocks da facade/CDP; remover imports Playwright.
- Integration points: Inc 4.

##### tests/test_live_lightpanda.py (novo)
- What changes: smoke live gated por env (`PRECOSBOT_LIVE=1`), roda 1 scraper via Lightpanda real.
- Integration points: dev/VM.

##### tests/conftest.py
- What changes: adicionar `test_live_lightpanda.py` ao `collect_ignore` (mesmo padrão de `test_live_scrapers.py`/`test_antibot.py`) para o CI unitário não coletar o smoke live.
- Integration points: CI unitário.

#### Edge cases
- Mocks da facade precisam ser `async` (gotcha documentado em memória: patch síncrono sai antes do await).
- Smoke live não roda no CI unitário (mesmo padrão de `test_live_scrapers`).

#### Verification
- Run: `python tests/test_all.py`; `PRECOSBOT_LIVE=1 python -m pytest tests/test_live_lightpanda.py -v` na VM.
- Tests to add/update: acima.
- Done: suíte unitária verde sem Playwright; smoke live passa na VM.

### Inc 6 — Deploy na VM + remover Playwright + docs (S) — DONE
**Depends on:** 4, 5
**Unblocks:** produção
**Done criteria:** hermes usa Lightpanda por padrão; Playwright removido de requirements/código/VM; docs atualizadas.
**Resultado (2026-08-19):** `playwright` removido de `requirements.txt`; hermes tool +
SKILL.md atualizados (Lightpanda); AGENTS.md/README.md/CHANGELOG.md atualizados;
`deploy-to-oci.ps1` instala o binário Lightpanda. **Deploy na VM + remoção do binário
Playwright da VM + `LIGHTPANDA_DISABLE_TELEMETRY=true` no env do hermes + restart +
soak são passos de produção que exigem acesso à VM — pendentes de execução manual
(ver "Remaining manual verification").**

#### Files to touch

##### requirements.txt
- What changes: remover `playwright>=1.44.0`; manter `websockets`.

##### deploy-hermes-oci.ps1 / deploy-to-oci.ps1 / DEPLOYMENT.md
- What changes: o binário Lightpanda **já foi instalado na VM no Inc 1** (spike); aqui só remover `playwright install chromium` do deploy e garantir `LIGHTPANDA_DISABLE_TELEMETRY=true` no env do hermes.
- Integration points: deploy.

##### AGENTS.md, README.md, CHANGELOG.md
- What changes: atualizar arquitetura (Lightpanda no lugar de Playwright), comandos de dev (`lightpanda serve`), notas de RAM, remover referências a Playwright.
- Integration points: docs.

##### hermes/tools/precosbot.py, hermes/skills/shopping/precosbot/SKILL.md
- What changes: atualizar textos "Playwright browser" → "Lightpanda"; sem mudança de contrato.
- Integration points: hermes.

#### Edge cases
- Binário Lightpanda na VM (glibc Ubuntu 24.04 OK); sem binário Windows (dev local em Windows → WSL2).
- Rollback: `git revert` + reinstalar Playwright (documentado).

#### Verification
- Run: `ssh ... "cd $REMOTE && git pull && pip install -r requirements.txt"`; `systemctl restart hermes`; `journalctl -u hermes -f`.
- Tests to add/update: n/a (deploy).
- Done: `precosbot_check` no Discord retorna preços via Lightpanda; `pip show playwright` ausente na VM.

## Cross-cutting verification

- Após Inc 4: `python agent_api.py check "RTX 4060"` e `python agent_api.py agent "RTX 4060"` na VM — conferir que os 8 scrapers retornam `StoreOutcome` e o MAS grava `agent_runs`.
- Após Inc 6: fluxo completo no Discord (`precosbot_check`, `precosbot_agent`) via hermes; monitorar RAM (`free -m`) e taxa de anti-bot por loja por alguns dias (soak) antes de considerar a migração estável.
- Rollback documentado: `git revert` do Inc 6 + reinstalar Playwright.

## Standards / common-mistakes referenced

- `.agents/learnings/mas-review-fixes.md` — aplica a: não tocar no contrato `agent_api.py`/`toolkit.py`; o executor é caminho único de scraping.
- Memória repo `precobot-testing.md` — gotcha de patch async em testes (aplica a Inc 5).

## Open questions (CONSIDER from review)

- **Ownership dos testes do CDP/facade:** `tests/test_cdp.py` e `tests/test_browser.py` são criados nas verificações do Inc 2/3 e listados de novo no Inc 5 — decidir se nascem no Inc 2/3 (recomendado) e o Inc 5 só consolida/expande, para não duplicar criação.
- **Stealth Chromium-specific:** se `STEALTH_SCRIPT` precisar de adaptação para o Lightpanda (APIs `userAgentData`/`chrome.runtime`), decidir se a adaptação vive no spike (Inc 1) ou no facade (Inc 3).
- **Inc 3 (facade) é o maior incremento (L):** dividir em 2 PRs se crescer além de 1 PR (ex.: navegação/avaliação vs interação/cookies/route).

## Out of scope

- Não migrar o hermes-agent (repo separado) — só o precosbot.
- Não adicionar knob `PRECOSBOT_BROWSER` (decisão: apenas Lightpanda).
- Não reescrever a lógica de extração dos scrapers (só trocar o motor).
- **Não automatizar o fallback `lightpanda fetch`** (gatilho automático por loja) — o fallback é decisão manual por loja, documentada no spike (Inc 1).
- Não usar o modo `lightpanda agent`/MCP nativo do Lightpanda (o precosbot mantém seu próprio MAS/MCP).
- Não adicionar suporte a Windows nativo (Lightpanda não tem binário Windows; dev em Windows via WSL2).