"""Debug all stores — check what works in Playwright after full render."""
import asyncio, sys, json
from playwright.async_api import async_playwright

STEALTH_ARGS = [
    "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]

async def test_kabum(browser):
    print("\n=== KABUM ===")
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
    )
    page = await ctx.new_page()
    try:
        await page.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(10000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"Error loading: {e}")
        await ctx.close()
        return

    # Use evaluate to get structured data from rendered DOM
    data = await page.evaluate("""() => {
        let results = [];
        // Try finding product cards by looking for <a> tags with /produto/ href
        let links = document.querySelectorAll("a[href*='/produto/']");
        for (let link of links) {
            let href = link.getAttribute('href') || '';
            let text = link.innerText.trim();
            // Find price-like text inside
            let priceText = '';
            let allSpans = link.querySelectorAll('span');
            for (let s of allSpans) {
                if (s.innerText.includes('R$') || /^\\d+[.,]\\d{2}$/.test(s.innerText.trim())) {
                    priceText += s.innerText.trim() + ' | ';
                }
            }
            // Get the closest named container
            let nameText = '';
            let nameEls = link.querySelectorAll('h2, h3, span[class*="name"], span[class*="Nome"], span[class*="title"]');
            for (let n of nameEls) {
                let t = n.innerText.trim();
                if (t.length > 3) nameText += t + ' | ';
            }
            results.push({href: href.substring(0, 80), textLen: text.length, text: text.substring(0, 100), priceText: priceText.substring(0, 100), nameText: nameText.substring(0, 100)});
        }
        return results.slice(0, 5);
    }""")
    
    for i, d in enumerate(data):
        print(f"  Link {i}: href={d['href'][:60]}")
        print(f"    text({d['textLen']}): {d['text'][:80]}")
        print(f"    prices: {d['priceText']}")
        print(f"    names: {d['nameText']}")
    
    await ctx.close()

async def test_pichau(browser):
    print("\n=== PICHAU ===")
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
    )
    page = await ctx.new_page()
    try:
        await page.goto("https://www.pichau.com.br/search?q=rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(10000)
    except Exception as e:
        print(f"Error loading: {e}")
        await ctx.close()
        return

    data = await page.evaluate("""() => {
        let results = [];
        // Pichau uses div[class*=product] containers
        let products = document.querySelectorAll("div[class*=product], div[class*=Product], a[href*='/p/']");
        for (let p of products) {
            let text = p.innerText.trim().substring(0, 200);
            let href = p.getAttribute('href') || p.querySelector('a')?.getAttribute('href') || '';
            results.push({tag: p.tagName, cls: (p.className||'').substring(0, 60), text, href: href.substring(0, 80)});
        }
        
        // Also try algolia/next data
        let nd = document.getElementById('__NEXT_DATA__');
        let nextData = nd ? nd.textContent.substring(0, 200) : null;
        
        return {products: results.slice(0, 5), nextData};
    }""")
    
    print(f"  Products found: {len(data['products'])}")
    print(f"  __NEXT_DATA__: {data['nextData'][:100] if data['nextData'] else 'None'}")
    for p in data['products']:
        print(f"  <{p['tag']} class='{p['cls']}'> href={p['href'][:50]}")
        print(f"    text: {p['text'][:100]}")
    
    await ctx.close()

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS)
        await test_kabum(browser)
        await test_pichau(browser)
        await browser.close()

asyncio.run(main())