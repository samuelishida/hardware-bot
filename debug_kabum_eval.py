"""Test the actual KaBuM scraper evaluate logic."""
import asyncio, sys, json
sys.path.insert(0, "/home/ubuntu/precosbot")
from playwright.async_api import async_playwright
from scrapers.kabum import KabumScraper

SEARCH_TERM = "rtx-4060"

EVALUATE_JS = """(searchTerm) => {
    const keywords = searchTerm.replace(/-/g, ' ').split(' ');
    const modelKeywords = keywords.filter(kw => /[a-zA-Z]/.test(kw) && /[0-9]/.test(kw));

    // Each product card is a <main> container with bare text nodes for price
    // Match main elements containing product links (stable structure)
    const cards = document.querySelectorAll("main[class*='sc-']");
    const results = [];

    for (const card of cards) {
        const text = card.innerText;
        const link = card.querySelector("a[href*='/produto/']");
        if (!link) continue;

        const href = link.getAttribute('href') || '';
        const linkText = link.innerText.toLowerCase();
        const slug = href.replace('/produto/', '').replace(/\\d+\\//, '').toLowerCase();

        // Filter by keywords (match in linkText or URL slug)
        if (!keywords.some(kw => linkText.includes(kw) || slug.includes(kw))) continue;
        if (modelKeywords.length > 0 && !modelKeywords.some(kw => linkText.includes(kw) || slug.includes(kw))) continue;

        // Extract price from card's innerText (bare text node pattern: R$ 1.699,99)
        const priceMatch = text.match(/R$\\s*([\\d.]+,\\d{2})/);
        let price = null;
        if (priceMatch) {
            const raw = priceMatch[1].replace(/[.]/g, '').replace(',', '.');
            price = parseFloat(raw);
        }

        const available = price !== null && !text.includes('indisponível');
        results.push({
            href,
            price,
            available,
            name: (link.querySelector('div')?.innerText || slug.replace(/-/g, ' ')).trim().substring(0, 200)
        });
    }
    return results;
}"""

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"])
        scraper = KabumScraper(browser=browser, search_term=SEARCH_TERM)
        page = await scraper._new_page()
        await page.goto(scraper.search_url, wait_until="commit", timeout=30000)
        await page.wait_for_timeout(12000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)

        products = await page.evaluate(EVALUATE_JS, SEARCH_TERM)
        print(f"Products found: {len(products)}")
        for p in products[:5]:
            print(f"  price={p['price']} available={p['available']} href={p['href'][:50]} name={p['name'][:40]}")

        await browser.close()

asyncio.run(main())