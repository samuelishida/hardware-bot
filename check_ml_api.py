import httpx
r = httpx.get(
    "https://api.mercadolibre.com/sites/MLB/search?q=rtx+4060&limit=5&condition=new",
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    },
    follow_redirects=True,
    timeout=15,
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    results = data.get("results", [])
    print(f"Results: {len(results)}")
    for item in results[:3]:
        print(f"  {item.get('title', 'N/A')[:60]} - R${item.get('price', 'N/A')}")
else:
    print(f"Body: {r.text[:200]}")