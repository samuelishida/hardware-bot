import httpx

headers_variants = [
    {"User-Agent": "python-requests/2.31.0", "Accept": "application/json"},
    {"User-Agent": "MLScraper/1.0", "Accept": "application/json"},
    {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "Accept": "application/json"},
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.mercadolivre.com.br/",
        "Origin": "https://www.mercadolivre.com.br",
    },
    {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json",
    },
]

urls = [
    "https://api.mercadolibre.com/sites/MLB/search?q=rtx+4060&limit=5&condition=new",
    "https://api.mercadolibre.com/sites/MLB/search?q=rtx+4060&limit=5",
]

import asyncio
async def main():
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for url in urls:
            for i, headers in enumerate(headers_variants):
                try:
                    r = await client.get(url, headers=headers)
                    print(f"  URL...{url[-30:]} | headers[{i}] | Status: {r.status_code} | Len: {len(r.text)}")
                    if r.status_code == 200:
                        data = r.json()
                        results = data.get("results", [])
                        print(f"    SUCCESS! Results: {len(results)}")
                        for item in results[:2]:
                            print(f"      {item.get('title','?')[:50]} - R${item.get('price','?')}")
                        break
                except Exception as e:
                    print(f"  URL...{url[-30:]} | headers[{i}] | Error: {e}")

asyncio.run(main())