let socket = null;
let isConnected = false;

function connect() {
  chrome.storage.local.get(['licenseKey'], (res) => {
    const key = res.licenseKey;
    if (!key) return;

    console.log("🔗 Connecting to server with key:", key);
    // Use your EC2 Public IP here
    socket = new WebSocket(`ws://18.199.98.207:8000/ws/${key}`);

    socket.onopen = () => {
      isConnected = true;
      console.log("✅ Connected to Stake Broadcaster");
      
      const scheduleNextPing = () => {
        const jitter = Math.floor(Math.random() * 10000);
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
      if (event.data === "pong") return;

      try {
        const data = JSON.parse(event.data);
        if (data.type === "DROP") {
          console.log(`🚀 Drop signal received from ${data.channel}: ${data.code}`);
          
          // CHECK USER PREFERENCES
          chrome.storage.local.get(['monitorDaily', 'monitorHigh'], async (prefs) => {
            const isDaily = data.channel === 'StakecomDailyDrops';
            const isHigh = data.channel === 'stakecomhighrollers';
            
            const allowed = (isDaily && prefs.monitorDaily !== false) || (isHigh && prefs.monitorHigh === true);
            
            if (allowed) {
              console.log("✅ Channel enabled in settings. Proceeding to claim...");
              await claimDrop(data.code);
            } else {
              console.log("⏭️ Channel disabled in settings. Skipping.");
            }
          });
        }
      } catch (e) {
        console.warn("⚠️ Unknown message:", event.data);
      }
    };

    socket.onclose = () => {
      isConnected = false;
      console.log("❌ Connection closed. Retrying in 10s...");
      setTimeout(connect, 10000);
    };
  });
}

async function claimDrop(code) {
  const tabs = await chrome.tabs.query({ url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
  if (tabs.length === 0) return;

  const targetTab = tabs[0];
  try {
    await chrome.scripting.executeScript({
      target: { tabId: targetTab.id },
      func: async (dropCode) => {
        const token = window.localStorage.getItem('x-access-token');
        if (!token) return;

        console.log("%c[STAKE-BOT] Attempting Background Claim...", "color: #00e676;");
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
            variables: { code: dropCode, currency: 'btc', turnstileToken: "" }
          })
        });

        const resJson = await response.json();
        if (resJson.errors) {
          const msg = resJson.errors[0].message;
          if (msg.includes('turnstileToken') || msg.includes('invalid_turnstile')) {
            window.location.href = `https://stake.com/settings/offers?code=${dropCode}&modal=redeemBonus`;
          }
        }
      },
      args: [code]
    });
  } catch (err) {}
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'GET_STATUS') sendResponse({ connected: isConnected });
  else if (request.action === 'RECONNECT') {
    if (socket) socket.close();
    connect();
  }
});

connect();

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && tab.url.includes('redeemBonus')) {
    chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: () => {
        if (window.stakeBotInjected) return;
        window.stakeBotInjected = true;
        const autoClick = setInterval(() => {
          const bodyText = document.body.innerText;
          const isFinished = /invalid|unavailable|claimed|Success|found/i.test(bodyText);
          if (isFinished) {
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
          if (btn) btn.click();
        }, 1000);
        setTimeout(() => { clearInterval(autoClick); window.stakeBotInjected = false; }, 30000);
      }
    });
  }
});