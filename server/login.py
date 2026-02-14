from telethon import TelegramClient
import os
import logging
from dotenv import load_dotenv

# Enable high-level logging to see what's happening
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)

load_dotenv()

API_ID = 39003063
API_HASH = 'b19980f250f5053c4be259bb05668a35'

# Try connecting on port 80 if 443 is blocked/slow
client = TelegramClient('broadcaster_session', API_ID, API_HASH, connection_retries=3)

async def main():
    print("DEBUG: Starting connection attempt...")
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("AUTH: Not authorized. Sending code request...")
            # This will prompt for phone number in the terminal
            await client.start()
        print("✅ Login successful! Session saved.")
    except Exception as e:
        print(f"❌ Error during connection: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())