from __future__ import annotations
import random
import re
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional


logger = logging.getLogger(__name__)


_SAFE_SELECTOR_RE = re.compile(r"^[A-Za-z0-9_#.\-\[\]='\":()>+ ,*|~^$]*$")


def is_safe_selector(selector: str) -> bool:
    """Valida um seletor CSS antes de persistir/usar (defesa contra injeção).

    Rejeita engine-prefixes do Playwright (``xpath=``, ``text=``, ``css=``, ``>>``),
    marcadores perigosos (``javascript:``, ``url(``, ``expression(``, ``@import``)
    e caracteres fora do charset CSS básico. Override inseguro → degrada para o
    default da subclass (override é otimização, nunca requisito).
    """
    s = (selector or "").strip()
    if not s or len(s) > 200:
        return False
    low = s.lower()
    if any(p in low for p in ("javascript:", "url(", "expression(", "@import", "behavior:", "//")):
        return False
    if low.startswith(("xpath=", "text=", "css=", "nth=", "has=", "role=")) or ">>" in s:
        return False
    return bool(_SAFE_SELECTOR_RE.match(s))

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
    title: Optional[str] = None


class BaseScraper:
    store_id = "base"

    # Subclasses declaram os seletores CSS por elemento, ex.: {'price': "span.price"}
    # (migrar o seletor hardcoded de cada scrape() para cá — Inc 6).
    SELECTORS: dict[str, str] = {}

    def __init__(self, browser=None):
        self.browser = browser
        # cache em memória por instância: element → override (None = sem override)
        self._selector_cache: dict[str, str | None] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def _new_page(self, retry: int = 2):
        """Create new page with retry for browser stability (facade Lightpanda)."""
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

    @staticmethod
    def _parse_price(raw_price: str | None) -> Optional[float]:
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

    async def _resolve_selector(self, element: str) -> str | None:
        """Resolve o seletor CSS de ``element`` (override self-healing > default).

        Ordem:
          1. override do ``selector_repo`` (cache em memória por instância);
          2. ``SELECTORS[element]`` (default declarado pela subclass).

        ``SELECTORS`` sem a chave e sem override → ``None`` (comportamento legado
        exato: a subclass continua usando o seletor hardcoded).

        NOTA (scaffolding): este hook e ``_on_extract_failure`` ainda não são
        chamados por nenhum scraper — a adoção de ``SELECTORS`` por subclass é
        migração pendente (Inc 6). O código é funcional e testado, mas inerte.
        """
        if element not in self._selector_cache:
            override = None
            try:
                from db.repositories.selector_repo import get_override

                row = await get_override(self.store_id, element)
                override = row["selector"] if row else None
            except Exception as e:  # DB fora → degrada para default
                logger.warning(f"[{self.store_id}] _resolve_selector({element}) DB falhou: {e}")
                override = None
            self._selector_cache[element] = override

        override = self._selector_cache[element]
        if override and is_safe_selector(override):
            return override
        if override:
            logger.warning(f"[{self.store_id}] override de seletor inseguro ignorado para '{element}'")
        return self.SELECTORS.get(element)

    async def _on_extract_failure(self, page, element: str = "price") -> None:
        """Hook chamado no caminho de falha de extração, com a ``page`` ainda aberta.

        Se o scraper adotou ``SELECTORS[element]``, aciona o self-healing (Inc 6):
        o LLM propõe um seletor, validado ao vivo e persistido como override, que é
        cacheado em ``_selector_cache`` para o ``_resolve_selector`` seguinte.
        Scrapers sem ``SELECTORS[element]`` → no-op (degradação limpa).

        NOTA (scaffolding): nenhum scraper chama este hook ainda — a adoção de
        ``SELECTORS`` por subclass é migração pendente (Inc 6).
        """
        if element not in self.SELECTORS:
            return None
        try:
            from agents.self_healing import attempt_self_heal  # lazy: evita import circular

            selector = await attempt_self_heal(self.store_id, element, page)
            if selector:
                self._selector_cache[element] = selector
        except Exception as e:
            logger.warning(f"[{self.store_id}] _on_extract_failure({element}) healing falhou: {e}")
        return None

    async def scrape(self) -> ScrapeResult:
        raise NotImplementedError
