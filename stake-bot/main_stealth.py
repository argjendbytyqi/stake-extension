import os
import re
import cv2
import pytesseract
import asyncio
import time
from telethon import TelegramClient, events
from playwright.async_api import async_playwright
# Import correctly - playwright_stealth exposes stealth as a function in its __init__
import playwright_stealth
from dotenv import load_dotenv

load_dotenv()

# Config
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
STAKE_SESSION = os.getenv("STAKE_SESSION")
STAKE_COOKIE = os.getenv("STAKE_COOKIE")
STAKE_URL = "https://stake.com"

# Global browser state
browser_context = None
stake_page = None

async def init_browser(playwright):
    global browser_context, stake_page
    print("[*] Launching Stealth Browser...")
    browser = await playwright.chromium.launch(headless=True)
    
    # Format cookies for Playwright
    cookies = []
    for item in STAKE_COOKIE.split(";"):
        if "=" in item:
            name, value = item.strip().split("=", 1)
            cookies.append({
                "name": name, 
                "value": value, 
                "domain": ".stake.com", 
                "path": "/"
            })

    browser_context = await browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720}
    )
    await browser_context.add_cookies(cookies)
    
    stake_page = await browser_context.new_page()
    # Correct way to call it when imported as a module
    await playwright_stealth.stealth_async(stake_page)
    
    print("[*] Pre-loading Stake Settings page...")
    await stake_page.goto(f"{STAKE_URL}/settings/offers")
    return browser

async def claim_code_browser(code):
    global stake_page
    if not stake_page:
        print("[!] Browser not initialized.")
        return

    start_time = time.time()
    print(f"[*] Claiming: {code}")
    
    # Use the direct URL structure for faster interaction
    target_url = f"{STAKE_URL}/settings/offers?type=drop&code={code}&modal=redeemBonus"
    
    try:
        await stake_page.goto(target_url)
        
        # Wait for the 'Claim' button to appear and click it
        # The button is usually a primary button with text 'Claim' or 'Redeem'
        # Adjust selector based on Stake's exact UI
        claim_button_selector = "button:has-text('Claim'), button:has-text('Redeem')"
        
        await stake_page.wait_for_selector(claim_button_selector, timeout=5000)
        await stake_page.click(claim_button_selector)
        
        print(f"[+] Clicked Claim for {code} in {time.time() - start_time:.2f}s")
        
        # Optional: wait for result toast/message
        # await asyncio.sleep(1) 
        
    except Exception as e:
        print(f"[!] Browser Claim Error: {e}")

def extract_from_video(file_path):
    cap = cv2.VideoCapture(file_path)
    count = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        if count % 10 == 0:
            h, w, _ = frame.shape
            roi = frame[int(h*0.3):int(h*0.8), int(w*0.1):int(w*0.9)]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            text = pytesseract.image_to_string(thresh, config='--psm 6').strip()
            match = re.search(r'stakecom\w+', text, re.IGNORECASE)
            if match:
                cap.release()
                return match.group(0)
        count += 1
        if count > 150: break
    cap.release()
    return None

async def main():
    async with async_playwright() as playwright:
        browser = await init_browser(playwright)
        
        client = TelegramClient('stake_bot_telethon', API_ID, API_HASH)
        await client.connect()
        
        print("[*] Fetching last messages...")
        entity = await client.get_entity('StakecomDailyDrops')
        
        async for message in client.iter_messages(entity, limit=1):
            if message.text:
                match = re.search(r'Code:\s*(stakecom\w+)', message.text, re.IGNORECASE)
                if match:
                    await claim_code_browser(match.group(1))
        
        print("[*] Bot is online and listening for NEW drops.")

        @client.on(events.NewMessage(chats=entity))
        async def handler(event):
            code = None
            if event.text:
                match = re.search(r'Code:\s*(stakecom\w+)', event.text, re.IGNORECASE)
                if match:
                    code = match.group(1)
                    print(f"[!] Found NEW code in text: {code}")
            
            if not code and event.message.video:
                print("[*] Downloading video for OCR...")
                path = await event.download_media()
                code = await asyncio.get_event_loop().run_in_executor(None, extract_from_video, path)
                os.remove(path)
                if code:
                    print(f"[!] Found NEW code in video: {code}")

            if code:
                await claim_code_browser(code)

        await client.run_until_disconnected()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
