import asyncio
import os
import re
import json
import logging
import threading
import cv2
import pytesseract
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from telethon import TelegramClient, events
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# Enable logging
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# --- CONFIGURATION ---
API_ID = 39003063
API_HASH = 'b19980f250f5053c4be259bb05668a35'
CHANNELS = ['StakecomDailyDrops', 'stakecomhighrollers']
VALID_KEYS = ["ADMIN-TEST-KEY", "USER-12345"]

# Global store for dashboard
stats = {
    "total_claims": 0,
    "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "history": []
}

# --- OCR LOGIC ---
def extract_text_from_media(file_path):
    """Extracts text from video frames using OCR."""
    logger.info(f"🎞️ Analyzing video: {file_path}")
    try:
        cap = cv2.VideoCapture(file_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        extracted_text = ""
        # Check every 15th frame to be fast
        for idx in range(0, total_frames, 15):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            success, image = cap.read()
            if success:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                # Tesseract OCR
                extracted_text += " " + pytesseract.image_to_string(gray)
                # Try thresholding for cleaner OCR
                _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                extracted_text += " " + pytesseract.image_to_string(thresh)
        cap.release()
        return extracted_text
    except Exception as e:
        logger.error(f"❌ OCR Error: {e}")
        return ""

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
        for key in list(self.active_connections.keys()):
            try:
                connection = self.active_connections.get(key)
                if connection:
                    asyncio.create_task(connection.send_text(message))
            except: pass

manager = ConnectionManager()

# --- TELEGRAM WORKER ---
def run_telegram_worker(loop, broadcaster_manager):
    asyncio.set_event_loop(loop)
    client = TelegramClient('broadcaster_session', API_ID, API_HASH)

    @client.on(events.NewMessage(chats=CHANNELS))
    async def handler(event):
        try:
            chat = await event.get_chat()
            channel_name = getattr(chat, 'username', 'Unknown')
            text = (event.raw_text or "").replace('\n', ' ')
            
            # 1. Check for text codes
            codes = re.findall(r'stakecom[a-zA-Z0-9]+', text) or re.findall(r'\b[a-zA-Z0-9]{8,20}\b', text)
            
            # 2. Check for media codes (Videos/Images)
            if not codes and event.media:
                logger.info(f"📦 Media detected in {channel_name}, downloading...")
                file_path = await event.download_media(file="temp_media")
                media_text = extract_text_from_media(file_path)
                codes = re.findall(r'stakecom[a-zA-Z0-9]+', media_text) or re.findall(r'\b[a-zA-Z0-9]{8,20}\b', media_text)
                if os.path.exists(file_path): os.remove(file_path)

            valid_codes = [c for c in set(codes) if not c.isdigit() and 'telegram' not in c.lower()]
            for code in valid_codes:
                logger.info(f"🔥 NEW DROP [{channel_name}]: {code}")
                asyncio.run_coroutine_threadsafe(broadcaster_manager.broadcast_drop(code, channel_name), main_loop)
        except Exception as e: logger.error(f"❌ Telegram Event Error: {e}")

    async def main_worker():
        await client.start()
        logger.info("✅ [TELEGRAM] Worker Active.")
        
        # Initial history check
        logger.info("🧪 [STARTUP] Waiting 15s for extensions before history check...")
        await asyncio.sleep(15)
        
        for channel in CHANNELS:
            try:
                logger.info(f"🔍 [STARTUP] Checking history for @{channel}...")
                async for message in client.iter_messages(channel, limit=1):
                    text = (message.text or "").replace('\n', ' ')
                    codes = re.findall(r'stakecom[a-zA-Z0-9]+', text) or re.findall(r'\b[a-zA-Z0-9]{8,20}\b', text)
                    
                    if not codes and message.media:
                        file_path = await message.download_media(file="temp_startup")
                        media_text = extract_text_from_media(file_path)
                        codes = re.findall(r'stakecom[a-zA-Z0-9]+', media_text) or re.findall(r'\b[a-zA-Z0-9]{8,20}\b', media_text)
                        if os.path.exists(file_path): os.remove(file_path)

                    valid = [c for c in set(codes) if not c.isdigit() and 'telegram' not in c.lower()]
                    if valid:
                        logger.info(f"🧪 [STARTUP] Found code in history: {valid[0]}")
                        asyncio.run_coroutine_threadsafe(broadcaster_manager.broadcast_drop(valid[0], channel), main_loop)
                    else:
                        logger.info(f"ℹ️ [STARTUP] No code found in last message of @{channel}")
            except Exception as e:
                logger.error(f"⚠️ [STARTUP] History check failed for {channel}: {e}")
        
        logger.info("📡 [TELEGRAM] Continuous monitoring enabled.")
        await client.run_until_disconnected()

    loop.run_until_complete(main_worker())

# --- LIFESPAN ---
main_loop = None
@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop
    main_loop = asyncio.get_running_loop()
    worker_loop = asyncio.new_event_loop()
    threading.Thread(target=run_telegram_worker, args=(worker_loop, manager), daemon=True).start()
    yield

app = FastAPI(lifespan=lifespan)

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def admin_dashboard():
    history_html = "".join([f"<tr><td>{h['time']}</td><td>{h['key']}</td><td>{h['channel']}</td><td>{h['code']}</td><td>{h['status']}</td></tr>" for h in reversed(stats['history'][-20:])])
    users_html = "".join([f"<li>{key} <span style='color:#00e676'>● Online</span></li>" for key in manager.active_connections.keys()])
    
    return f"""
    <html>
    <head><title>Stake Bot Admin</title><style>
        body {{ font-family: sans-serif; background: #0f212e; color: white; padding: 40px; }}
        .card {{ background: #1a2c38; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #243b4a; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #243b4a; }}
        th {{ color: #1475e1; }}
        h1 {{ color: #1475e1; }}
        .stat {{ font-size: 24px; font-weight: bold; color: #00e676; }}
    </style></head>
    <body>
        <h1>Didier Drogba Broadcaster</h1>
        <div style="display: flex; gap: 20px;">
            <div class="card" style="flex: 1;">
                <h3>Status</h3>
                <p>Server Up Since: {stats['start_time']}</p>
                <p>Total Claims Processed: <span class="stat">{stats['total_claims']}</span></p>
            </div>
            <div class="card" style="flex: 1;">
                <h3>Active Extensions</h3>
                <ul>{users_html or "No users connected"}</ul>
            </div>
        </div>
        <div class="card">
            <h3>Recent Claim History</h3>
            <table>
                <tr><th>Time</th><th>User Key</th><th>Channel</th><th>Code</th><th>Status</th></tr>
                {history_html or "<tr><td colspan='5'>No claims recorded yet.</td></tr>"}
            </table>
        </div>
        <script>setTimeout(() => location.reload(), 5000);</script>
    </body>
    </html>
    """

@app.websocket("/ws/{license_key}")
async def websocket_endpoint(websocket: WebSocket, license_key: str):
    if license_key not in VALID_KEYS:
        await websocket.close(code=4003)
        return
    await manager.connect(license_key, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "REPORT":
                stats["total_claims"] += 1
                stats["history"].append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "key": license_key,
                    "channel": msg.get("channel"),
                    "code": msg.get("code"),
                    "status": msg.get("status")
                })
    except: manager.disconnect(license_key)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)