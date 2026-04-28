# 🤖 PreçoBot — Monitor de Preços de Hardware BR

Bot de Discord que monitora preços e disponibilidade de produtos de hardware nas principais lojas brasileiras. Suporta **qualquer produto** com busca dinâmica, monitoramento por canal e alertas personalizados.

---

## Funcionalidades

- **Busca dinâmica** — `/buscar RTX 4060 Ti` busca qualquer produto em 5 lojas
- **Monitoramento contínuo** — `/monitorar iPhone 15 Pro` faz varreduras automáticas a cada 15 min
- **Alerta de queda de preço** — notifica o canal quando o preço cai ≥ 5%
- **Alerta de restoque** — avisa quando o produto volta ao estoque
- **Alerta pessoal por DM** — `/alerta <produto> <valor>` recebe DM quando o preço atinge o alvo
- **Histórico de preços** — mínimo, máximo e média por loja nos últimos N dias
- **Multi-produto** — monitore vários produtos simultaneamente em canais diferentes

---

## Lojas monitoradas

| Loja | Método | Observação |
|---|---|---|
| KaBuM! | Playwright (browser) | Seletores: `article.productCard` |
| Pichau | Playwright (browser) | React/MUI — aguarda `networkidle` |
| Terabyte Shop | Playwright (browser) | Seletores: `div.pbox` |
| Mercado Livre | API REST pública + Playwright fallback | Fallback em caso de 403 |
| Amazon BR | Playwright (browser) | Anti-bot: delay aleatório + detecção de CAPTCHA |

---

## Comandos

| Comando | Descrição |
|---|---|
| `/precos [produto]` | Preços atuais (filtra por produto se especificado) |
| `/buscar <produto>` | Busca preços de qualquer produto agora |
| `/monitorar <produto>` | Começa a monitorar um produto neste canal |
| `/parar <produto>` | Para de monitorar um produto |
| `/lista` | Lista produtos monitorados neste canal |
| `/alerta <valor> [produto]` | Configura alerta pessoal por DM |
| `/alerta cancelar [produto]` | Remove alerta ativo |
| `/historico [dias]` | Resumo de preços dos últimos N dias (padrão: 30) |
| `/status` | Status do bot e lojas |
| `/ajuda` | Lista de comandos |

---

## Pré-requisitos

- Python 3.10+
- Conta de bot no [Discord Developer Portal](https://discord.com/developers/applications)
- Permissões do bot: `Send Messages`, `Embed Links`, `Use Slash Commands`, `Send Messages in Threads`

---

## Instalação

```bash
# 1. Clone o projeto
git clone https://github.com/seu-usuario/precobot.git
cd precobot

# 2. Instale as dependências Python
pip install -r requirements.txt

# 3. Instale o Chromium para o Playwright
playwright install chromium

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env com seu editor preferido
```

---

## Configuração

Copie `.env.example` para `.env` e preencha:

```env
# Token do bot (Discord Developer Portal → Bot → Token)
DISCORD_TOKEN=cole_seu_token_aqui

# ID do servidor Discord
DISCORD_GUILD_ID=123456789012345678

# ID do canal onde os alertas automáticos serão enviados
ALERT_CHANNEL_ID=123456789012345678

# Intervalo de varredura em minutos (padrão: 15)
SCRAPE_INTERVAL_MINUTES=15

# Percentual mínimo de queda para disparar alerta (padrão: 5%)
PRICE_DROP_THRESHOLD_PCT=5
```

> **Como obter os IDs:** Ative o Modo Desenvolvedor no Discord (`Configurações → Avançado → Modo Desenvolvedor`), depois clique com o botão direito no servidor ou canal e selecione **Copiar ID**.

---

## Como rodar

```bash
python main.py
```

O bot irá:
1. Criar o banco de dados `precobot.db` automaticamente
2. Sincronizar os slash commands no servidor
3. Iniciar o scheduler de varredura
4. Aparecer como **online** no servidor com status *"Assistindo preços 🔍"*

---

## Estrutura do projeto

```
precobot/
├── main.py                     # Entry point — orquestra bot + scheduler
├── config.py                   # Variáveis de ambiente e constantes globais
├── requirements.txt
├── .env.example
│
├── bot/
│   ├── cog_monitor.py          # Slash commands organizados por grupo
│   └── embeds.py               # Fábrica de Discord Embeds
│
├── core/
│   └── product_manager.py      # Normalização de busca, geração de URLs
│
├── db/
│   ├── database.py             # Setup SQLite assíncrono (aiosqlite)
│   ├── queries.py              # Camada de compatibilidade (re-exports)
│   └── repositories/           # Padrão Repository por entidade
│       ├── price_repo.py       # Operações de preço
│       ├── alert_repo.py       # Operações de alerta
│       └── tracking_repo.py    # Operações de monitoramento
│
├── scheduler/
│   ├── jobs.py                 # Orquestração da varredura periódica
│   ├── executor.py             # Motor de execução de scrapers
│   └── dispatcher.py           # Disparo de alertas (canal + DM)
│
├── scrapers/
│   ├── base.py                 # Classe abstrata BaseScraper + ScrapeResult
│   ├── kabum.py                # KaBuM (Playwright)
│   ├── pichau.py               # Pichau (Playwright + networkidle)
│   ├── terabyte.py             # Terabyte Shop (Playwright)
│   ├── mercadolivre.py         # Mercado Livre (httpx + Playwright fallback)
│   └── amazon.py               # Amazon BR (Playwright + anti-bot)
│
├── utils/
│   └── formatters.py           # Utilitários de formatação compartilhados
│
└── tests/                      # Testes unitários
    ├── test_all.py             # Validação rápida
    ├── test_formatters.py      # Testes de formatação
    ├── test_product_manager.py # Testes do ProductManager
    ├── test_repositories.py    # Testes dos repositórios
    ├── test_executor.py        # Testes do executor
    ├── test_embeds.py          # Testes dos embeds
    └── test_integration.py     # Testes de integração
```

---

## Banco de dados

SQLite criado automaticamente em `precobot.db` com três tabelas:

### `price_history`
Um registro por varredura por loja.

| Coluna | Tipo | Descrição |
|---|---|---|
| `store_id` | TEXT | Identificador da loja (`kabum`, `pichau`, etc.) |
| `product_name` | TEXT | Nome do produto (ex: `AMD Ryzen 5 5700X3D`) |
| `search_term` | TEXT | Termo normalizado (ex: `ryzen-5-5700x3d`) |
| `price` | REAL | Preço em R$ (`NULL` se indisponível) |
| `available` | INTEGER | `1` = em estoque, `0` = fora |
| `stock_label` | TEXT | Texto descritivo do estoque |
| `url` | TEXT | URL direta do produto |
| `scraped_at` | TEXT | Timestamp da varredura |

### `user_alerts`
Alertas de preço por usuário Discord.

| Coluna | Tipo | Descrição |
|---|---|---|
| `discord_user` | TEXT | ID do usuário Discord |
| `product_name` | TEXT | Nome do produto |
| `search_term` | TEXT | Termo normalizado |
| `target_price` | REAL | Dispara quando `price <= target_price` |
| `active` | INTEGER | `1` = ativo, `0` = disparado/cancelado |

### `tracked_products`
Produtos sendo monitorados por canal.

| Coluna | Tipo | Descrição |
|---|---|---|
| `channel_id` | TEXT | ID do canal Discord |
| `product_name` | TEXT | Nome do produto |
| `search_term` | TEXT | Termo normalizado |
| `active` | INTEGER | `1` = ativo, `0` = removido |

---

## Como adicionar uma nova loja

**1.** Crie `scrapers/novaloja.py` herdando de `BaseScraper`:

```python
from .base import BaseScraper, ScrapeResult

class NovaLojaScraper(BaseScraper):
    store_id = "novaloja"

    async def scrape(self) -> ScrapeResult:
        page = await self._new_page()
        await page.goto(f"https://novaloja.com.br/busca?q={self.search_term}")
        # ... lógica de scraping
        return ScrapeResult(
            store_id=self.store_id,
            price=preco,
            available=disponivel,
            stock_label="Em estoque",
            url=url_do_produto,
        )
```

**2.** Adicione a loja em `config.py`:

```python
STORE_URL_TEMPLATES["novaloja"]     = "https://novaloja.com.br/busca?q={query}"
STORE_DISPLAY_NAMES["novaloja"]     = "Nova Loja"
STORE_COLORS["novaloja"]            = 0xABCDEF
```

**3.** Registre o scraper em `bot/cog_monitor.py` e `scheduler/jobs.py`:

```python
from scrapers.novaloja import NovaLojaScraper
BROWSER_SCRAPERS = [..., NovaLojaScraper]   # se usar Playwright
# ou
HTTP_SCRAPERS    = [..., NovaLojaScraper]   # se usar httpx
```

---

## Testes

```bash
# Validar tudo
python tests/test_all.py

# Testes específicos
python -m pytest tests/test_formatters.py -v
python -m pytest tests/test_product_manager.py -v
python -m pytest tests/test_repositories.py -v
python -m pytest tests/test_embeds.py -v
python -m pytest tests/test_integration.py -v
```

---

## Dependências

| Pacote | Versão mínima | Uso |
|---|---|---|
| `discord.py` | 2.3.0 | Bot Discord e slash commands |
| `playwright` | 1.44.0 | Scraping com browser headless (Chromium) |
| `aiosqlite` | 0.20.0 | SQLite assíncrono |
| `apscheduler` | 3.10.0 | Scheduler de varredura periódica |
| `httpx` | 0.27.0 | HTTP assíncrono para API do Mercado Livre |
| `python-dotenv` | 1.0.0 | Leitura do arquivo `.env` |

---

## Licença

MIT
