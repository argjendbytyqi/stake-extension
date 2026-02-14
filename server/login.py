import os
import telethon.sync
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()

API_ID = 39003063
API_HASH = 'b19980f250f5053c4be259bb05668a35'

def main():
    # 1. Clean up old session
    if os.path.exists('broadcaster_session.session'):
        os.remove('broadcaster_session.session')

    print("--- TELEGRAM LOGIN ---")
    print("Connecting...")
    
    # 2. Start the client in SYNC mode
    client = TelegramClient('broadcaster_session', API_ID, API_HASH)
    
    try:
        client.start()
        print("\n" + "="*30)
        print("✅ LOGIN SUCCESSFUL!")
        print("="*30)
        print("Session saved. You can now run 'python3 server.py'.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()