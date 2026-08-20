# Spike: CDP do Lightpanda — capacidades validadas

**Data:** 2026-08-19 · **Binário:** `lightpanda-x86_64-linux` v1.0.0-nightly.8737
**Probe:** `scripts/lightpanda_probe.py` (protótipo descartável, Inc 1)

## Resumo

O CDP do Lightpanda cobre **toda** a superfície que os scrapers do precosbot
precisam. O spike validou cada capacidade contra o binário real e scrapeou KaBuM
ponta-a-ponta via CDP (5 produtos encontrados). **A migração é viável.**

## Descoberta crítica: fluxo de setup obrigatório

O CDP do Lightpanda **não** aceita comandos de página antes de um setup explícito.
Sem ele, todo comando falha com `BrowserContextNotLoaded`. O fluxo obrigatório é:

```
1. Target.createBrowserContext  → browserContextId
2. Target.createTarget {url, browserContextId}  → targetId
3. Target.attachToTarget {targetId, flatten:true}  → sessionId
4. TODOS os comandos seguintes DEVEM incluir "sessionId" no payload
```

**Restrição de RAM/design:** Lightpanda suporta **APENAS 1 browser context e 1
página por vez** (`Target.createBrowserContext` com 2º → erro
`Cannot have more than one browser context at a time`). Isso **confirma** o design
do plano: 1 instância `lightpanda serve` compartilhada, scraping sequencial. O
facade `Context`/`Page` deve criar o browser context + target + attach no
`new_context()` e reusar a mesma `sessionId` para todos os comandos daquela página.

## Tabela de capacidades CDP

| Capacidade | Método CDP | Suportado | Nota |
|---|---|---|---|
| Setup browser context | `Target.createBrowserContext` | ✅ | 1 por conexão |
| Criar página | `Target.createTarget` | ✅ | 1 página por vez |
| Attach (sessionId) | `Target.attachToTarget` | ✅ | `flatten:true`; sessionId obrigatório depois |
| Avaliar JS (objetos aninhados) | `Runtime.evaluate` + `returnByValue` | ✅ | lista de dicts serializa corretamente |
| Avaliar função + arg | `Runtime.evaluate` `(${js})(${arg})` | ✅ | padrão de TODOS os scrapers |
| Navegar | `Page.navigate` | ✅ | evento `Page.frameNavigated` |
| Query seletor | `DOM.getDocument` → `DOM.querySelector` | ✅ | `getDocument` registra o root nodeId |
| Stealth init script | `Page.addScriptToEvaluateOnNewDocument` | ✅ | `STEALTH_SCRIPT` não lança |
| Cookies | `Network.getCookies` / `setCookies` | ✅ | `setCookies` usa `cookies:[{...}]` |
| Interceptação de rede | `Network.setBlockedURLs` | ✅ | **param é `urlPatterns`** (não `urls`): `[{urlPattern, block}]` |
| Teclado | `Input.dispatchKeyEvent` | ✅ | |
| Mouse/wheel | `Input.dispatchMouseEvent` (`mouseWheel`) | ✅ | |
| Screenshot | `Page.captureScreenshot` | ✅ | |
| Stealth não lança | `Runtime.evaluate` | ✅ | `navigator.userAgentData`/`window.chrome` OK |

## Workarounds / decisões do spike

- **`Network.setBlockedURLs` usa `urlPatterns`** (não `urls` como no Chrome). O
  facade `Route`/interceptação do ML deve enviar `urlPatterns: [{urlPattern, block}]`.
- **`DOM.querySelector` requer `DOM.getDocument` antes** para registrar o root
  nodeId. O facade `query_selector` deve chamar `getDocument` (cachear o rootId) e
  depois `querySelector`.
- **`networkidle` (OLX):** o Lightpanda emite eventos de lifecycle `networkIdle`
  (release 0.3.5). O facade pode mapear `wait_until="networkidle"` para esperar o
  evento `Page.lifecycleEvent` com `name="networkIdle"`; fallback: espera fixa.
- **`commit` vs `domcontentloaded`:** `Page.frameNavigated` dispara na navegação
  (commit); `Page.loadEventFired` no load. O facade mapeia `commit`→`frameNavigated`,
  `domcontentloaded`→`frameNavigated`+pequena espera, `load`→`loadEventFired`.
- **`:has-text()` (ML):** `DOM.querySelector` não entende `:has-text()`. O facade
  traduz para query JS por `textContent` case-insensitive (ver Inc 3).
- **Stealth:** `Page.addScriptToEvaluateOnNewDocument` funciona; `STEALTH_SCRIPT`
  do precosbot roda sem lançar no Lightpanda (APIs Chromium-only são no-ops).

## Fallback `lightpanda fetch` (decisão manual por loja)

Se uma loja não renderizar via CDP (antibot/JS complexo), o fallback é **manual e
por loja**, documentado aqui (automação fora de escopo):

```bash
LIGHTPANDA_DISABLE_TELEMETRY=true lightpanda fetch --dump html \
  --wait-until domcontentloaded --wait-ms 5000 \
  "https://www.kabum.com.br/busca/rtx-4060" > page.html
```

Gatilho: quando o smoke test (Inc 5) mostrar que uma loja específica falha
consistentemente via CDP, decidir manualmente se aquela loja usa `lightpanda fetch`
(reescrevendo o scraper como parser HTML) ou se mantém CDP com workaround.

## Instalação do binário (VM OCI, Ubuntu 24.04)

```bash
# glibc Ubuntu 24.04 OK (sem binário Windows; dev em Windows via WSL2)
curl -sL -o /usr/local/bin/lightpanda \
  https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux
chmod +x /usr/local/bin/lightpanda
lightpanda version
```

- **NÃO** usar `--obey-robots` (o Playwright atual não obedece robots.txt).
- `LIGHTPANDA_DISABLE_TELEMETRY=true` no env do hermes.

## Edge cases validados

- `lightpanda serve` sobe com `--host 127.0.0.1 --port 9222`; `/json/version`
  retorna `webSocketDebuggerUrl: ws://127.0.0.1:9222/`.
- Telemetria desabilitada via env var (sem flag CLI).
- KaBuM hidrata React async → `Page.navigate` + espera ~8s antes de `evaluate`.

## Alimenta Inc 2/3

- **Inc 2 (`core/cdp.py`):** `CDPClient.send` deve aceitar `sessionId` no payload;
  `wait_event` para `Page.frameNavigated`/`Page.lifecycleEvent`.
- **Inc 3 (`core/browser.py`):** `Context.new_page()` = createBrowserContext +
  createTarget + attachToTarget; `Page` guarda a `sessionId`; `query_selector`
  chama `getDocument`+`querySelector`; `route` usa `Network.setBlockedURLs` com
  `urlPatterns`; `wait_until` mapeado conforme tabela acima.
