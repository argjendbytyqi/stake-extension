let socket = null;
let isConnected = false;

// Audio context for "Ka-ching!" sound
const SUCCESS_SOUND_URL = "https://assets.mixkit.co/active_storage/sfx/2017/2017-preview.mp3";

function connect() {
  chrome.storage.local.get(['licenseKey'], (res) => {
    const key = res.licenseKey;
    if (!key) return;

    socket = new WebSocket(`ws://18.199.98.207:8000/ws/${key}`);

    socket.onopen = () => {
      isConnected = true;
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
          chrome.storage.local.get(['monitorDaily', 'monitorHigh'], async (prefs) => {
            const isDaily = data.channel === 'StakecomDailyDrops';
            const isHigh = data.channel === 'stakecomhighrollers';
            if ((isDaily && prefs.monitorDaily !== false) || (isHigh && prefs.monitorHigh === true)) {
              await claimDrop(data.code, data.channel);
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

async function claimDrop(code, channel) {
  const tabs = await chrome.tabs.query({ url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] });
  if (tabs.length === 0) return;

  chrome.scripting.executeScript({
    target: { tabId: tabs[0].id },
    func: async (dropCode, dropChannel, soundUrl) => {
      const token = window.localStorage.getItem('x-access-token');
      if (!token) return { status: "No Token" };

      const query = `mutation ClaimBonusCode($code: String!, $currency: CurrencyEnum!, $turnstileToken: String!) {
        claimBonusCode(code: $code, currency: $currency, turnstileToken: $turnstileToken) { ip }
      }`;

      try {
        const response = await fetch('https://stake.com/_api/graphql', {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-access-token': token, 'x-language': 'en' },
          body: JSON.stringify({ query, variables: { code: dropCode, currency: 'btc', turnstileToken: "" } })
        });
        const resJson = await response.json();
        
        if (resJson.errors) {
          const msg = resJson.errors[0].message;
          if (msg.includes('turnstileToken') || msg.includes('invalid_turnstile')) {
            window.location.href = `https://stake.com/settings/offers?code=${dropCode}&modal=redeemBonus`;
            return { status: "Captcha (Redirected)" };
          }
          return { status: msg };
        }
        
        // Success Logic: Play Sound
        const audio = new Audio(soundUrl);
        audio.play();
        return { status: "Success" };
      } catch (e) { return { status: "Error" }; }
    },
    args: [code, channel, SUCCESS_SOUND_URL]
  }).then((results) => {
    // Report back to server
    if (results && results[0] && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        type: "REPORT",
        status: results[0].result.status,
        code: code,
        channel: channel
      }));
    }
  });
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'GET_STATUS') sendResponse({ connected: isConnected });
  else if (request.action === 'RECONNECT') { if (socket) socket.close(); connect(); }
});

connect();

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && tab.url.includes('redeemBonus')) {
    chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: (soundUrl) => {
        if (window.stakeBotInjected) return;
        window.stakeBotInjected = true;
        const autoClick = setInterval(() => {
          const bodyText = document.body.innerText;
          if (/invalid|unavailable|claimed|Success|found/i.test(bodyText)) {
            if (bodyText.includes('Success')) { new Audio(soundUrl).play(); }
            setTimeout(() => {
              const closeBtn = document.querySelector('button[aria-label="Close"]') || document.querySelector('.modal-close');
              if (closeBtn) closeBtn.click(); else window.location.href = 'https://stake.com/settings/offers';
              window.stakeBotInjected = false;
            }, 4000);
            clearInterval(autoClick);
            return;
          }
          const btn = Array.from(document.querySelectorAll('button')).find(b => /Redeem|Submit|Claim/i.test(b.innerText) && b.offsetParent !== null && !b.disabled);
          if (btn) btn.click();
        }, 1000);
      },
      args: [SUCCESS_SOUND_URL]
    });
  }
});