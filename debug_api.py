"""Test KaBuM search API."""
import asyncio, sys, json, httpx

async def main():
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        # KaBuM has a known API endpoint
        urls = [
            "https://kabum.com.br/api/catalogo/listagem?pagina=1&ordem=mais_relevantes&limite=10&string=rtx+4060",
            "https://www.kabum.com.br/api/catalogo/listagem?pagina=1&ordem=mais_relevantes&limite=10&string=rtx+4060",
            "https://services.kabum.com.br/api/catalogo/listagem?pagina=1&ordem=mais_relevantes&limite=10&string=rtx+4060",
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }
        for url in urls:
            try:
                resp = await client.get(url, headers=headers)
                print(f"\nURL: {url[:80]}...")
                print(f"Status: {resp.status_code}")
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        print(f"Keys: {list(data.keys())[:10]}")
                        if "dados" in data:
                            produtos = data["dados"]
                            if isinstance(produtos, list) and len(produtos) > 0:
                                p = produtos[0]
                                print(f"First product keys: {list(p.keys())[:15]}")
                                print(f"Nome: {p.get('nome', p.get('name', 'N/A'))[:80]}")
                                print(f"Preco: {p.get('preco', p.get('price', p.get('preco_desconto', 'N/A')))}")
                            elif isinstance(produtos, dict):
                                print(f"dados keys: {list(produtos.keys())[:10]}")
                                for k, v in list(produtos.items())[:3]:
                                    if isinstance(v, list):
                                        print(f"  {k}: list of {len(v)}")
                                        if v:
                                            print(f"    First: {str(v[0])[:100]}")
                        print(f"Response length: {len(resp.text)}")
                    except:
                        print(f"Not JSON. Length: {len(resp.text)}")
                        print(resp.text[:200])
            except Exception as e:
                print(f"\nURL: {url[:80]}...")
                print(f"Error: {e}")

asyncio.run(main())