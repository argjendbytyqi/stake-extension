let socket = null;
let isConnected = false;

function connect() {
  chrome.storage.local.get(['licenseKey'], (res) => {
    const key = res.licenseKey;
    if (!key) return;

    console.log("🔗 Connecting to server with key:", key);
    // Replace with your EC2 IP later
    socket = new WebSocket(`ws://18.199.98.207:8000/ws/${key}`);

    socket.onopen = () => {
      isConnected = true;
      console.log("✅ Connected to Stake Broadcaster");
      
      // Professional Heartbeat: Randomized between 20-30s to prevent server spikes
      const scheduleNextPing = () => {
        const jitter = Math.floor(Math.random() * 10000); // 0-10 seconds
        setTimeout(() => {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send("ping");
            scheduleNextPing();
          }
        }, 20000 + jitter);
      };
      scheduleNextPing();
    };

    socket.onmessage = async (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "DROP") {
        console.log("🚀 Drop signal received!", data.code);
        await claimDrop(data.code);
      }
    };

    socket.onclose = () => {
      isConnected = false;
      console.log("❌ Connection closed. Retrying in 10s...");
      setTimeout(connect, 10000);
    };

    socket.onerror = (err) => {
      console.error("WebSocket Error:", err);
    };
  });
}

async function claimDrop(code) {
  console.log("🔍 Searching for Stake tabs...");
  const tabs = await chrome.tabs.query({ url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
  
  if (tabs.length === 0) {
    console.error("❌ No Stake tab found. Is stake.com open?");
    return;
  }

  const targetTab = tabs[0];
  console.log("💉 Injecting into tab:", targetTab.id, targetTab.url);

  try {
    await chrome.scripting.executeScript({
      target: { tabId: targetTab.id },
      func: async (dropCode) => {
        const logStyle = "background: #1475e1; color: white; padding: 2px 5px; border-radius: 3px; font-weight: bold;";
        console.log("%c[STAKE-BOT]%c Received Drop Signal: " + dropCode, logStyle, "");
        
        try {
          // Improved token retrieval
          const findToken = () => {
            const keys = ['x-access-token', 'sessionToken', 'token', 'jwt'];
            for (const key of keys) {
              const val = window.localStorage.getItem(key) || window.sessionStorage.getItem(key);
              if (val) return val;
            }
            // Check cookies as last resort
            const cookieMatch = document.cookie.match(/session=([^;]+)/);
            if (cookieMatch) return cookieMatch[1];
            return null;
          };

          let token = findToken();
          
          if (!token) {
            console.error("%c[STAKE-BOT] Error: No token found. Available LocalStorage keys: " + Object.keys(window.localStorage).join(', '), "color: red;");
            const toast = document.createElement('div');
            toast.style = "position:fixed; top:20px; right:20px; background:#ff9800; color:black; padding:15px; z-index:1000000; border-radius:5px; font-weight:bold;";
            toast.textContent = "⚠️ STAKE-BOT: Token not found! Please refresh the page.";
            document.body.appendChild(toast);
            return;
          }

          console.log("%c[STAKE-BOT] Attempting GraphQL Claim...", "color: #00e676;");
          
          const query = `
            mutation ClaimBonusCode($code: String!, $currency: CurrencyEnum!, $turnstileToken: String!) {
              claimBonusCode(code: $code, currency: $currency, turnstileToken: $turnstileToken) {
                ip
              }
            }
          `;

          const response = await fetch('https://stake.com/_api/graphql', {
            method: 'POST',
            headers: {
              'content-type': 'application/json',
              'x-access-token': token,
              'x-language': 'en'
            },
            body: JSON.stringify({
              query: query,
              variables: { 
                code: dropCode,
                currency: 'btc',
                turnstileToken: "" 
              }
            })
          });

          const resJson = await response.json();
          
          if (resJson.errors) {
            const msg = resJson.errors[0].message;
            console.warn("%c[STAKE-BOT] Server Message: " + msg, "color: orange;");
            
            // Critical check: if it's a captcha error, we must use the UI fallback
            if (msg.includes('turnstileToken') || msg.includes('invalid_turnstile')) {
              console.log("%c[STAKE-BOT] Captcha required. Opening redeem UI...", "color: #1475e1;");
              // Use navigation to the direct modal link
              window.location.href = `https://stake.com/settings/offers?code=${dropCode}&modal=redeemBonus`;
            } else {
              // Show other errors (unavailable, claimed, etc) as a toast
              const toast = document.createElement('div');
              toast.style = "position:fixed; top:20px; right:20px; background:#ff5252; color:white; padding:15px; z-index:1000000; border-radius:5px; font-weight:bold; box-shadow: 0 4px 15px rgba(0,0,0,0.3);";
              toast.textContent = "❌ Drop Fail: " + msg;
              document.body.appendChild(toast);
              setTimeout(() => toast.remove(), 5000);
            }
          } else {
            console.log("%c[STAKE-BOT] ✅ SUCCESS! Drop Claimed.", "color: #00e676; font-size: 14px;");
            const toast = document.createElement('div');
            toast.style = "position:fixed; top:20px; right:20px; background:#00e676; color:black; padding:20px; z-index:1000000; border-radius:10px; font-weight:bold; box-shadow: 0 4px 20px rgba(0,0,0,0.4);";
            toast.innerHTML = "💰 STAKE DROP CLAIMED!<br><span style='font-size:12px; font-weight:normal;'>" + dropCode + "</span>";
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 10000);
          }
        } catch (e) {
          console.error("%c[STAKE-BOT] Fatal Execution Error:", "color: red;", e.message);
        }
      },
      args: [code]
    });
  } catch (err) {
    console.error("❌ Injection failed:", err);
  }
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'GET_STATUS') {
    sendResponse({ connected: isConnected });
  } else if (request.action === 'RECONNECT') {
    if (socket) socket.close();
    connect();
  }
});

// Start connection
connect();

// Auto-click logic for when the page redirects to the offers modal
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  // Only inject if the URL contains redeemBonus and the status is 'complete'
  // Also use a simple check to prevent double injection on the same tab/URL
  if (changeInfo.status === 'complete' && tab.url && tab.url.includes('redeemBonus')) {
    chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: () => {
        if (window.stakeBotInjected) return;
        window.stakeBotInjected = true;
        
        console.log("%c[STAKE-BOT] UI Mode Active. Watching for button...", "color: #1475e1; font-weight: bold;");
        
        const autoClick = setInterval(() => {
          const bodyText = document.body.innerText;
          
          // 1. Check for success/error text to close modal
          const isFinished = /invalid|unavailable|claimed|Success|found/i.test(bodyText);
          
          if (isFinished) {
            console.log("%c[STAKE-BOT] Process finished. Closing modal in 4s...", "color: orange;");
            setTimeout(() => {
              const closeBtn = document.querySelector('button[aria-label="Close"]') || 
                               document.querySelector('.modal-close') || 
                               Array.from(document.querySelectorAll('button')).find(b => /Dismiss|Close/i.test(b.innerText));
              
              if (closeBtn) {
                closeBtn.click();
              } else {
                window.location.href = 'https://stake.com/settings/offers';
              }
              window.stakeBotInjected = false;
            }, 4000);
            clearInterval(autoClick);
            return;
          }

          // 2. Look for the action button
          const btn = Array.from(document.querySelectorAll('button')).find(b => 
            /Redeem|Submit|Claim/i.test(b.innerText) && b.offsetParent !== null && !b.disabled
          );
          
          if (btn) {
            console.log("%c[STAKE-BOT] Button found! Clicking...", "color: #00e676;");
            btn.click();
          }
        }, 1000);

        setTimeout(() => {
          clearInterval(autoClick);
          window.stakeBotInjected = false;
        }, 30000);
      }
    });
  }
});