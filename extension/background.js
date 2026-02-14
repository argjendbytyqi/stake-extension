let socket = null;
let isConnected = false;
let isProcessing = false;
const dropQueue = [];

const SUCCESS_SOUND_URL = "https://assets.mixkit.co/active_storage/sfx/2017/2017-preview.mp3";

function connect() {
  chrome.storage.local.get(['licenseKey'], (res) => {
    const key = res.licenseKey;
    if (!key) return;

    socket = new WebSocket(`ws://18.199.98.207:8000/ws/${key}`);

    socket.onopen = () => {
      isConnected = true;
      console.log("✅ Connected to Stake Broadcaster");
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
          
          chrome.storage.local.get(['monitorDaily', 'monitorHigh'], async (prefs) => {
            const isDaily = data.channel === 'StakecomDailyDrops';
            const isHigh = data.channel === 'stakecomhighrollers';
            const monitorDaily = prefs.monitorDaily !== false;
            const monitorHigh = !!prefs.monitorHigh;

            if ((isDaily && monitorDaily) || (isHigh && monitorHigh)) {
              dropQueue.push({ code: data.code, channel: data.channel });
              processQueue();
            }
          });
        }
      } catch (e) {}
    };

    socket.onclose = () => {
      isConnected = false;
      setTimeout(connect, 10000);
    };
  });
}

async function processQueue() {
  if (isProcessing || dropQueue.length === 0) return;
  isProcessing = true;
  
  const drop = dropQueue.shift();
  console.log(`🚀 Processing drop from queue: ${drop.code}`);
  await claimDrop(drop.code, drop.channel);
  
  setTimeout(() => {
    isProcessing = false;
    processQueue();
  }, 10000); 
}

async function claimDrop(code, channel) {
  let tabs = await chrome.tabs.query({ active: true, currentWindow: true, url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
  if (tabs.length === 0) {
    tabs = await chrome.tabs.query({ url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
  }
  
  if (tabs.length === 0) {
    console.warn("❌ No Stake tab found.");
    return;
  }

  const targetTabId = tabs[0].id;
  console.log(`💉 Attempting background claim for ${code} on tab ${targetTabId}`);

  chrome.scripting.executeScript({
    target: { tabId: targetTabId },
    func: async (dropCode, dropChannel, soundUrl) => {
      const findToken = () => {
        const keys = ['x-access-token', 'sessionToken', 'token', 'jwt'];
        for (const k of keys) {
          const val = window.localStorage.getItem(k) || window.sessionStorage.getItem(k);
          if (val) return val;
        }
        const cookieMatch = document.cookie.match(/session=([^;]+)/);
        return cookieMatch ? cookieMatch[1] : null;
      };

      const token = findToken();
      if (!token) return { status: "No Token" };

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
            console.log("[STAKE-BOT] Captcha required, switching to UI...");
            window.location.href = `https://stake.com/settings/offers?currency=btc&type=drop&code=${dropCode}&channel=${dropChannel}&modal=redeemBonus`;
            return { status: "REDIRECTED" };
          }
          return { status: msg };
        }
        
        try { new Audio(soundUrl).play(); } catch(e) {}
        return { status: "Success" };
      } catch (e) { 
        return { status: "Fetch Error" }; 
      }
    },
    args: [code, channel, SUCCESS_SOUND_URL]
  }).then((results) => {
    // Only report if it's NOT a redirect
    const status = results[0].result?.status || "Unknown";
    if (status !== "REDIRECTED" && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        type: "REPORT",
        status: status,
        code: code,
        channel: channel
      }));
    }
  });
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'GET_STATUS') {
    sendResponse({ connected: isConnected });
  } else if (request.action === 'RECONNECT') {
    if (socket) socket.close();
    connect();
  } else if (request.action === 'FINAL_REPORT') {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        type: "REPORT",
        status: request.status,
        code: request.code,
        channel: request.channel
      }));
    }
  }
});

connect();

// UI Auto-Clicker Logic
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && tab.url.includes('modal=redeemBonus')) {
    const url = new URL(tab.url);
    const code = url.searchParams.get('code');
    const channel = url.searchParams.get('channel') || (tab.url.includes('DailyDrops') ? 'StakecomDailyDrops' : 'stakecomhighrollers');

    chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: (soundUrl, dropCode, dropChannel) => {
        if (window.stakeBotInjected) return;
        window.stakeBotInjected = true;
        
        console.log("%c[STAKE-BOT] UI Mode Active.", "color: #1475e1; font-weight: bold;");
        
        const autoClick = setInterval(() => {
          const bodyText = document.body.innerText;
          const isFinished = /invalid|unavailable|claimed|Success|found|limit/i.test(bodyText);
          
          if (isFinished) {
            let finalStatus = "Unavailable";
            if (bodyText.includes('Success')) finalStatus = "Success";
            if (bodyText.includes('invalid')) finalStatus = "Invalid Code";
            
            console.log(`%c[STAKE-BOT] Result: ${finalStatus}`, "color: orange;");
            
            chrome.runtime.sendMessage({ 
              action: 'FINAL_REPORT', 
              status: finalStatus, 
              code: dropCode, 
              channel: dropChannel 
            });

            if (finalStatus === 'Success') {
              try { new Audio(soundUrl).play(); } catch(e) {}
            }
            
            setTimeout(() => {
              const closeBtn = document.querySelector('button[aria-label="Close"]') || 
                               document.querySelector('.modal-close') ||
                               Array.from(document.querySelectorAll('button')).find(b => /Dismiss|Close/i.test(b.innerText));
              if (closeBtn) closeBtn.click();
              else window.location.href = 'https://stake.com/settings/offers';
              window.stakeBotInjected = false;
            }, 4000);
            
            clearInterval(autoClick);
            return;
          }

          const btn = Array.from(document.querySelectorAll('button')).find(b => 
            /Redeem|Submit|Claim/i.test(b.innerText) && b.offsetParent !== null && !b.disabled
          );
          
          if (btn) {
            console.log("%c[STAKE-BOT] Button ready! Clicking...", "color: #00e676;");
            btn.click();
          }
        }, 1000);

        setTimeout(() => { 
          clearInterval(autoClick); 
          window.stakeBotInjected = false; 
        }, 30000);
      },
      args: [SUCCESS_SOUND_URL, code, channel]
    });
  }
});