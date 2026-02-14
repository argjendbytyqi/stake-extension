import asyncio
import os
import re
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from telethon import TelegramClient, events
from dotenv import load_dotenv

# Load env from the same folder
load_dotenv()

# --- CONFIGURATION ---
API_ID = 39003063
API_HASH = 'b19980f250f5053c4be259bb05668a35'
CHANNEL_USERNAME = 'StakecomDailyDrops'

# Simple License DB (In-memory for testing)
VALID_KEYS = ["ADMIN-TEST-KEY", "USER-12345"]

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    print("🚀 Starting Telegram Monitor...")
    await client.start()
    asyncio.create_task(client.run_until_disconnected())
    yield
    # Shutdown logic (optional)
    await client.disconnect()

app = FastAPI(lifespan=lifespan)

# Remove the old startup event
# @app.on_event("startup")
# async def startup_event():
#     ...

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)