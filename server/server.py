import asyncio
import os
import re
import json
import logging
import threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from telethon import TelegramClient, events, sync
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# Enable logging
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load env
load_dotenv()

# --- CONFIGURATION ---
API_ID = 39003063
API_HASH = 'b19980f250f5053c4be259bb05668a35'
CHANNELS = ['StakecomDailyDrops', 'stakecomhighrollers']
VALID_KEYS = ["ADMIN-TEST-KEY", "USER-12345"]

# --- CONNECTION MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, key: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[key] = websocket
        logger.info(f"➕ User connected: {key}")

    def disconnect(self, key: str):
        if key in self.active_connections:
            del self.active_connections[key]
            logger.info(f"➖ User disconnected: {key}")

    async def broadcast_drop(self, code: str, channel: str):
        logger.info(f"📡 [{channel}] Broadcasting code: {code} to {len(self.active_connections)} users")
        message = json.dumps({"type": "DROP", "code": code, "channel": channel})
        
        # Use a copy of keys to avoid modification errors during iteration
        for key in list(self.active_connections.keys()):
            try:
                connection = self.active_connections.get(key)
                if connection:
                    # We use a non-blocking task for each send
                    asyncio.create_task(connection.send_text(message))
            except:
                pass

manager = ConnectionManager()

# --- TELEGRAM WORKER (THREADED) ---
def run_telegram_worker(loop, broadcaster_manager):
    """Runs in a separate thread to prevent FastAPI event loop blocking."""
    asyncio.set_event_loop(loop)
    
    client = TelegramClient('broadcaster_session', API_ID, API_HASH)

    @client.on(events.NewMessage(chats=CHANNELS))
    async def handler(event):
        try:
            chat = await event.get_chat()
            channel_name = getattr(chat, 'username', 'Unknown')
            text = (event.raw_text or "").replace('\n', ' ')
            codes = re.findall(r'stakecom[a-zA-Z0-9]+', text) or re.findall(r'\b[a-zA-Z0-9]{8,20}\b', text)
            
            valid_codes = [c for c in set(codes) if not c.isdigit() and 'telegram' not in c.lower()]
            for code in valid_codes:
                logger.info(f"🔥 NEW DROP [{channel_name}]: {code}")
                # Schedule the broadcast in the MAIN FastAPI loop
                asyncio.run_coroutine_threadsafe(
                    broadcaster_manager.broadcast_drop(code, channel_name), 
                    main_loop
                )
        except Exception as e:
            logger.error(f"❌ Telegram Event Error: {e}")

    async def main_worker():
        logger.info("🚀 [TELEGRAM] Starting worker...")
        try:
            await client.start()
            logger.info("✅ [TELEGRAM] Connection verified and authorized.")
            
            # Initial history check
            for channel in CHANNELS:
                async for message in client.iter_messages(channel, limit=1):
                    text = (message.text or "").replace('\n', ' ')
                    codes = re.findall(r'stakecom[a-zA-Z0-9]+', text) or re.findall(r'\b[a-zA-Z0-9]{8,20}\b', text)
                    valid = [c for c in set(codes) if not c.isdigit() and 'telegram' not in c.lower()]
                    if valid:
                        logger.info(f"🧪 [STARTUP] Found code in @{channel}: {valid[0]}")
                        asyncio.run_coroutine_threadsafe(
                            broadcaster_manager.broadcast_drop(valid[0], channel), 
                            main_loop
                        )

            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"❌ [TELEGRAM] Worker Fatal Error: {e}")

    loop.run_until_complete(main_worker())

# --- LIFESPAN HANDLER ---
main_loop = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop
    main_loop = asyncio.get_running_loop()
    
    # Start Telegram in a dedicated thread
    worker_loop = asyncio.new_event_loop()
    worker_thread = threading.Thread(target=run_telegram_worker, args=(worker_loop, manager), daemon=True)
    worker_thread.start()
    
    yield
    logger.info("🛑 [SERVER] Shutting down...")

app = FastAPI(lifespan=lifespan)

# --- ROUTES ---
@app.get("/")
async def root():
    return {"status": "Stake Broadcaster Online", "users": len(manager.active_connections)}

@app.get("/test-drop/{channel}/{code}")
async def test_drop(channel: str, code: str):
    logger.info(f"🧪 [MANUAL] Triggered: {code} for {channel}")
    await manager.broadcast_drop(code, channel)
    return {"status": "Broadcasted", "code": code, "channel": channel}

@app.websocket("/ws/{license_key}")
async def websocket_endpoint(websocket: WebSocket, license_key: str):
    if license_key not in VALID_KEYS:
        await websocket.close(code=4003) 
        return

    await manager.connect(license_key, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(license_key)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)