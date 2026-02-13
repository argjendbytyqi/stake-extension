# Stake Automation Memory (Didier Drogba)

## Setup Overview
- **Agent Name:** Didier Drogba ⚽
- **Task:** Monitor `@StakecomDailyDrops` on Telegram and automatically claim bonus codes on `stake.com`.
- **Browser Config:** Uses a headed Chrome instance with remote debugging on port `9222` and a persistent data directory at `/home/argjend/.openclaw/workspace/chrome_data`.

## Critical Technical Details
- **Code Casing:** Codes must be sent with **exact casing** (case-sensitive).
- **Security Bypass:** Cloudflare Turnstile requires a manual solve in the headed browser if it triggers.
- **Claim Logic:**
  - Identifies the "Bonus Drop" input by excluding the "Welcome Offer" container.
  - Uses multiple click fallbacks (Native Click, MouseEvents, Form Submit, and Keyboard Enter).
  - Automatically dismisses "Bonus unavailable" modals after reading the result.

## Active Command
To restart the browser if closed:
`google-chrome --remote-debugging-port=9222 --user-data-dir=/home/argjend/.openclaw/workspace/chrome_data`

## Session Info
- Injected user session via cookies and `x-access-token` on 2026-02-13.
- Monitor script: `stake_monitor.py`
- Debug logs: `debug.log`
