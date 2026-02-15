import asyncio
import os
import re
import json
import logging
import threading
import sqlite3
import secrets
import cv2
import pytesseract
import jwt
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from telethon import TelegramClient, events
from dotenv import load_dotenv
from contextlib import asynccontextmanager

# Enable logging
logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# --- CONFIGURATION ---
API_ID = os.getenv("TG_API_ID", "39003063")
API_HASH = os.getenv("TG_API_HASH", "b19980f250f5053c4be259bb05668a35")
CHANNELS = ['StakecomDailyDrops', 'stakecomhighrollers']
DB_PATH = 'licenses.db'
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-immediately")
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
ALGORITHM = "HS256"

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    # Added expires_at and created_at
    conn.execute('''CREATE TABLE IF NOT EXISTS licenses 
                    (key TEXT PRIMARY KEY, 
                     status TEXT DEFAULT 'active', 
                     total_claims INTEGER DEFAULT 0,
                     created_at TEXT,
                     expires_at TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS history 
                    (time TEXT, key TEXT, channel TEXT, code TEXT, status TEXT)''')
    conn.commit()
    conn.close()

def generate_key(days: int):
    """Generates a unique key valid for X days."""
    new_key = f"STAKE-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
    created_at = datetime.now()
    expires_at = created_at + timedelta(days=days)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO licenses (key, created_at, expires_at) VALUES (?, ?, ?)",
                 (new_key, created_at.isoformat(), expires_at.isoformat()))
    conn.commit()
    conn.close()
    return new_key

def is_key_valid(key):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT expires_at FROM licenses WHERE key = ? AND status = 'active'", (key,)).fetchone()
    conn.close()
    if not res: return False
    
    expires_at = datetime.fromisoformat(res[0])
    return datetime.now() < expires_at

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

def log_claim(key, channel, code, status):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if this specific code was already successfully claimed by ANYONE
    # Or if this specific license already has an entry for this code
    existing = conn.execute("SELECT 1 FROM history WHERE code = ? AND (status = 'Success' OR key = ?)", (code, key)).fetchone()
    
    if not existing:
        conn.execute("INSERT INTO history VALUES (?, ?, ?, ?, ?)", (now, key, channel, code, status))
        if status == 'Success':
            conn.execute("UPDATE licenses SET total_claims = total_claims + 1 WHERE key = ?", (key,))
        conn.commit()
    conn.close()

init_db()

security = HTTPBasic()

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "admin" or credentials.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- CONNECTION MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, key: str, websocket: WebSocket):
        # OPTION B IMPROVED: Check if connection is actually alive
        if key in self.active_connections:
            old_ws = self.active_connections[key]
            
            # If the new connection is from the SAME IP as the old one,
            # we assume the user refreshed their tab and we let them in.
            if websocket.client.host == old_ws.client.host:
                logger.info(f"♻️ Auto-refreshing connection for {key} from same IP")
                try: await old_ws.close()
                except: pass
                if key in self.active_connections: del self.active_connections[key]
            else:
                try:
                    # Use a small timeout for the check to avoid blocking
                    await asyncio.wait_for(old_ws.send_text(json.dumps({"type": "ping"})), timeout=0.3)
                    logger.warning(f"🚫 Connection rejected: {key} is already active on another device")
                    # Try to accept and then close to provide a clear error message to the client
                    await websocket.accept()
                    await websocket.send_text(json.dumps({"type": "ERROR", "message": "License already in use"}))
                    await websocket.close(code=4003)
                    return False
                except Exception as e:
                    # Old connection is dead or timed out, clean it up
                    logger.info(f"♻️ Cleaning up stale connection for {key}")
                    if key in self.active_connections:
                        del self.active_connections[key]
            
        await websocket.accept()
        self.active_connections[key] = websocket
        logger.info(f"➕ User connected: {key}")
        return True

    def disconnect(self, key: str):
        if key in self.active_connections:
            del self.active_connections[key]
            logger.info(f"➖ User disconnected: {key}")

    async def broadcast_drop(self, code: str, channel: str):
        logger.info(f"📡 [{channel}] Broadcasting code: {code} to {len(self.active_connections)} users")
        
        # Determine priority based on channel name
        priority = 1 if 'highrollers' in channel.lower() else 2
        
        message = json.dumps({
            "type": "DROP", 
            "code": code, 
            "channel": channel,
            "priority": priority
        })
        
        for key in list(self.active_connections.keys()):
            try:
                connection = self.active_connections.get(key)
                if connection: asyncio.create_task(connection.send_text(message))
            except: pass

manager = ConnectionManager()

# --- OCR LOGIC ---
def extract_text_from_media(file_path):
    try:
        cap = cv2.VideoCapture(file_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        extracted_text = ""
        for idx in range(0, total_frames, 15):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            success, image = cap.read()
            if success:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                extracted_text += " " + pytesseract.image_to_string(gray)
                _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                extracted_text += " " + pytesseract.image_to_string(thresh)
        cap.release()
        return extracted_text
    except Exception as e:
        logger.error(f"❌ OCR Error: {e}")
        return ""

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
            
            # FAST PATH: Check text first and broadcast immediately
            codes = re.findall(r'stakecom[a-zA-Z0-9]+', text) or re.findall(r'\b[a-zA-Z0-9]{8,20}\b', text)
            valid_codes = [c for c in set(codes) if not c.isdigit() and 'telegram' not in c.lower()]
            
            for code in valid_codes:
                asyncio.run_coroutine_threadsafe(broadcaster_manager.broadcast_drop(code, channel_name), main_loop)
            
            # SLOW PATH: OCR (only if no codes found in text and media exists)
            if not valid_codes and event.media:
                file_path = await event.download_media(file="temp_media")
                
                # Check if it's an image first (faster)
                is_image = any(file_path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp'])
                
                if is_image:
                    image = cv2.imread(file_path)
                    if image is not None:
                        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                        media_text = pytesseract.image_to_string(gray)
                        # Add a thresholded version for better accuracy
                        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                        media_text += " " + pytesseract.image_to_string(thresh)
                else:
                    # It's a video, use the original frame-by-frame logic
                    media_text = extract_text_from_media(file_path)
                
                codes = re.findall(r'stakecom[a-zA-Z0-9]+', media_text) or re.findall(r'\b[a-zA-Z0-9]{8,20}\b', media_text)
                if os.path.exists(file_path): os.remove(file_path)
                
                valid_ocr_codes = [c for c in set(codes) if not c.isdigit() and 'telegram' not in c.lower()]
                for code in valid_ocr_codes:
                    asyncio.run_coroutine_threadsafe(broadcaster_manager.broadcast_drop(code, channel_name), main_loop)
                    
        except Exception as e: logger.error(f"❌ Telegram Event Error: {e}")

    async def main_worker():
        await client.start()
        logger.info("✅ [TELEGRAM] Worker Active.")
        await asyncio.sleep(15)
        for channel in CHANNELS:
            try:
                async for message in client.iter_messages(channel, limit=1):
                    text = (message.text or "").replace('\n', ' ')
                    codes = re.findall(r'stakecom[a-zA-Z0-9]+', text) or re.findall(r'\b[a-zA-Z0-9]{8,20}\b', text)
                    if not codes and message.media:
                        file_path = await message.download_media(file="temp_startup")
                        media_text = extract_text_from_media(file_path)
                        codes = re.findall(r'stakecom[a-zA-Z0-9]+', media_text) or re.findall(r'\b[a-zA-Z0-9]{8,20}\b', media_text)
                        if os.path.exists(file_path): os.remove(file_path)
                    valid = [c for c in set(codes) if not c.isdigit() and 'telegram' not in c.lower()]
                    if valid: asyncio.run_coroutine_threadsafe(broadcaster_manager.broadcast_drop(valid[0], channel), main_loop)
            except: pass
        await client.run_until_disconnected()

    loop.run_until_complete(main_worker())

# --- LIFESPAN ---
main_loop = None
@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop
    main_loop = asyncio.get_running_loop()
    threading.Thread(target=run_telegram_worker, args=(asyncio.new_event_loop(), manager), daemon=True).start()
    yield

app = FastAPI(lifespan=lifespan)

# --- CORS SETTINGS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (required for Chrome Extensions)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def admin_dashboard(page: int = 1, search: str = "", username: str = Depends(authenticate)):
    conn = sqlite3.connect(DB_PATH)
    limit = 10
    offset = (page - 1) * limit
    
    # History with pagination and search
    query = "SELECT * FROM history"
    params = []
    if search:
        query += " WHERE key LIKE ? OR code LIKE ? OR channel LIKE ? OR status LIKE ?"
        params = [f"%{search}%"] * 4
    
    total_rows = conn.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]
    total_pages = (total_rows + limit - 1) // limit
    
    history = conn.execute(f"{query} ORDER BY rowid DESC LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
    licenses = conn.execute("SELECT key, expires_at, total_claims FROM licenses").fetchall()
    conn.close()

    history_html = "".join([f"<tr><td>{h[0]}</td><td>{h[1]}</td><td>{h[2]}</td><td>{h[3]}</td><td>{h[4]}</td></tr>" for h in history])
    
    pagination_html = f"<div style='margin-top:10px;'>"
    if page > 1: pagination_html += f"<a href='/?page={page-1}&search={search}' class='btn' style='padding:5px 10px; font-size:12px;'>Previous</a>"
    pagination_html += f"<span style='margin: 0 15px;'>Page {page} of {total_pages}</span>"
    if page < total_pages: pagination_html += f"<a href='/?page={page+1}&search={search}' class='btn' style='padding:5px 10px; font-size:12px;'>Next</a>"
    pagination_html += "</div>"

    licenses_html = ""
    for l in licenses:
        exp = datetime.fromisoformat(l[1]).strftime("%Y-%m-%d")
        color = "#00e676" if datetime.now() < datetime.fromisoformat(l[1]) else "#ff5252"
        status = manager.active_connections.get(l[0]) and "● Online" or "○ Offline"
        status_color = manager.active_connections.get(l[0]) and "#00e676" or "#94a3b8"
        licenses_html += f"<tr><td>{l[0]}</td><td style='color:{color}'>{exp}</td><td>{l[2]}</td><td style='color:{status_color}'>{status}</td><td><a href='/admin/delete/{l[0]}' style='color:#ff5252; text-decoration:none;' onclick='return confirm(\"Are you sure?\")'>Delete</a></td></tr>"
    
    return f"""
    <html><head><title>Stake Bot Admin</title><style>
        body {{ font-family: sans-serif; background: #0f212e; color: white; padding: 40px; }}
        .card {{ background: #1a2c38; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #243b4a; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #243b4a; }}
        th {{ color: #1475e1; font-size: 12px; text-transform: uppercase; }}
        h1, h2 {{ color: #1475e1; }} .stat {{ font-size: 24px; font-weight: bold; color: #00e676; }}
        .btn {{ background: #1475e1; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold; margin-right: 10px; display: inline-block; }}
        input[type="text"] {{ background: #0f212e; border: 1px solid #243b4a; color: white; padding: 8px; border-radius: 5px; width: 300px; }}
    </style></head><body>
        <h1>Didier Drogba Broadcaster</h1>
        <div class="card">
            <h2>Generate New License</h2>
            <a href="/admin/generate/1" class="btn">1 Day</a>
            <a href="/admin/generate/7" class="btn">7 Days</a>
            <a href="/admin/generate/30" class="btn">30 Days</a>
            <a href="/admin/generate/90" class="btn">90 Days</a>
            <a href="/admin/generate/365" class="btn">1 Year</a>
        </div>
        <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h2>Active Licenses</h2>
                <a href="/admin/reset-history" class="btn" style="background:#ff5252; font-size:12px; padding:5px 10px;" onclick="return confirm('This will delete ALL claim history and reset counters to 0. Are you sure?')">Reset All History</a>
            </div>
            <table><tr><th>License Key</th><th>Expires At</th><th>Total Claims</th><th>Status</th><th>Action</th></tr>{licenses_html}</table>
        </div>
        <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h2>Recent Claim History</h2>
                <form action="/" method="get">
                    <input type="text" name="search" placeholder="Search by Key, Code, Status..." value="{search}">
                    <button type="submit" class="btn" style="padding:8px 15px;">Search</button>
                </form>
            </div>
            <table><tr><th>Time</th><th>User Key</th><th>Channel</th><th>Code</th><th>Status</th></tr>{history_html}</table>
            {pagination_html}
        </div>
        <script>
            let autoReload = {str(not bool(search)).lower()};
            setInterval(() => {{ if(autoReload) location.reload(); }}, 15000);
            function toggleReload() {{ autoReload = !autoReload; document.getElementById('reload-btn').innerText = autoReload ? 'Auto-Reload: ON' : 'Auto-Reload: OFF'; }}
        </script>
        <button id="reload-btn" onclick="toggleReload()" class="btn" style="background:#334155;">Auto-Reload: {'ON' if not search else 'OFF'}</button>
    </body></html>"""

@app.get("/admin/reset-history")
async def admin_reset_history(username: str = Depends(authenticate)):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM history")
    conn.execute("UPDATE licenses SET total_claims = 0")
    conn.commit()
    conn.close()
    return HTMLResponse("<html><body style='background:#0f212e;color:white;font-family:sans-serif;padding:50px;'><h1>History Reset Successful</h1><p>All claim records have been deleted and license counters reset to 0.</p><br><a href='/' style='color:#1475e1;'>Back to Dashboard</a></body></html>")

@app.get("/admin/delete/{license_key}")
async def admin_delete(license_key: str, username: str = Depends(authenticate)):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM licenses WHERE key = ?", (license_key,))
    conn.commit()
    conn.close()
    return HTMLResponse("<html><body style='background:#0f212e;color:white;font-family:sans-serif;padding:50px;'><h1>License Deleted</h1><br><a href='/' style='color:#1475e1;'>Back to Dashboard</a></body></html>")

@app.get("/admin/generate/{days}")
async def admin_generate(days: int, username: str = Depends(authenticate)):
    key = generate_key(days)
    return HTMLResponse(f"<html><body style='background:#0f212e;color:white;font-family:sans-serif;padding:50px;'><h1>Key Generated!</h1><p style='font-size:24px;color:#00e676;'>{key}</p><br><a href='/' style='color:#1475e1;'>Back to Dashboard</a></body></html>")

@app.get("/auth/token")
async def get_token(license_key: str):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT expires_at, total_claims FROM licenses WHERE key = ? AND status = 'active'", (license_key,)).fetchone()
    conn.close()
    
    if not res:
        raise HTTPException(status_code=403, detail="Invalid or expired license key")
        
    token = create_access_token(data={"sub": license_key})
    return {
        "token": token, 
        "expires_at": res[0],
        "total_claims": res[1]
    }

@app.websocket("/ws/{license_key}")
async def websocket_endpoint(websocket: WebSocket, license_key: str):
    # FALLBACK: Support old direct license key connection for existing users
    if not is_key_valid(license_key):
        await websocket.close(code=4003)
        return
        
    if not await manager.connect(license_key, websocket):
        return

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "REPORT":
                log_claim(license_key, msg.get("channel"), msg.get("code"), msg.get("status"))
    except: manager.disconnect(license_key)

@app.websocket("/ws")
async def websocket_endpoint_token(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        license_key = payload.get("sub")
        if license_key is None: raise Exception("Invalid token")
    except:
        await websocket.close(code=4003)
        return

    if not await manager.connect(license_key, websocket):
        return

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "REPORT":
                log_claim(license_key, msg.get("channel"), msg.get("code"), msg.get("status"))
    except: manager.disconnect(license_key)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)