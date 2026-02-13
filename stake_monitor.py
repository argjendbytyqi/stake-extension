import asyncio
import os
import re
import cv2
import random
import pytesseract
from telethon import TelegramClient, events
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# --- CONFIGURATION ---
API_ID = 39003063
API_HASH = 'b19980f250f5053c4be259bb05668a35'
CHANNEL_USERNAME = 'StakecomDailyDrops'
STAKE_URL = "https://stake.com/settings/offers"

# Global lock to prevent race conditions
action_lock = asyncio.Lock()
browser_instance = None

client = TelegramClient('stake_session', API_ID, API_HASH)

def extract_text_from_media(file_path):
    cap = cv2.VideoCapture(file_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    extracted_text = ""
    for idx in range(0, total_frames, 5):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        success, image = cap.read()
        if success:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            extracted_text += " " + pytesseract.image_to_string(gray)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            extracted_text += " " + pytesseract.image_to_string(thresh)
            adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            extracted_text += " " + pytesseract.image_to_string(adaptive)
    cap.release()
    return extracted_text

async def local_solve_turnstile(page):
    try:
        challenge_frame = None
        for frame in page.frames:
            if "challenges.cloudflare.com" in frame.url:
                challenge_frame = frame
                break
        if challenge_frame:
            iframe_el = await page.query_selector('iframe[src*="challenges.cloudflare.com"]')
            if iframe_el:
                box = await iframe_el.bounding_box()
                if box:
                    print("🛡️ Cloudflare box found, clicking...")
                    await page.mouse.click(box['x'] + 30, box['y'] + box['height']/2)
                    await asyncio.sleep(5)
                    return True
    except: pass
    return False

async def claim_code(code):
    global browser_instance
    if not code or not browser_instance: return
    
    async with action_lock:
        print(f"🚀 Striking code: {code}")
        try:
            context = browser_instance.contexts[0]
            page = None
            for p in context.pages:
                try:
                    if "stake.com" in p.url:
                        page = p
                        break
                except: continue
            
            if not page:
                page = await context.new_page()
                await stealth_async(page)

            direct_url = f"https://stake.com/settings/offers?type=drop&code={code}&modal=redeemBonus"
            print(f"🔗 Strike URL: {direct_url}")
            
            # Fast navigation
            await page.goto(direct_url, wait_until="domcontentloaded")
            await asyncio.sleep(2) # Stabilize
            
            # Check for Cloudflare block
            content = await page.content()
            if "Security verification" in content or "Verify you are human" in content:
                print("⚠️ Blocked by Cloudflare. Attempting local click...")
                await local_solve_turnstile(page)
                await page.goto(direct_url, wait_until="domcontentloaded")
                await asyncio.sleep(2)

            # High-speed JS Execution with retry loop
            result = "Error: Execution failed"
            for i in range(3):
                try:
                    # Final check for readiness
                    await page.wait_for_load_state("domcontentloaded")
                    result = await page.evaluate("""
                        async (targetCode) => {
                            const findButton = () => {
                                return Array.from(document.querySelectorAll('button')).find(b => 
                                    (b.innerText.includes('Redeem') || b.innerText.includes('Submit') || b.innerText.includes('Claim')) && 
                                    b.offsetParent !== null
                                );
                            };

                            let button = null;
                            for (let j = 0; j < 10; j++) {
                                button = findButton();
                                if (button) break;
                                await new Promise(r => setTimeout(r, 500));
                            }

                            if (!button) {
                                const body = document.body.innerText.substring(0, 100).replace(/\\n/g, ' ');
                                return `Error: Button not found. Text: ${body}`;
                            }

                            button.removeAttribute('disabled');
                            button.click();
                            button.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                            
                            await new Promise(r => setTimeout(r, 4000));
                            
                            const text = document.body.innerText;
                            if (text.includes('Bonus unavailable')) {
                                const close = document.querySelector('button[aria-label="Close"], .modal-close, button svg')?.closest('button');
                                if (close) close.click();
                                return "Bonus unavailable (Limit reached)";
                            }
                            if (text.includes('Code not found')) return "Error: Code not found";
                            if (text.includes('already claimed')) return "Error: Already claimed";
                            if (text.includes('Success')) return "Success!";
                            
                            return "Redeem clicked. Monitor window for final result.";
                        }
                    """, code)
                    break
                except Exception as eval_e:
                    if "destroyed" in str(eval_e) and i < 2:
                        print(f"🔄 UI Context destroyed (Attempt {i+1}), retrying...")
                        await asyncio.sleep(1)
                        continue
                    else:
                        result = f"JS Error: {str(eval_e)[:50]}"
                        break

            print(f"✅ Result: {result}")
            await page.screenshot(path=f"strike_log_{code}.png")
            
        except Exception as e:
            print(f"⚠️ Global Strike Error: {e}")

@client.on(events.NewMessage(chats=CHANNEL_USERNAME))
async def handler(event):
    text = (event.raw_text or "").replace('\n', ' ')
    codes = re.findall(r'stakecom[a-zA-Z0-9]+', text)
    if not codes: codes = re.findall(r'\b[a-zA-Z0-9]{8,20}\b', text)
    noise = {'stakecom', 'telegram', 'available', 'wagered', 'claimed', 'active', 'dropped', 'Code'}
    valid_codes = [c for c in set(codes) if c.lower() not in [n.lower() for n in noise] and not c.isdigit()]
    for code in valid_codes:
        await asyncio.create_task(claim_code(code))

async def main():
    global browser_instance
    print("🚀 Starting Didier Drogba...")
    await client.start()
    print(f"⚽ Didier Drogba is on the pitch. Monitoring @{CHANNEL_USERNAME}...")
    
    async with async_playwright() as p:
        try:
            browser_instance = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            print("🔗 Connected to browser session.")
            
            async def page_warmer():
                while True:
                    await asyncio.sleep(600)
                    if not action_lock.locked():
                        async with action_lock:
                            try:
                                context = browser_instance.contexts[0]
                                page = context.pages[0] if context.pages else await context.new_page()
                                await page.goto(STAKE_URL, wait_until="domcontentloaded")
                                print("🔥 Session refreshed.")
                            except: pass

            asyncio.create_task(page_warmer())
            
            async for message in client.iter_messages(CHANNEL_USERNAME, limit=1):
                text = (message.text or "").replace('\n', ' ')
                codes = re.findall(r'stakecom[a-zA-Z0-9]+', text)
                if not codes: codes = re.findall(r'\b[a-zA-Z0-9]{8,20}\b', text)
                valid = [c for c in set(codes) if c.lower() not in ['stakecom', 'code'] and not c.isdigit()]
                for code in valid: await claim_code(code)
            
            await client.run_until_disconnected()
        except Exception as e: print(f"❌ Error: {e}")

if __name__ == '__main__':
    asyncio.run(main())
