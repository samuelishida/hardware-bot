import asyncio, sys, logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
sys.path.insert(0, '.')
from scrapers.mercadolivre import MercadoLivreScraper

async def test():
    for term in ['ryzen-5-5700x3d', 'rtx-4060-ti', 'rx-7900-xtx', 'rtx-4060']:
        s = MercadoLivreScraper(search_term=term)
        async with s:
            r = await s.scrape()
        print(f'{term}: price=R${r.price} available={r.available} label={r.stock_label}')

asyncio.run(test())
