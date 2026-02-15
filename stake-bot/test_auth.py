import os
import re
import capsolver
from curl_cffi import requests
from dotenv import load_dotenv

load_dotenv()

# Config
CAPSOLVER_KEY = os.getenv("API_KEY")
STAKE_SESSION = os.getenv("STAKE_SESSION")
STAKE_COOKIE = os.getenv("STAKE_COOKIE")
STAKE_URL = "https://stake.com"

capsolver.api_key = CAPSOLVER_KEY

# Headers setup
session_headers = {
    "x-access-token": STAKE_SESSION,
    "cookie": STAKE_COOKIE,
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_fresh_clearance():
    print("[*] Requesting fresh Cloudflare Clearance from Capsolver...")
    try:
        solution = capsolver.solve({
            "type": "AntiCloudflareTask",
            "websiteURL": STAKE_URL,
        })
        token = solution.get("token")
        if token:
            print(f"[+] New Clearance obtained: {token[:20]}...")
            new_cookie = f"cf_clearance={token}"
            if "cf_clearance=" in session_headers["cookie"]:
                session_headers["cookie"] = re.sub(r"cf_clearance=[^;]+", new_cookie, session_headers["cookie"])
            else:
                session_headers["cookie"] += f"; {new_cookie}"
            return True
    except Exception as e:
        print(f"[!] Capsolver Clearance error: {e}")
    return False

def test_auth(retry=True):
    print("[*] Testing Stake Session...")
    payload = {"query": "{ user { id name email } }"}

    try:
        resp = requests.post(
            f"{STAKE_URL}/api/graphql",
            json=payload,
            headers=session_headers,
            impersonate="chrome110"
        )
        
        if resp.status_code == 403 and "Just a moment" in resp.text and retry:
            print("[!] 403 Forbidden. Cloudflare detected. Attempting bypass...")
            if get_fresh_clearance():
                return test_auth(retry=False)
        
        if resp.status_code == 200:
            data = resp.json()
            if "data" in data and data["data"].get("user"):
                user = data["data"]["user"]
                print(f"[+] Auth Success! Logged in as: {user.get('name')}")
                return True
            else:
                print(f"[!] Session Invalid. Response: {resp.text}")
        else:
            print(f"[!] HTTP Error {resp.status_code}")
            
    except Exception as e:
        print(f"[!] Request error: {e}")
    return False

if __name__ == "__main__":
    if test_auth():
        print("\n[READY] The bot is authorized and bypass logic is working.")
    else:
        print("\n[CRITICAL] Auth failed. Check if STAKE_SESSION is correct in .env.")
