import os
import re
import cv2
import pytesseract
import capsolver
import asyncio
import pyrogram
from pyrogram import Client, filters
from curl_cffi import requests
from dotenv import load_dotenv

# FORCED MONKEYPATCH for Python 3.14 compatibility
# Pyrogram's sync.async_to_sync calls get_event_loop() at import time, 
# which fails in 3.14 if no loop is running.
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

load_dotenv()

# Config
API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")
CAPSOLVER_KEY = os.getenv("API_KEY")
STAKE_SESSION = os.getenv("STAKE_SESSION")
STAKE_COOKIE = os.getenv("STAKE_COOKIE")
STAKE_URL = "https://stake.com"

capsolver.api_key = CAPSOLVER_KEY

def solve_turnstile():
    print("[*] Solving Turnstile...")
    try:
        solution = capsolver.solve({
            "type": "AntiTurnstileTaskProxyLess",
            "queries": {
                "websiteURL": STAKE_URL,
                "websiteKey": "0x4AAAAAAAE6m_S_A-04T5Xn"
            }
        })
        return solution.get("token")
    except Exception as e:
        print(f"[!] Capsolver error: {e}")
        return None

def claim_code(code):
    print(f"[*] Attempting to claim: {code}")
    token = solve_turnstile()
    if not token:
        print("[!] Failed to get Turnstile token.")
        return

    headers = {
        "x-access-token": STAKE_SESSION,
        "cookie": STAKE_COOKIE,
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    payload = {
        "query": "mutation RedeemBonusDrop($code: String!, $token: String!) { redeemBonusDrop(code: $code, token: $token) }",
        "variables": {"code": code, "token": token}
    }

    try:
        resp = requests.post(
            f"{STAKE_URL}/api/graphql",
            json=payload,
            headers=headers,
            impersonate="chrome110"
        )
        print(f"[+] Response: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[!] Request error: {e}")

def extract_from_video(file_path):
    cap = cv2.VideoCapture(file_path)
    count = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        if count % 15 == 0:
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

async def run_bot():
    app = Client("stake_bot", api_id=API_ID, api_hash=API_HASH)

    @app.on_message(filters.chat("StakecomDailyDrops"))
    async def handle_message(client, message):
        code = None
        if message.text:
            match = re.search(r'Code:\s*(stakecom\w+)', message.text, re.IGNORECASE)
            if match:
                code = match.group(1)
                print(f"[!] Found code in text: {code}")
        elif message.video:
            print("[*] Downloading video...")
            path = await message.download()
            loop = asyncio.get_running_loop()
            code = await loop.run_in_executor(None, extract_from_video, path)
            os.remove(path)
            if code:
                print(f"[!] Found code in video: {code}")

        if code:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, claim_code, code)

    print("[*] Bot starting...")
    await app.start()
    print("[*] Bot is online and listening.")
    await pyrogram.idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_bot())
