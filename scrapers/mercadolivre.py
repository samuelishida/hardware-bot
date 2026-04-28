from __future__ import annotations
import json
import logging
import asyncio
import random
import os
from pathlib import Path
from .base import BaseScraper, ScrapeResult, STEALTH_SCRIPT, USER_AGENTS, VIEWPORTS

logger = logging.getLogger(__name__)

COOKIE_FILE = Path(__file__).parent.parent / "ml_cookies.json"

# Extra ML-specific stealth patches applied on top of base STEALTH_SCRIPT
_ML_EXTRA_STEALTH = """
Object.defineProperty(screen, 'width',  { get: () => 1920 });
Object.defineProperty(screen, 'height', { get: () => 1080 });
Object.defineProperty(screen, 'availWidth',  { get: () => 1920 });
Object.defineProperty(screen, 'availHeight', { get: () => 1040 });
Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
if (navigator.connection) {
    Object.defineProperty(navigator.connection, 'effectiveType', { get: () => '4g' });
}
if (navigator.getBattery) {
    navigator.getBattery = () => Promise.resolve({
        charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1.0,
        addEventListener: () => {}, removeEventListener: () => {},
    });
}
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
"""

_PERMISSIONS_SCRIPT = """
const _origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) => (
    p.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        _origQuery(p)
);
"""


class MercadoLivreScraper(BaseScraper):
    store_id = "mercadolivre"

    def __init__(self, browser=None, search_term: str = None):
        super().__init__(browser)
        self.search_term = search_term

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def scrape(self) -> ScrapeResult:
        await asyncio.sleep(random.uniform(1.5, 3.5))
        return await self._scrape_via_browser()

    # ------------------------------------------------------------------
    # Cookie helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_cookies() -> list | None:
        if COOKIE_FILE.exists():
            try:
                return json.loads(COOKIE_FILE.read_text())
            except Exception:
                pass
        return None

    @staticmethod
    async def _save_cookies(context) -> None:
        try:
            cookies = await context.cookies()
            COOKIE_FILE.write_text(json.dumps(cookies))
            logger.info("[mercadolivre] Cookies salvos em ml_cookies.json")
        except Exception as e:
            logger.warning(f"[mercadolivre] Falha ao salvar cookies: {e}")

    # ------------------------------------------------------------------
    # Auto-login helper
    # ------------------------------------------------------------------

    @staticmethod
    async def _try_login(page, context) -> bool:
        """Attempt to log in with ML_EMAIL / ML_PASSWORD from environment."""
        email = os.getenv("ML_EMAIL", "").strip()
        password = os.getenv("ML_PASSWORD", "").strip()
        if not email or not password:
            return False

        try:
            for sel in ("button:has-text('Já tenho conta')", "a:has-text('Já tenho conta')"):
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    await page.wait_for_timeout(random.randint(1500, 2500))
                    break

            email_input = await page.wait_for_selector(
                "input[type='email'], input[name='user_id'], input[id*='email']",
                timeout=8000,
            )
            await email_input.fill(email)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(random.randint(1500, 2500))

            pass_input = await page.wait_for_selector("input[type='password']", timeout=8000)
            await pass_input.fill(password)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(random.randint(2500, 4000))

            # Save cookies so subsequent runs skip login
            await MercadoLivreScraper._save_cookies(context)
            logger.info("[mercadolivre] Login realizado com sucesso.")
            return True

        except Exception as e:
            logger.warning(f"[mercadolivre] Login automático falhou: {e}")
            return False

    # ------------------------------------------------------------------
    # Browser fallback
    # ------------------------------------------------------------------

    async def _scrape_via_browser(self) -> ScrapeResult:
        result = await self._browser_attempt()
        if result is not None:
            return result
        logger.warning("[mercadolivre] Browser tentativa 1 falhou, tentando novamente...")
        await asyncio.sleep(random.uniform(2.0, 4.0))
        result = await self._browser_attempt()
        if result is not None:
            return result
        return ScrapeResult(self.store_id, None, False, "Erro", None)

    async def _browser_attempt(self) -> ScrapeResult | None:
        from playwright.async_api import async_playwright

        ua = random.choice(USER_AGENTS)
        vp = random.choice(VIEWPORTS)
        pw = None
        browser = None
        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--window-size=1920,1080",
                ],
            )

            context = await browser.new_context(
                user_agent=ua,
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport=vp,
                device_scale_factor=1,
                color_scheme="light",
                reduced_motion="no-preference",
                extra_http_headers={
                    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                    "Sec-CH-UA-Mobile": "?0",
                    "Sec-CH-UA-Platform": '"Windows"',
                },
            )

            await context.add_init_script(STEALTH_SCRIPT)
            await context.add_init_script(_ML_EXTRA_STEALTH)
            await context.add_init_script(_PERMISSIONS_SCRIPT)

            # Inject saved session cookies before first navigation
            saved = self._load_cookies()
            if saved:
                try:
                    await context.add_cookies(saved)
                    logger.info("[mercadolivre] Cookies carregados do arquivo.")
                except Exception as e:
                    logger.warning(f"[mercadolivre] Falha ao injetar cookies: {e}")

            page = await context.new_page()

            # Block heavy resources
            async def _route(route):
                if route.request.resource_type in ("image", "media", "font"):
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", _route)

            search_url = f"https://lista.mercadolivre.com.br/{self.search_term}"
            await page.goto(search_url, wait_until="commit", timeout=60_000)
            await page.wait_for_timeout(random.randint(3000, 5000))

            # Handle cookie consent banner
            await self._dismiss_cookie_banner(page)

            # Detect and handle login wall
            if "account-verification" in page.url:
                logger.info("[mercadolivre] Login wall detectada, tentando contornar...")
                logged_in = await self._try_login(page, context)
                if not logged_in:
                    logger.warning(
                        "[mercadolivre] Sem credenciais ML. "
                        "Defina ML_EMAIL e ML_PASSWORD no .env ou exporte ml_cookies.json."
                    )
                    return None

                # After login, navigate to the search page
                await page.goto(search_url, wait_until="commit", timeout=60_000)
                await page.wait_for_timeout(random.randint(3000, 5000))

            # Still on login wall after login attempt?
            if "account-verification" in page.url:
                return None

            # Wait for product cards
            try:
                await page.wait_for_selector(
                    "li.ui-search-layout__item, div.poly-card, div.andes-card",
                    timeout=18_000,
                )
            except Exception:
                await page.wait_for_timeout(random.randint(5000, 8000))

            # Human-like scroll to trigger lazy loading
            await self._human_scroll(page)

            # Save fresh cookies after successful page load
            await self._save_cookies(context)

            products = await page.evaluate(
                """(searchTerm) => {
                const keywords = searchTerm.replace(/-/g, ' ').toLowerCase().split(' ').filter(Boolean);
                const sigKws = keywords.filter(kw => kw.length >= 2);
                const matchKws = sigKws.length > 0 ? sigKws : keywords;
                const modelKws = keywords.filter(kw => /[0-9]/.test(kw));
                const SYSTEM_EXCL = ['pc gamer','pc gaming','computador gamer','computador completo','desktop gamer','workstation','pc completo','notebook','laptop','usado','seminovo'];

                const selectors = [
                    'li.ui-search-layout__item',
                    'div.poly-card',
                    'div.ui-search-result__content',
                    'div.andes-card',
                    'article',
                ];

                let cards = [];
                for (const sel of selectors) {
                    const found = document.querySelectorAll(sel);
                    if (found.length >= 3) { cards = Array.from(found); break; }
                }

                const results = [];
                for (const card of cards) {
                    const text = card.innerText.toLowerCase();
                    // Exclude pre-built systems
                    if (SYSTEM_EXCL.some(p => text.includes(p))) continue;
                    // ALL model keywords must match — prevents "ryzen 5" matching a motherboard
                    if (modelKws.length > 0 && !modelKws.every(kw => text.includes(kw))) continue;
                    // All significant keywords must match (prevents "4060" alone matching accessories)
                    if (matchKws.length > 0 && !matchKws.every(kw => text.includes(kw))) continue;

                    // Use specific price element — avoids picking up installment amounts
                    let price = null;
                    const mainPriceEl = card.querySelector(
                        '.poly-price__current, [class*="price-tag-amount"], .ui-search-price__second-line'
                    );
                    const priceSource = mainPriceEl || card;
                    const fractionEl = priceSource.querySelector(
                        '.andes-money-amount__fraction, [class*="fraction"]'
                    );
                    const centsEl = priceSource.querySelector(
                        '.andes-money-amount__cents:not([class*="installment"]):not([class*="phrase"])'
                    );
                    if (fractionEl) {
                        // Brazilian thousands separator: "3.589" → 3589
                        const frac = fractionEl.innerText.replace(/\\./g, '').trim();
                        const cents = centsEl ? centsEl.innerText.trim().padEnd(2, '0').substring(0, 2) : '00';
                        const val = parseFloat(frac + '.' + cents);
                        if (!isNaN(val) && val > 100) price = val;
                    }
                    // Fallback: first R$ value in the card text that is > 300 (skips accessory prices)
                    if (price === null) {
                        const m = text.match(/r\\$\\s*([\\d.]+)(?:,([\\d]{2}))?/);
                        if (m) {
                            const val = parseFloat(m[1].replace(/\\./g, '') + '.' + (m[2] || '00'));
                            if (!isNaN(val) && val > 300) price = val;
                        }
                    }

                    const link = card.querySelector(
                        'a[href*="mercadolivre.com"], a[href*="produto.mercadolivre"]'
                    );
                    const url = link ? link.href : null;
                    const titleEl = card.querySelector(
                        'h2, h3, [class*=title], [class*=Title], [class*=poly-component__title]'
                    );
                    const title = titleEl ? titleEl.innerText.trim() : '';

                    // Relevance score: more keywords in title = better match
                    const titleLower = title.toLowerCase();
                    const matchCount = keywords.filter(kw => titleLower.includes(kw)).length;

                    const available = price !== null
                        && !text.includes('sem estoque')
                        && !text.includes('esgotado');

                    if (price !== null) results.push({ price, available, url, title: title.substring(0, 200), matchCount });
                }
                // Sort by relevance (most keywords matched in title), then by price
                results.sort((a, b) => b.matchCount - a.matchCount || a.price - b.price);
                return results;
            }""",
                self.search_term,
            )

            if not products:
                logger.info("[mercadolivre] Browser: nenhum resultado.")
                return None

            # Results sorted by relevance (matchCount) then price — pick first available
            for p in products:
                if p["available"] and p["price"] is not None:
                    return ScrapeResult(
                        self.store_id, p["price"], True, "Em estoque", p["url"],
                    )

            p = products[0]
            return ScrapeResult(
                self.store_id, p["price"], p["available"],
                "Em estoque" if p["available"] else "Esgotado", p["url"],
            )

        except Exception as e:
            logger.error(f"[mercadolivre] Browser attempt falhou: {e}")
            return None
        finally:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()

    async def _dismiss_cookie_banner(self, page) -> None:
        for sel in (
            "button[data-testid='cookie-consent-banner-accept']",
            "button:has-text('Aceitar cookies')",
            "button.andes-button:has-text('Aceitar')",
        ):
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    await page.wait_for_timeout(random.randint(500, 1000))
                    return
            except Exception:
                pass

    async def _human_scroll(self, page) -> None:
        try:
            for _ in range(random.randint(2, 4)):
                await page.mouse.wheel(0, random.randint(200, 500))
                await page.wait_for_timeout(random.randint(300, 700))
        except Exception:
            pass
