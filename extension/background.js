let socket = null;
let isConnected = false;
let isProcessing = false;
let afkTimer = null;
const dropQueue = [];

const SUCCESS_SOUND_URL = "https://assets.mixkit.co/active_storage/sfx/2017/2017-preview.mp3";

function connect() {
  chrome.storage.local.get(['licenseKey'], (res) => {
    const key = res.licenseKey;
    if (!key) return;

    // 1. Get a short-lived JWT token using the license key
    fetch(`http://18.199.98.207:8000/auth/token?license_key=${key}`)
      .then(r => r.json())
      .then(data => {
        if (!data.token) return;

        // 2. Connect to WebSocket using the token
        socket = new WebSocket(`ws://18.199.98.207:8000/ws?token=${data.token}`);

        socket.onopen = () => {
          isConnected = true;
          console.log("✅ Connected to Stake Broadcaster (via Token)");
          setupAFK();
          const scheduleNextPing = () => {
            setTimeout(() => {
              if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: "ping" }));
                console.log("📤 WebSocket Ping Sent");
                scheduleNextPing();
              }
            }, 25000);
          };
          scheduleNextPing();
        };

        socket.onmessage = async (event) => {
          if (event.data === "pong") return;
          try {
            const data = JSON.parse(event.data);
            if (data.type === "DROP") {
              console.log(`📡 Signal: ${data.channel} -> ${data.code} (Priority: ${data.priority || 2})`);
              
              chrome.storage.local.get(['monitorDaily', 'monitorHigh'], async (prefs) => {
                const isDaily = data.channel === 'StakecomDailyDrops';
                const isHigh = data.channel === 'stakecomhighrollers';
                
                if ((isDaily && prefs.monitorDaily !== false) || (isHigh && prefs.monitorHigh === true)) {
                  dropQueue.push({ 
                    code: data.code, 
                    channel: data.channel, 
                    priority: data.priority || 2 
                  });
                  
                  // Sort queue by priority (1 is highest)
                  dropQueue.sort((a, b) => a.priority - b.priority);
                  
                  processQueue();
                }
              });
            }
          } catch (e) {}
        };

        socket.onclose = () => {
          isConnected = false;
          if (afkTimer) clearInterval(afkTimer);
          setTimeout(connect, 10000);
        };
      })
      .catch(e => {
        console.error("Auth error:", e);
        setTimeout(connect, 10000);
      });
  });
}

// ANTI-AFK: Pings Stake API to keep session hot
function setupAFK() {
  if (afkTimer) clearInterval(afkTimer);
  afkTimer = setInterval(async () => {
    const tabs = await chrome.tabs.query({ url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
    if (tabs.length === 0) return;

    // 1. Keep Session Hot
    chrome.scripting.executeScript({
      target: { tabId: tabs[0].id },
      func: async () => {
        try {
          const findToken = () => {
            const keys = ['x-access-token', 'sessionToken', 'token', 'jwt'];
            for (const k of keys) {
              const val = window.localStorage.getItem(k) || window.sessionStorage.getItem(k);
              if (val) return val;
            }
            return null;
          };
          const token = findToken();
          if (!token) return;
          
          await fetch('https://stake.com/_api/graphql', {
            method: 'POST',
            headers: { 'content-type': 'application/json', 'x-access-token': token },
            body: JSON.stringify({ query: "{ me { id username } }" })
          });
          console.log("[STAKE-BOT] AFK: Session Refreshed");
        } catch (e) {}
      }
    });

    // 2. Pre-fetch Offers page to warm up cache
    // We create an offscreen document or a hidden tab to load the heavy assets
    try {
      const prefetchTab = await chrome.tabs.create({ 
        url: "https://stake.com/settings/offers", 
        active: false,
        pinned: true
      });
      // Give it 15 seconds to load then close it
      setTimeout(() => {
        chrome.tabs.remove(prefetchTab.id);
        console.log("[STAKE-BOT] Cache Warmed: Offers Page Pre-fetched");
      }, 15000);
    } catch (e) { console.error("Prefetch error:", e); }

  }, 1000 * 60 * 5); // Every 5 mins
}

async function processQueue() {
  if (isProcessing || dropQueue.length === 0) return;
  isProcessing = true;
  const drop = dropQueue.shift();
  await claimDrop(drop.code, drop.channel);
  // No delay for next item if queue isn't empty
  isProcessing = false;
  if (dropQueue.length > 0) processQueue();
}

async function claimDrop(code, channel) {
  let tabs = await chrome.tabs.query({ active: true, currentWindow: true, url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
  if (tabs.length === 0) tabs = await chrome.tabs.query({ url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
  if (tabs.length === 0) return;

  chrome.scripting.executeScript({
    target: { tabId: tabs[0].id },
    func: async (dropCode, dropChannel, soundUrl) => {
      const findToken = () => {
        // 1. Check all possible localStorage keys (Stake sometimes uses random prefixes)
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key.includes('token') || key.includes('session') || key === 'jwt') {
            const val = localStorage.getItem(key);
            if (val && val.length > 20) return val; // Real tokens are long
          }
        }
        
        // 2. Check standard keys specifically
        const standardKeys = ['x-access-token', 'sessionToken', 'token', 'jwt'];
        for (const k of standardKeys) {
          const val = window.localStorage.getItem(k) || window.sessionStorage.getItem(k);
          if (val) return val;
        }

        // 3. Check cookies
        const cookieMatch = document.cookie.match(/session=([^;]+)/);
        if (cookieMatch) return cookieMatch[1];
        
        return null;
      };

      const token = findToken();
      if (!token) {
        // If background claim fails to find token, we MUST redirect to UI mode 
        // because the UI usually forces the token to load or shows the login screen.
        console.warn("[STAKE-BOT] No token found in background. Redirecting to UI...");
        window.location.href = `https://stake.com/settings/offers?currency=btc&type=drop&code=${dropCode}&channel=${dropChannel}&modal=redeemBonus`;
        return { status: "No Token (Redirected)" };
      }
      try {
        const query = `mutation ClaimBonusCode($code: String!, $currency: CurrencyEnum!, $turnstileToken: String!) {
          claimBonusCode(code: $code, currency: $currency, turnstileToken: $turnstileToken) { ip }
        }`;
        const response = await fetch('https://stake.com/_api/graphql', {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-access-token': token, 'x-language': 'en' },
          body: JSON.stringify({ query, variables: { code: dropCode, currency: 'btc', turnstileToken: "" } })
        });
        const resJson = await response.json();
        if (resJson.errors) {
          const msg = resJson.errors[0].message;
          if (msg.includes('turnstileToken') || msg.includes('invalid_turnstile')) {
            window.location.href = `https://stake.com/settings/offers?currency=btc&type=drop&code=${dropCode}&channel=${dropChannel}&modal=redeemBonus`;
            return { status: "REDIRECTED" };
          }
          return { status: msg };
        }
        try { new Audio(soundUrl).play(); } catch(e) {}
        return { status: "Success" };
      } catch (e) { return { status: "Fetch Error" }; }
    },
    args: [code, channel, SUCCESS_SOUND_URL]
  }).then((results) => {
    const status = results[0].result?.status || "Unknown";
    if (status !== "REDIRECTED" && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "REPORT", status: status, code: code, channel: channel }));
    }
  });
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'GET_STATUS') sendResponse({ connected: isConnected });
  else if (request.action === 'RECONNECT') { if (socket) socket.close(); connect(); }
  else if (request.action === 'FINAL_REPORT') {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "REPORT", status: request.status, code: request.code, channel: request.channel }));
    }
  }
});

connect();

// Tab Manager: Ensures only one Stake tab stays open
chrome.tabs.onCreated.addListener(async (newTab) => {
  if (!newTab.url && !newTab.pendingUrl) return;
  const url = newTab.url || newTab.pendingUrl;
  
  if (url.includes("stake.com") || url.includes("stake.us")) {
    const tabs = await chrome.tabs.query({ url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
    // If we have more than 1 stake tab, close the OLDER ones
    if (tabs.length > 1) {
      const tabsToRemove = tabs
        .filter(t => t.id !== newTab.id)
        .map(t => t.id);
      chrome.tabs.remove(tabsToRemove);
      console.log(`[StakePeek] Closed ${tabsToRemove.length} duplicate Stake tabs.`);
    }
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && tab.url.includes('modal=redeemBonus')) {
    const url = new URL(tab.url);
    const code = url.searchParams.get('code');
    const channel = url.searchParams.get('channel');
    chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: (soundUrl, dropCode, dropChannel) => {
        if (window.stakeBotInjected) return;
        window.stakeBotInjected = true;
        const autoClick = setInterval(() => {
          const bodyText = document.body.innerText;
          const isFinished = /invalid|unavailable|claimed|Success|found|limit|Expired|already/i.test(bodyText);
          if (isFinished) {
            let finalStatus = "Unavailable";
            if (bodyText.includes('Success')) finalStatus = "Success";
            if (bodyText.includes('invalid')) finalStatus = "Invalid Code";
            if (bodyText.includes('already')) finalStatus = "Already Claimed";
            chrome.runtime.sendMessage({ action: 'FINAL_REPORT', status: finalStatus, code: dropCode, channel: dropChannel });
            if (finalStatus === 'Success') { try { new Audio(soundUrl).play(); } catch(e) {} }
            setTimeout(() => {
              const closeBtn = document.querySelector('button[aria-label="Close"]') || document.querySelector('.modal-close');
              if (closeBtn) closeBtn.click(); else window.location.href = 'https://stake.com/settings/offers';
              window.stakeBotInjected = false;
            }, 3000);
            clearInterval(autoClick);
            return;
          }
          const btn = Array.from(document.querySelectorAll('button')).find(b => /Redeem|Submit|Claim/i.test(b.innerText) && b.offsetParent !== null && !b.disabled);
          if (btn) {
            btn.click();
            // Faster check after click
            setTimeout(() => {}, 500);
          }
        }, 500);
        setTimeout(() => { clearInterval(autoClick); window.stakeBotInjected = false; }, 30000);
      },
      args: [SUCCESS_SOUND_URL, code, channel]
    });
  }
});