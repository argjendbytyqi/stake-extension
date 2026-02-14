from telethon import TelegramClient
import os
from dotenv import load_dotenv

load_dotenv()

API_ID = 39003063
API_HASH = 'b19980f250f5053c4be259bb05668a35'

client = TelegramClient('broadcaster_session', API_ID, API_HASH)

async def main():
    print("Connecting to Telegram...")
    await client.start()
    print("✅ Login successful! Session saved to 'broadcaster_session.session'.")
    print("You can now run 'python3 server.py'.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())