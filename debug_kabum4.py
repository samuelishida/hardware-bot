"""Debug KaBuM — get link's immediate parent chain and its inner text."""
import asyncio, sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )
        page = await ctx.new_page()

        await page.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)

        # Get detailed parent chain for first few product links
        result = await page.evaluate("""() => {
            let links = document.querySelectorAll("a[href*='/produto/']");
            let results = [];
            for (let i = 0; i < Math.min(links.length, 5); i++) {
                let link = links[i];
                let href = link.getAttribute('href');
                let linkText = link.innerText.trim().substring(0, 150);
                
                // Walk up 3 levels and get tag+class at each level
                let chain = [];
                let el = link;
                for (let j = 0; j < 5; j++) {
                    let tag = el.tagName;
                    let cls = el.className ? el.className.substring(0, 60) : '';
                    let text = el.innerText.trim().substring(0, 80);
                    chain.push({tag, cls, textLen: el.innerText.length});
                    el = el.parentElement;
                    if (!el) break;
                }
                
                results.push({href: href?.substring(0, 80), linkText, chain});
            }
            return results;
        }""")

        for r in result:
            print(f"\nLink: {r['href']}")
            print(f"  Text: {r['linkText'][:80]}")
            for c in r['chain']:
                print(f"  <{c['tag']} class='{c['cls']}'> textLen={c['textLen']}")

        # Also look for price elements specifically near the first product link
        price_info = await page.evaluate("""() => {
            let firstLink = document.querySelector("a[href*='/produto/']");
            if (!firstLink) return null;
            
            // Get the card container (3 levels up from link)
            let card = firstLink;
            for (let i = 0; i < 3; i++) {
                if (card.parentElement) card = card.parentElement;
            }
            
            // Find all elements with R$ inside card
            let allEls = card.querySelectorAll('*');
            let priceEls = [];
            for (let el of allEls) {
                if (el.innerText && el.innerText.includes('R$') && el.children.length === 0) {
                    priceEls.push({tag: el.tagName, cls: (el.className||'').substring(0,60), text: el.innerText.trim().substring(0, 50)});
                }
            }
            
            // Also check for span elements near the link
            let siblingSpans = firstLink.parentElement?.querySelectorAll('span') || [];
            let spanInfo = Array.from(siblingSpans).map(s => ({
                cls: (s.className||'').substring(0,60),
                text: s.innerText.trim().substring(0, 50)
            }));
            
            return {priceEls, spanInfo, cardText: card.innerText.substring(0, 200)};
        }""")

        if price_info:
            print(f"\nCard text: {price_info.get('cardText', '')[:150]}")
            print(f"Price elements in card:")
            for p in price_info.get('priceEls', [])[:10]:
                print(f"  <{p['tag']} class='{p['cls']}'> {p['text']}")
            print(f"Spans near link:")
            for s in price_info.get('spanInfo', [])[:10]:
                print(f"  class='{s['cls']}' text='{s['text']}'")

        await browser.close()

asyncio.run(main())