let socket = null;
let isConnected = false;
let isProcessing = false;
let afkTimer = null;
let hotTurnstileToken = { value: null, timestamp: 0 }; // Store token with timestamp
const dropQueue = [];
const processedCodes = new Set(); // Reset on extension reload

const SUCCESS_SOUND_URL = "https://assets.mixkit.co/active_storage/sfx/2017/2017-preview.mp3";

function connect() {
  chrome.storage.local.get(['licenseKey', 'connectionActive'], (res) => {
    const key = res.licenseKey;
    if (!key || res.connectionActive === false) return;

    fetch(`http://18.199.98.207:8000/auth/token?license_key=${key}`)
      .then(r => r.json())
      .then(data => {
        if (!data.token) return;

        socket = new WebSocket(`ws://18.199.98.207:8000/ws?token=${data.token}`);

        socket.onopen = () => {
          isConnected = true;
          console.log("✅ Connected to Stake Broadcaster");
          setupAFK();
          const scheduleNextPing = () => {
            setTimeout(() => {
              if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: "ping" }));
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
              console.log(`📡 Signal: ${data.channel} -> ${data.code}`);
              
              // 1. IN-MEMORY DUPLICATE CHECK (Resets on reload)
              if (processedCodes.has(data.code)) {
                  console.log(`⏭️ Already tried ${data.code}. Skipping.`);
                  return;
              }

              chrome.storage.local.get(['monitorDaily', 'monitorHigh'], async (prefs) => {
                const isDaily = data.channel === 'StakecomDailyDrops';
                const isHigh = data.channel === 'stakecomhighrollers';
                
                if ((isDaily && prefs.monitorDaily !== false) || (isHigh && prefs.monitorHigh === true)) {
                  // 2. Mark as processed immediately
                  processedCodes.add(data.code);

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

function setupAFK() {
  if (afkTimer) clearInterval(afkTimer);
  afkTimer = setInterval(async () => {
    const tabs = await chrome.tabs.query({ url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
    if (tabs.length === 0) return;

    // Send heartbeat to all tabs to keep them alive and active
    tabs.forEach(tab => {
        chrome.tabs.sendMessage(tab.id, { action: "HEARTBEAT" }).catch(() => {});
    });

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
        } catch (e) {}
      }
    });
  }, 1000 * 60 * 5);
}

async function processQueue() {
  if (isProcessing || dropQueue.length === 0) return;
  isProcessing = true;
  const drop = dropQueue.shift();
  await claimDrop(drop.code, drop.channel);
  isProcessing = false;
  if (dropQueue.length > 0) processQueue();
}

async function claimDrop(code, channel) {
  const tabs = await chrome.tabs.query({ url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
  if (tabs.length === 0) return;

  console.log(`[Blitz] Attempting ${code} on ${tabs.length} tabs...`);

  const query = `mutation ClaimBonusCode($code: String!, $currency: CurrencyEnum!, $turnstileToken: String!) {
    claimBonusCode(code: $code, currency: $currency, turnstileToken: $turnstileToken) { ip }
  }`;
  
  // Use the hot token if it's fresh (less than 90 seconds old)
  let activeToken = "";
  const now = Date.now();
  if (hotTurnstileToken.value && (now - hotTurnstileToken.timestamp < 90000)) {
    activeToken = hotTurnstileToken.value;
    console.log(`[Blitz] Using hot token (Age: ${Math.round((now - hotTurnstileToken.timestamp)/1000)}s)`);
  } else if (hotTurnstileToken.value) {
    console.log("[Blitz] Hot token expired, ignoring.");
  }

  // Clear it so it's not reused
  hotTurnstileToken = { value: null, timestamp: 0 }; 

  const payload = JSON.stringify({ query, variables: { code: code, currency: 'btc', turnstileToken: activeToken } });

  tabs.forEach(tab => {
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: async (dropCode, dropChannel, soundUrl, readyPayload) => {
        if (window.isClaiming === dropCode) return;
        window.isClaiming = dropCode;

        const findToken = () => {
          const keys = ['x-access-token', 'sessionToken', 'token', 'jwt'];
          for (const k of keys) {
            const val = window.localStorage.getItem(k) || window.sessionStorage.getItem(k);
            if (val) return val;
          }
          return null;
        };

        const token = findToken();
        if (!token) {
          window.location.href = `https://stake.com/settings/offers?currency=btc&type=drop&code=${dropCode}&channel=${dropChannel}&modal=redeemBonus`;
          return { status: "No Token (Redirected)" };
        }

        try {
          const response = await fetch('https://stake.com/_api/graphql', {
            method: 'POST',
            headers: { 'content-type': 'application/json', 'x-access-token': token, 'x-language': 'en' },
            body: readyPayload
          });
          const resJson = await response.json();
          if (resJson.errors) {
            const msg = resJson.errors[0].message;
            if (msg.includes('turnstileToken') || msg.includes('invalid_turnstile') || msg.includes('captcha')) {
              window.location.href = `https://stake.com/settings/offers?currency=btc&type=drop&code=${dropCode}&channel=${dropChannel}&modal=redeemBonus`;
              return { status: "REDIRECTED" };
            }
            return { status: msg };
          }
          try { new Audio(soundUrl).play(); } catch(e) {}
          return { status: "Success" };
        } catch (e) { return { status: "Fetch Error" }; }
      },
      args: [code, channel, SUCCESS_SOUND_URL, payload]
    }).then((results) => {
      const status = results[0]?.result?.status;
      if (status && !["REDIRECTED", "No Token (Redirected)"].includes(status)) {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "REPORT", status: status, code: code, channel: channel }));
        }
      }
    });
  });
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'GET_STATUS') sendResponse({ connected: isConnected });
  else if (request.action === 'SET_HOT_TOKEN') {
    hotTurnstileToken = {
        value: request.token,
        timestamp: Date.now()
    };
    console.log("🔥 Captcha Warmer: Fresh token received.");
  }
  else if (request.action === 'RECONNECT') { 
    if (socket) socket.close(); 
    processedCodes.clear(); // CLEAR CACHE ON RECONNECT/ACTIVATE
    connect(); 
  }
  else if (request.action === 'FINAL_REPORT') {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "REPORT", status: request.status, code: request.code, channel: request.channel }));
    }
  }
});

connect();

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
          if (btn) btn.click();
        }, 500);
        setTimeout(() => { clearInterval(autoClick); window.stakeBotInjected = false; }, 30000);
      },
      args: [SUCCESS_SOUND_URL, code, channel]
    });
  }
});
