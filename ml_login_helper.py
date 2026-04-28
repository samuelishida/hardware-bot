"""
ml_login_helper.py — Run on WINDOWS to capture ML session cookies.

Opens a Chrome window. Log into Mercado Livre — the script detects login
automatically and saves cookies, then deploys to the VM.

Usage:
  python ml_login_helper.py
  ! python ml_login_helper.py    (from Claude Code terminal)
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

COOKIE_FILE = Path("ml_cookies.json")
VM = "ubuntu@137.131.159.91"
VM_PATH = "/home/ubuntu/precosbot/ml_cookies.json"
SSH_KEY = str(Path.home() / ".ssh" / "oci_yvy")
LOGIN_TIMEOUT_S = 180  # 3 minutes to complete login


def _is_logged_in(cookies: list) -> bool:
    """Return True if the cookie set indicates an active ML session."""
    auth_names = {"orguserid", "ssid", "dsid", "edsid", "c:access_token", "access_token"}
    names = {c["name"] for c in cookies}
    return bool(names & auth_names)


async def capture_cookies():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright não encontrado. Instale: pip install playwright && playwright install chromium")
        sys.exit(1)

    print("Abrindo Chrome...")
    print(f"Faça login no Mercado Livre. O script detecta automaticamente (timeout: {LOGIN_TIMEOUT_S}s).\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--window-size=1280,900", "--no-sandbox"],
        )
        context = await browser.new_context(
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        await page.goto("https://www.mercadolivre.com.br/", wait_until="domcontentloaded")

        # Poll until logged in or timeout
        elapsed = 0
        poll_interval = 3
        logged_in = False
        while elapsed < LOGIN_TIMEOUT_S:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            cookies = await context.cookies()
            if _is_logged_in(cookies):
                logged_in = True
                print(f"Login detectado após {elapsed}s!")
                break
            print(f"  Aguardando login... ({elapsed}s / {LOGIN_TIMEOUT_S}s)")

        if not logged_in:
            print(f"\nTimeout após {LOGIN_TIMEOUT_S}s. Nenhum login detectado.")
            # Save whatever cookies we have anyway — might still be enough
            cookies = await context.cookies()
            ml_cookies = [
                c for c in cookies
                if "mercadolivre" in c.get("domain", "") or "mercadolibre" in c.get("domain", "")
            ]
            if ml_cookies:
                print(f"Salvando {len(ml_cookies)} cookies de sessão parcial...")
            else:
                print("Sem cookies ML. Tente fazer login e execute novamente.")
                await browser.close()
                return False
        else:
            ml_cookies = [
                c for c in (await context.cookies())
                if "mercadolivre" in c.get("domain", "") or "mercadolibre" in c.get("domain", "")
            ]

        COOKIE_FILE.write_text(json.dumps(ml_cookies, indent=2))
        print(f"{len(ml_cookies)} cookies salvos em {COOKIE_FILE}")

        # Keep browser open briefly so user can see it completed
        await asyncio.sleep(2)
        await browser.close()
        return True


def deploy():
    print(f"\nDeployando {COOKIE_FILE} para o VM...")
    result = subprocess.run(
        ["scp", "-i", SSH_KEY, str(COOKIE_FILE), f"{VM}:{VM_PATH}"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("Deploy concluído! ML deve funcionar no bot agora.")
    else:
        print(f"scp falhou: {result.stderr.strip()}")
        print(f"\nDeploy manual:\n  scp -i {SSH_KEY} {COOKIE_FILE} {VM}:{VM_PATH}")


if __name__ == "__main__":
    ok = asyncio.run(capture_cookies())
    if ok:
        deploy()
