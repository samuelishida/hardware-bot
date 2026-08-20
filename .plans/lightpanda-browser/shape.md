# Shape — Migração para Lightpanda

Decisões de modelagem e alternativas consideradas (não fazem parte do `plan.md` —
só o caminho escolhido entra no plano).

## Alternativas de integração consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Cliente CDP próprio em Python** (`core/cdp.py` + facade) | 100% Python; controle total; sem runtime extra; testável | Mais código; CDP do Lightpanda é Beta | **Escolhido** |
| `lightpanda fetch --dump html` por scraper | Muito simples; alinha com padrão SSR (OLX/Enjoei `__NEXT_DATA__`); memória mínima | Não cobre JS complexo (lógica de preço do KaBuM), login (ML), scroll; reescreveria scrapers como parsers HTML | Rejeitado (mas mantido como **fallback por loja** se o CDP não renderizar) |
| Playwright `connect_over_cdp` → Lightpanda | Barato se funcionar; scrapers inalterados | Mantém Playwright (contraria decisão do usuário); CDP do Lightpanda não é Chromium — risco alto de quebrar | Rejeitado |
| Puppeteer via Node | Cliente documentado do Lightpanda | Adiciona runtime Node na VM de 1 GB; projeto é Python | Rejeitado |
| Modo `lightpanda agent` / MCP nativo | Zero código de scraping | Fora do escopo (precosbot mantém seu próprio MAS/MCP); não é scraping determinístico | Rejeitado |

## Decisões de modelagem

- **Facade espelha a API Playwright** (não uma API nova) → churn mecânico nos scrapers,
  menor risco de regressão de lógica de extração.
- **1 instância `lightpanda serve` compartilhada** → respeita a RAM da VM (espelha o
  design atual de 1 browser compartilhado).
- **Remoção do Playwright por último (Inc 6)** → rollback via `git revert` até o
  Lightpanda estar validado em produção.
- **Spike (Inc 1) é gate de arquitetura** → valida a superfície CDP (evaluate com
  `returnByValue`, init scripts, interceptação, keyboard/mouse, cookies, `commit` vs
  `domcontentloaded`) antes de comprometer o facade.

## Riscos que o plano aceita (resumo)

- CDP do Lightpanda incompleto → workarounds + `lightpanda fetch` fallback.
- Antibot maior (fingerprint não-Chromium) → stealth adaptado + cookies ML + re-scrape.
- Estabilidade Beta → timeout/restart/log.
- `:has-text()` (ML) → tradução para query JS por `textContent` (Inc 3).