import os
import logging
from telethon import TelegramClient
from dotenv import load_dotenv

# Enable very detailed logging
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.DEBUG)

load_dotenv()

API_ID = 39003063
API_HASH = 'b19980f250f5053c4be259bb05668a35'

def main():
    # 1. Clean up old session to start fresh
    if os.path.exists('broadcaster_session.session'):
        print("DEBUG: Removing old session file...")
        os.remove('broadcaster_session.session')

    print("DEBUG: Starting synchronous login flow...")
    
    # 2. Use the high-level start() method which handles connection/auth automatically
    # We use sync mode here to ensure the terminal prompts are visible
    client = TelegramClient('broadcaster_session', API_ID, API_HASH)
    
    with client:
        print("\n" + "="*30)
        print("✅ CONNECTION SUCCESSFUL!")
        print("="*30)
        client.send_message('me', 'Hello from Stake-Extension Broadcaster on EC2!')
        print("Verified: Sent a test message to your 'Saved Messages'.")
        print("Login complete. You can now run 'python3 server.py'.")

if __name__ == "__main__":
    main()