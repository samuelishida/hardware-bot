"""Quick check KaBuM main element structure."""
import asyncio, sys
sys.path.insert(0, "/home/ubuntu/precosbot")
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        page = await ctx.new_page()
        await page.goto("https://www.kabum.com.br/busca/rtx-4060", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(12000)

        # Check main element
        main_info = await page.evaluate("""() => {
            let main = document.querySelector("main");
            if (!main) return {found: false};
            return {
                found: true,
                className: main.className || "",
                hasSc: main.className?.includes("sc-") || false,
                tag: main.tagName,
                childrenCount: main.children.length,
                childTags: Array.from(main.children).map(c => c.tagName + "." + (c.className||"").substring(0,30)).slice(0, 10),
            };
        }""")
        print(f"Main: {main_info}")

        # Run the scraper's evaluate directly
        result = await page.evaluate("""(searchTerm) => {
            const keywords = searchTerm.replace(/-/g, ' ').split(' ');
            const modelKeywords = keywords.filter(kw => /[a-zA-Z]/.test(kw) && /[0-9]/.test(kw));

            // Check different container approaches
            const mainSc = document.querySelectorAll("main[class*='sc-']");
            const allMain = document.querySelectorAll("main");
            const mainDivs = document.querySelectorAll("main > div");
            const productLinks = document.querySelectorAll("a[href*='/produto/']");

            // For each product link, find its container
            let containers = new Set();
            for (let link of productLinks) {
                let el = link;
                for (let i = 0; i < 5; i++) {
                    el = el?.parentElement;
                    if (!el) break;
                }
                if (el) containers.add(el.tagName + "." + (el.className||"").substring(0,30));
            }

            return {
                mainSc: mainSc.length,
                allMain: allMain.length,
                mainDivs: mainDivs.length,
                productLinks: productLinks.length,
                containerTypes: Array.from(containers),
                firstMainClass: allMain[0]?.className?.substring(0, 60) || "none",
            };
        }""", "rtx-4060")
        print(f"Scraper result: {result}")

        await browser.close()

asyncio.run(main())