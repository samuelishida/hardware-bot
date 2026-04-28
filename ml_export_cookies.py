"""
ml_export_cookies.py — Run this on WINDOWS (not the VM) while logged into ML in Chrome/Edge.

Usage:
  python ml_export_cookies.py

It saves ml_cookies.json to the project root, then you deploy it to the VM:
  scp -i ~/.ssh/oci_yvy ml_cookies.json ubuntu@137.131.159.91:/home/ubuntu/precosbot/

The scraper will automatically load these cookies and bypass the login wall.
Cookies typically last 7-30 days; re-run this script when they expire.
"""

import json
import sys

try:
    import browser_cookie3
except ImportError:
    print("Install browser_cookie3 first:  pip install browser_cookie3")
    sys.exit(1)

DOMAINS = [".mercadolivre.com.br", ".mercadolibre.com", "mercadolivre.com.br"]

cookies_out = []
for loader in (browser_cookie3.chrome, browser_cookie3.edge):
    try:
        for domain in DOMAINS:
            for c in loader(domain_name=domain.lstrip(".")):
                cookies_out.append({
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path if c.path else "/",
                    "expires": int(c.expires) if c.expires else -1,
                    "httpOnly": False,
                    "secure": bool(c.secure),
                    "sameSite": "Lax",
                })
    except Exception as e:
        print(f"  {loader.__name__}: {e}")

if not cookies_out:
    print("Nenhum cookie ML encontrado. Certifique-se de estar logado no Chrome ou Edge.")
    sys.exit(1)

out_file = "ml_cookies.json"
with open(out_file, "w") as f:
    json.dump(cookies_out, f)

print(f"Exportados {len(cookies_out)} cookies -> {out_file}")
print()
print("Deploy para o VM:")
print("  scp -i ~/.ssh/oci_yvy ml_cookies.json ubuntu@137.131.159.91:/home/ubuntu/precosbot/")
