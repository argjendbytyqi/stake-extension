# Stake Extension Project

High-speed automatic drop claiming for Stake using a WebSocket-to-Extension architecture.

## Folder Structure
- `/extension`: The Chrome extension (Manifest V3).
- `/server`: The Python backend (Broadcaster + Monitor).

## Setup Instructions

### 1. The Server (Backend)
Navigate to the `/server` folder and install dependencies:
```bash
pip install -r requirements.txt
python server.py
```
*Note: On first run, it will ask you to log in to Telegram.*

### 2. The Extension (Frontend)
1. Open Chrome and go to `chrome://extensions`.
2. Enable **Developer Mode** (top right).
3. Click **Load Unpacked**.
4. Select the `stake-extension/extension` folder.
5. Click the extension icon in your toolbar.
6. Enter the test license key: `ADMIN-TEST-KEY`.
7. Keep at least one `stake.com` tab open.

## How it works
1. Your server monitors the Telegram channel.
2. When a code drops, the server sends a signal via WebSocket to every connected extension.
3. The extension instantly executes a background GraphQL claim in the user's active Stake tab.
4. The user sees a "💰 Stake Drop Claimed" alert.
