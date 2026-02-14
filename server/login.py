from telethon import TelegramClient
import os
import logging
from dotenv import load_dotenv
import asyncio

# Enable high-level logging
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.INFO)

load_dotenv()

API_ID = 39003063
API_HASH = 'b19980f250f5053c4be259bb05668a35'

client = TelegramClient('broadcaster_session', API_ID, API_HASH)

async def main():
    print("DEBUG: Starting manual auth flow...")
    await client.connect()
    
    if not await client.is_user_authorized():
        phone = input("Please enter your phone number (with country code, e.g. +123456789): ")
        await client.send_code_request(phone)
        code = input("Please enter the code you received: ")
        try:
            await client.sign_in(phone, code)
        except Exception as e:
            if "password" in str(e).lower():
                password = input("Please enter your 2FA password: ")
                await client.sign_in(password=password)
            else:
                raise e
                
    print("✅ Login successful! Session saved.")

if __name__ == "__main__":
    asyncio.run(main())