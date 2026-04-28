"""
tests/test_antibot.py — Anti-bot blocking pattern detection.

Run each scraper with search term "rx 7900 xtx" and report:
1. Which scrapers succeed/fail
2. What error messages or blocking patterns appear
3. Capture screenshots of any CAPTCHA or blocking pages
"""

from __future__ import annotations
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright

# Import scrapers
from scrapers.kabum import KabumScraper
from scrapers.pichau import PichauScraper
from scrapers.amazon import AmazonScraper
from scrapers.terabyte import TeraScraper
from scrapers.mercadolivre import MercadoLivreScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

SEARCH_TERM = "rx-7900-xtx"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"

# Blocking patterns to detect
BLOCKING_PATTERNS = {
    "captcha": ["captcha", "verify", "verification", "i'm not a robot", "checkbox"],
    "cloudflare": ["cloudflare", "just a moment", "checking browser", "ray id"],
    "access_denied": ["access denied", "forbidden", "403", "403 forbidden", "blocked"],
    "robot": ["robot", "bot", "automated", "suspicious"],
    "rate_limit": ["rate limit", "too many requests", "429", "slow down"],
}

# Browser-based scrapers
BROWSER_SCRAPERS = [
    ("Kabum", KabumScraper),
    ("Pichau", PichauScraper),
    ("Amazon", AmazonScraper),
    ("Terabyte", TeraScraper),
]

# HTTP-based scraper
HTTP_SCRAPERS = [
    ("MercadoLivre", MercadoLivreScraper),
]


async def check_blocking_patterns(page, scraper_name: str) -> dict:
    """Check page for blocking patterns and return findings."""
    findings = {
        "blocked": False,
        "patterns_found": [],
        "page_title": "",
        "screenshot_path": None,
    }
    
    try:
        page_title = await page.title()
        findings["page_title"] = page_title
        logger.info(f"[{scraper_name}] Page title: {page_title}")
        
        # Check title for blocking patterns
        title_lower = page_title.lower()
        for category, patterns in BLOCKING_PATTERNS.items():
            for pattern in patterns:
                if pattern in title_lower:
                    findings["patterns_found"].append(f"{category}: '{pattern}' in title")
                    findings["blocked"] = True
        
        # Check page content for blocking patterns
        content = await page.content()
        content_lower = content.lower()
        
        for category, patterns in BLOCKING_PATTERNS.items():
            for pattern in patterns:
                if pattern in content_lower and f"{category}: '{pattern}' in title" not in findings["patterns_found"]:
                    findings["patterns_found"].append(f"{category}: '{pattern}' in content")
                    findings["blocked"] = True
        
        # Take screenshot if blocking detected
        if findings["blocked"]:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = SCREENSHOT_DIR / f"{scraper_name.lower()}_{timestamp}_blocked.png"
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path), full_page=True)
            findings["screenshot_path"] = str(screenshot_path)
            logger.warning(f"[{scraper_name}] Screenshot saved: {screenshot_path}")
        
    except Exception as e:
        logger.error(f"[{scraper_name}] Error checking blocking patterns: {e}")
        findings["error"] = str(e)
    
    return findings


async def run_browser_scraper_with_screenshot(scraper_name: str, scraper_class, browser) -> dict:
    """Run a browser-based scraper with dedicated page for screenshot capture."""
    result = {
        "scraper": scraper_name,
        "success": False,
        "price": None,
        "available": False,
        "stock_label": "",
        "error": None,
        "blocking": None,
        "url": None,
        "screenshot_path": None,
    }
    
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing {scraper_name} scraper...")
        logger.info(f"{'='*60}")
        
        # Create a page for direct navigation and screenshot
        page = await browser.new_page()
        
        scraper = scraper_class(browser=browser, search_term=SEARCH_TERM)
        
        # Navigate to the search URL directly first to capture screenshot
        logger.info(f"[{scraper_name}] Navigating to: {scraper.search_url}")
        
        try:
            await page.goto(scraper.search_url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(3000)  # Wait for any dynamic content
            
            # Check for blocking patterns
            blocking_info = await check_blocking_patterns(page, scraper_name)
            if blocking_info["blocked"]:
                result["blocking"] = blocking_info
                result["screenshot_path"] = blocking_info["screenshot_path"]
                logger.warning(f"[{scraper_name}] BLOCKING DETECTED!")
                for pattern in blocking_info["patterns_found"]:
                    logger.warning(f"[{scraper_name}]   - {pattern}")
        except Exception as nav_error:
            logger.error(f"[{scraper_name}] Navigation error: {nav_error}")
            result["error"] = str(nav_error)
            
            # Try screenshot anyway
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = SCREENSHOT_DIR / f"{scraper_name.lower()}_{timestamp}_error.png"
                SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(screenshot_path), full_page=True)
                result["screenshot_path"] = str(screenshot_path)
            except:
                pass
        
        # Now run the actual scraper
        scrape_result = await scraper.scrape()
        
        result["success"] = scrape_result.price is not None or scrape_result.available
        result["price"] = scrape_result.price
        result["available"] = scrape_result.available
        result["stock_label"] = scrape_result.stock_label
        result["url"] = scrape_result.url
        
        if scrape_result.price:
            logger.info(f"[{scraper_name}] SUCCESS - Price: R$ {scrape_result.price:.2f}")
            logger.info(f"[{scraper_name}] Available: {scrape_result.available}")
            logger.info(f"[{scraper_name}] Stock: {scrape_result.stock_label}")
        else:
            logger.warning(f"[{scraper_name}] No price found")
            logger.warning(f"[{scraper_name}] Status: {scrape_result.stock_label}")
        
        await page.close()
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[{scraper_name}] ERROR: {e}", exc_info=True)
    
    return result


async def run_http_scraper(scraper_name: str, scraper_class) -> dict:
    """Run an HTTP-based scraper and capture results."""
    result = {
        "scraper": scraper_name,
        "success": False,
        "price": None,
        "available": False,
        "stock_label": "",
        "error": None,
        "blocking": None,
        "url": None,
    }
    
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing {scraper_name} scraper (HTTP API)...")
        logger.info(f"{'='*60}")
        
        scraper = scraper_class(search_term=SEARCH_TERM)
        async with scraper:
            scrape_result = await scraper.scrape()
        
        result["success"] = scrape_result.price is not None or scrape_result.available
        result["price"] = scrape_result.price
        result["available"] = scrape_result.available
        result["stock_label"] = scrape_result.stock_label
        result["url"] = scrape_result.url
        
        if scrape_result.price:
            logger.info(f"[{scraper_name}] SUCCESS - Price: R$ {scrape_result.price:.2f}")
            logger.info(f"[{scraper_name}] Available: {scrape_result.available}")
            logger.info(f"[{scraper_name}] Stock: {scrape_result.stock_label}")
            logger.info(f"[{scraper_name}] URL: {scrape_result.url}")
        else:
            logger.warning(f"[{scraper_name}] No price found")
            logger.warning(f"[{scraper_name}] Status: {scrape_result.stock_label}")
            
        # Check for API blocking
        if scrape_result.stock_label == "Erro de rede":
            result["blocking"] = {"patterns_found": ["HTTP API returned error (possible 403 blocking)"]}
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[{scraper_name}] ERROR: {e}", exc_info=True)
    
    return result


async def main():
    """Main test runner."""
    print("\n" + "="*70)
    print("Anti-Bot Blocking Pattern Detection Test")
    print("="*70)
    print(f"Search term: {SEARCH_TERM.replace('-', ' ')}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    results = []
    
    # Setup Playwright
    logger.info("\nStarting Playwright browser...")
    pw = await async_playwright().start()
    
    STEALTH_ARGS = [
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-blink-features=AutomationControlled",
        "--window-size=1920,1080",
    ]
    
    browser = await pw.chromium.launch(
        headless=True,
        args=STEALTH_ARGS,
    )
    
    logger.info("Browser launched\n")
    
    try:
        # Run browser-based scrapers
        for scraper_name, scraper_class in BROWSER_SCRAPERS:
            result = await run_browser_scraper_with_screenshot(scraper_name, scraper_class, browser)
            results.append(result)
            await asyncio.sleep(2)  # Delay between scrapers
        
        # Run HTTP-based scrapers
        for scraper_name, scraper_class in HTTP_SCRAPERS:
            result = await run_http_scraper(scraper_name, scraper_class)
            results.append(result)
            await asyncio.sleep(1)
    
    finally:
        await browser.close()
        await pw.stop()
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    success_count = 0
    blocked_count = 0
    
    for result in results:
        status = "SUCCESS" if result["success"] else "FAILED"
        if result["blocking"]:
            status = "BLOCKED"
            blocked_count += 1
        elif result["success"]:
            success_count += 1
        
        print(f"\n{result['scraper']}: {status}")
        print(f"  Price: R$ {result['price']:.2f}" if result['price'] else "  Price: Not found")
        print(f"  Available: {result['available']}")
        print(f"  Stock: {result['stock_label']}")
        
        if result["error"]:
            print(f"  Error: {result['error']}")
        
        if result["blocking"]:
            print(f"  BLOCKING PATTERNS DETECTED:")
            for pattern in result["blocking"].get("patterns_found", []):
                print(f"     - {pattern}")
            if result["blocking"].get("screenshot_path"):
                print(f"  Screenshot: {result['blocking']['screenshot_path']}")
            if result["blocking"].get("page_title"):
                print(f"  Page Title: {result['blocking']['page_title']}")
    
    print("\n" + "="*70)
    print(f"Results: {success_count} successful, {blocked_count} blocked, {len(results) - success_count - blocked_count} failed")
    print(f"Screenshots saved to: {SCREENSHOT_DIR.absolute()}")
    print("="*70 + "\n")
    
    return results


if __name__ == "__main__":
    results = asyncio.run(main())
    
    # Exit with error if any scraper was blocked
    blocked = [r for r in results if r.get("blocking")]
    sys.exit(1 if blocked else 0)
