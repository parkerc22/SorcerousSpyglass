import os
import json
import asyncio
import requests
import logging
import random
from playwright.async_api import async_playwright

# --- Setup Configuration from Secrets ---
cards_json = os.getenv("CARDS_TO_MONITOR")
CARDS_TO_MONITOR = json.loads(cards_json) if cards_json else {}
NTFY_TOPIC = os.getenv("NTFY_TOPIC")

logging.basicConfig(
    filename='stock_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def send_notification(card_name, price, url):
    """Sends push notification via ntfy.sh"""
    message = f" {card_name} is IN STOCK for {price}"
    try:
        # requests is blocking, so we run it in a thread to keep the loop moving
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": "TCG Stock Alert", "Priority": "high", "Click": url}
        ))
    except Exception as e:
        logging.error(f"Failed to send notification: {e}")

async def check_single_card(browser, name, url):
    """Staggers the check and looks for 'Out of Stock' text"""
    # Jitter to avoid bot detection
    await asyncio.sleep(random.uniform(5, 10))
    
    page = await browser.new_page()
    try:
        # Standard User-Agent to look like a real browser
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        # 1. Check if the "Out of Stock" message is present
        # We use a case-insensitive regex for flexibility
        oos_message = page.get_by_text("This product is currently out of stock", exact=False)
        is_oos = await oos_message.count() > 0
        
        # 2. Get the current price
        price_elem = page.locator(".product-details__price, .price, .regular-price").first
        price = await price_elem.inner_text() if await price_elem.count() > 0 else "Price Hidden"

        if not is_oos:
            # If the OOS message is GONE, it's likely in stock!
            logging.info(f" {name}: IN STOCK ({price})")
            await send_notification(name, price, url)
        else:
            logging.info(f" {name}: Still Out of Stock")
            
    except Exception as e:
        logging.error(f" Error checking {name}: {str(e)[:50]}")
    finally:
        await page.close()

async def main():
    if not CARDS_TO_MONITOR:
        print("No cards found in CARDS_TO_MONITOR secret.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        tasks = [check_single_card(browser, name, url) for name, url in CARDS_TO_MONITOR.items()]
        await asyncio.gather(*tasks)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
