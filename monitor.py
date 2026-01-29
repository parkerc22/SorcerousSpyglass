import os
import json
import asyncio
import requests
import logging
import random
from playwright.async_api import async_playwright

# --- Setup ---
CARDS_JSON = os.getenv("CARDS_TO_MONITOR")
CARDS_TO_MONITOR = json.loads(CARDS_JSON) if CARDS_JSON else {}
NTFY_TOPIC = os.getenv("NTFY_TOPIC")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

async def check_single_card(browser_context, name, url):
    # 1. Random Jitter (Bot prevention)
    await asyncio.sleep(random.uniform(5, 10))
    
    page = await browser_context.new_page()
    try:
        # 2. Navigate and wait for content
        logging.info(f"Checking {name}...")
        response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Check for 403 or other blockages
        if response.status == 403:
            logging.error(f"❌ Access Denied (403) for {name}. Bot detected.")
            return

        # Give dynamic JS extra time to load inventory data
        await asyncio.sleep(7) 

        # 3. DEBUG: Take a screenshot to see what the bot sees
        await page.screenshot(path=f"debug_{name.replace(' ', '_')}.png")

        # 4. Check Stock Status
        # We look for the "Out of Stock" text. If NOT found, we check for "Add to Cart"
        content = await page.content()
        oos_text = "This product is currently out of stock"
        
        # Pro sites sometimes use specific button text
        in_stock_button = page.get_by_text("Add to Cart", exact=False)
        button_count = await in_stock_button.count()

        if oos_text not in content and button_count > 0:
            # Found button and no OOS message
            price_elem = page.locator(".product-details__price, .price").first
            price = await price_elem.inner_text() if await price_elem.count() > 0 else "Price Unknown"
            
            logging.info(f"✅ {name} IS IN STOCK!")
            requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", 
                          data=f"{name} is in stock for {price}!".encode("utf-8"),
                          headers={"Title": "Stock Alert", "Click": url, "Priority": "high"})
        else:
            logging.info(f"❌ {name} is out of stock.")
            
    except Exception as e:
        logging.error(f"⚠️ Error checking {name}: {e}")
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        # 5. Stealth launch arguments
        browser = await p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
        ])
        
        # Use a real user context to bypass simple bot checks
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        
        tasks = [check_single_card(context, name, url) for name, url in CARDS_TO_MONITOR.items()]
        await asyncio.gather(*tasks)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
