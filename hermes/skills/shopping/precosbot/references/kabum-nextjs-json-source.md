## KaBuM! Search API — `__NEXT_DATA__` JSON Source

KaBuM!'s frontend is a Next.js app. Search results are server-side rendered into a `<script id="__NEXT_DATA__" type="application/json">` tag. This is a reliable, HTML-parsable source of structured product data when the Playwright scraper times out or returns "Não encontrado".

### Extraction Pattern (curl + grep/jq)

```bash
# 1. Fetch search page with a real browser UA
URL="https://www.kabum.com.br/busca/processador%20amd%20ryzen%207%205700x3d"
HTML=$(curl -sL "$URL" -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

# 2. Extract the __NEXT_DATA__ block
JSON=$(echo "$HTML" | grep -oP '(?<=<script id="__NEXT_DATA__" type="application/json">).*?(?=</script>)')

# 3. Products are under props.pageProps.data.catalogServer.products[]
#    Each product has: code, name, price, priceWithDiscount, available, url
```

### Key Fields

| Field | Meaning |
|-------|---------|
| `code` | SKU (e.g. `560101`) |
| `name` | Full product title |
| `price` | Raw price (centavos as float, e.g. `1967.00`) |
| `priceWithDiscount` | Price after any active discount |
| `available` | Boolean stock flag |
| `url` | Relative path — prepend `https://www.kabum.com.br` |
| `maxInstallment` | e.g. "10x de R$ 196,70" |

### Why This Matters

- The PrecoBot KaBuM scraper sometimes fails in headless mode because card elements don't render before the timeout.
- The `__NEXT_DATA__` JSON is present in the very first HTML response — no JavaScript execution required.
- This same pattern applies to **all** KaBuM! catalog pages (search, category, brand).

### Caveats

- `__NEXT_DATA__` is large (50–100KB of JSON embedded in HTML). Extract efficiently.
- Some products are `isMarketplace: true` (sold by third-party sellers). Check `sellerName` if you need to distinguish.
- Images are under `photos.g` / `photos.gg` arrays.
