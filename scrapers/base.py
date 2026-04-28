from __future__ import annotations
import random
import asyncio
from dataclasses import dataclass
from typing import Optional

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
]

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        { name: 'Native Client', filename: 'internal-nacl-plugin' },
    ],
});
Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'userAgentData', {
    get: () => ({
        mobile: false,
        platform: 'Windows',
        brands: [
            { brand: 'Chromium', version: '131' },
            { brand: 'Not_A Brand', version: '24' }
        ]
    })
});
window.chrome = window.chrome || {};
window.chrome.runtime = {
    id: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    connect: () => ({}),
    sendMessage: () => {},
    getURL: () => '',
    getManifest: () => ({ version: '1.0', name: 'Google Chrome' }),
};
Element.prototype._element_querySelector = Element.prototype.querySelector;
Element.prototype._element_querySelectorAll = Element.prototype.querySelectorAll;
"""


@dataclass
class ScrapeResult:
    store_id: str
    price: Optional[float]
    available: bool
    stock_label: Optional[str]
    url: Optional[str]


class BaseScraper:
    store_id = "base"

    def __init__(self, browser=None):
        self.browser = browser

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def _new_page(self, retry: int = 2):
        """Create new page with retry for browser stability."""
        if self.browser is None:
            raise RuntimeError(f"[{self.store_id}] Browser não inicializado")

        ua = random.choice(USER_AGENTS)
        vp = random.choice(VIEWPORTS)

        try:
            context = await self.browser.new_context(
                user_agent=ua,
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport=vp,
                device_scale_factor=1,
                color_scheme="light",
                reduced_motion="no-preference",
            )

            await context.add_init_script(STEALTH_SCRIPT)
            await context.add_init_script("""
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)

            page = await context.new_page()

            await page.set_extra_http_headers({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            })

            return page
        except Exception as e:
            if retry > 0:
                await asyncio.sleep(1)
                return await self._new_page(retry - 1)
            raise

    def _parse_price(self, raw_price: str | None) -> Optional[float]:
        if not raw_price:
            return None

        value = raw_price.strip().lower()
        for token in ("r$", "à vista", "no pix", "pix", "por", "cada"):
            value = value.replace(token, "")

        filtered = "".join(ch for ch in value if ch.isdigit() or ch in ",.")
        if not filtered:
            return None

        if "," in filtered and "." in filtered:
            last_comma = filtered.rfind(",")
            last_dot = filtered.rfind(".")
            if last_comma > last_dot:
                filtered = filtered.replace(".", "").replace(",", ".")
            else:
                filtered = filtered.replace(",", "")
        elif "," in filtered:
            filtered = filtered.replace(",", ".")

        try:
            return float(filtered)
        except ValueError:
            return None

    async def scrape(self) -> ScrapeResult:
        raise NotImplementedError
