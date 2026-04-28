"""KaBuM - check prices via document.body.innerText and HTML."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        page = await ctx.new_page()

        await page.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        
        for _ in range(5):
            await page.wait_for_timeout(3000)
            await page.evaluate("window.scrollBy(0, 500)")
        
        # Get all text containing R$
        text = await page.inner_text("body")
        lines = [l.strip() for l in text.split("\n") if "R$" in l]
        print(f"Lines with R$: {len(lines)}")
        for l in lines[:10]:
            print(f"  {l[:80]}")

        # Check what's in the product links
        link_texts = await page.evaluate("""() => {
            let links = document.querySelectorAll("a[href*='/produto/']");
            return Array.from(links).slice(0, 5).map(l => ({
                href: l.getAttribute('href'),
                text: l.innerText.substring(0, 100),
                html: l.innerHTML.substring(0, 300),
                children: l.children.length,
                childTags: Array.from(l.children).map(c => c.tagName).join(',')
            }));
        }""")
        print(f"\nProduct links: {len(link_texts)}")
        for l in link_texts:
            print(f"  href={l['href'][:50]}")
            print(f"  text={l['text'][:60]}")
            print(f"  children={l['children']} tags=[{l['childTags']}]")
            print(f"  html={l['html'][:200]}")

        # Check what's around the price elements in the full HTML
        html = await page.content()
        # Find the first occurrence of a price near a product link
        import re
        for m in re.finditer(r'R\$\s*[\d.,]+', html):
            pos = m.start()
            ctx_before = html[max(0,pos-100):pos]
            ctx_after = html[pos:pos+100]
            if '/produto/' in ctx_before or '/produto/' in ctx_after:
                print(f"\nPrice near product link: {m.group()}")
                print(f"  Before: {ctx_before}")
                print(f"  After: {ctx_after}")
                break

        await browser.close()

asyncio.run(main())