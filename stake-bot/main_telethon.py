import os
import re
import cv2
import pytesseract
import capsolver
import asyncio
import json
import time
from telethon import TelegramClient, events
from curl_cffi import requests
from dotenv import load_dotenv

load_dotenv()

# Config
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
CAPSOLVER_KEY = os.getenv("API_KEY")
STAKE_SESSION = os.getenv("STAKE_SESSION")
STAKE_COOKIE = os.getenv("STAKE_COOKIE")
STAKE_URL = "https://stake.com"

# Capsolver needs the key set here
capsolver.api_key = CAPSOLVER_KEY

session_headers = {
    "x-access-token": STAKE_SESSION,
    "cookie": STAKE_COOKIE,
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def solve_turnstile():
    print("[*] Solving Turnstile...")
    try:
        task_data = {
            "clientKey": CAPSOLVER_KEY,
            "task": {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": STAKE_URL,
                "websiteKey": "0x4AAAAAAAE6m_S_A-04T5Xn",
                "metadata": {
                    "action": "redeemBonusDrop"
                }
            }
        }
        
        create_resp = requests.post("https://api.capsolver.com/createTask", json=task_data).json()
        task_id = create_resp.get("taskId")
        
        if not task_id:
            print(f"[!] Capsolver Create Task Error: {create_resp}")
            return None
            
        while True:
            time.sleep(2)
            result_resp = requests.post("https://api.capsolver.com/getTaskResult", json={
                "clientKey": CAPSOLVER_KEY,
                "taskId": task_id
            }).json()
            
            status = result_resp.get("status")
            if status == "ready":
                return result_resp.get("solution", {}).get("token")
            if status == "failed" or result_resp.get("errorId"):
                # If proxyless fails, we might need to use a proxy, but let's try one more tweak
                print(f"[!] Capsolver Error: {result_resp}")
                return None
            print("[*] Waiting for Turnstile solver...")
            
    except Exception as e:
        print(f"[!] Capsolver error: {e}")
        return None

def claim_code(code):
    print(f"[*] Attempting to claim: {code}")
    token = solve_turnstile()
    if not token:
        print("[!] No Turnstile token, skipping claim.")
        return

    payload = {
        "query": "mutation RedeemBonusDrop($code: String!, $token: String!) { redeemBonusDrop(code: $code, token: $token) }",
        "variables": {"code": code, "token": token}
    }

    try:
        resp = requests.post(
            f"{STAKE_URL}/api/graphql",
            json=payload,
            headers=session_headers,
            impersonate="chrome110"
        )
        print(f"[+] Response for {code}: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[!] Request error: {e}")

async def main():
    client = TelegramClient('stake_bot_telethon', API_ID, API_HASH)
    await client.connect()
    
    print("[*] Fetching last messages from StakecomDailyDrops...")
    entity = await client.get_entity('StakecomDailyDrops')
    
    # Process the most recent message only for testing history
    async for message in client.iter_messages(entity, limit=1):
        code = None
        if message.text:
            match = re.search(r'Code:\s*(stakecom\w+)', message.text, re.IGNORECASE)
            if match:
                code = match.group(1)
                print(f"[!] Found old code in text: {code}")
        
        if code:
            # Using run_in_executor to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, claim_code, code)
    
    print("\n[*] Finished processing history. Bot will now listen for NEW drops.")
    
    @client.on(events.NewMessage(chats=entity))
    async def handler(event):
        code = None
        if event.text:
            match = re.search(r'Code:\s*(stakecom\w+)', event.text, re.IGNORECASE)
            if match:
                code = match.group(1)
                print(f"[!] Found NEW code: {code}")
        
        if not code and event.message.video:
            print("[*] Downloading video...")
            path = await event.download_media()
            # In a real drop, we'd do OCR here
            # For now, just a placeholder as it's a blocking operation
            print("[*] Video processing triggered (placeholder)")
            os.remove(path)

        if code:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, claim_code, code)

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
