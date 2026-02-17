let socket = null;
let isConnected = false;
let hotTurnstileToken = { value: null, timestamp: 0 }; 
let lastSignalTime = 0; 
const processedCodes = new Set(); 

// ⚡ PERFORMANCE CACHE
let prefs = { monitorDaily: true, monitorHigh: false, licenseKey: null };
let activeStakeTabs = new Set();

const SUCCESS_SOUND_URL = "https://assets.mixkit.co/active_storage/sfx/2017/2017-preview.mp3";

// 1. Pre-load preferences
chrome.storage.local.get(['licenseKey', 'monitorDaily', 'monitorHigh'], (res) => {
    prefs = { ...prefs, ...res };
    connect();
});

chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local') {
        for (let [key, { newValue }] of Object.entries(changes)) {
            prefs[key] = newValue;
        }
    }
});

// 2. Track tabs
const updateTabCache = () => {
    chrome.tabs.query({ url: ["*://stake.com/*", "*://stake.us/*", "*://*.stake.com/*"] }, (tabs) => {
        activeStakeTabs.clear();
        tabs.forEach(t => activeStakeTabs.add(t.id));
    });
};
chrome.tabs.onUpdated.addListener(updateTabCache);
chrome.tabs.onRemoved.addListener(updateTabCache);
updateTabCache();

function connect() {
    if (!prefs.licenseKey) return;
    fetch(`http://18.199.98.207:8000/auth/token?license_key=${prefs.licenseKey}`)
      .then(r => r.json())
      .then(data => {
        if (!data.token) return;
        socket = new WebSocket(`ws://18.199.98.207:8000/ws?token=${data.token}`);
        socket.onopen = () => { isConnected = true; };
        socket.onmessage = async (event) => {
          if (event.data === "pong") return;
          try {
            const data = JSON.parse(event.data);
            if (data.type === "DROP") {
              lastSignalTime = Date.now();
              if (!data.code || data.code === "None" || processedCodes.has(data.code)) return;
              const isDaily = data.channel === 'StakecomDailyDrops';
              const isHigh = data.channel === 'stakecomhighrollers';
              if ((isDaily && prefs.monitorDaily !== false) || (isHigh && prefs.monitorHigh === true)) {
                  processedCodes.add(data.code);
                  claimDrop(data.code, data.channel);
              }
            }
          } catch (e) {}
        };
        socket.onclose = () => { isConnected = false; setTimeout(connect, 5000); };
      }).catch(e => setTimeout(connect, 5000));
}

async function claimDrop(code, channel) {
  if (activeStakeTabs.size === 0) {
    chrome.tabs.create({ url: `https://stake.com/settings/offers?code=${code}&modal=redeemBonus` });
    return;
  }

  let activeToken = "";
  if (hotTurnstileToken.value && (Date.now() - hotTurnstileToken.timestamp < 90000)) {
    activeToken = hotTurnstileToken.value;
  }
  
  const payload = `{"query":"mutation ClaimBonusCode($code: String!, $currency: CurrencyEnum!, $turnstileToken: String!) { claimBonusCode(code: $code, currency: $currency, turnstileToken: $turnstileToken) { ip } }","variables":{"code":"${code}","currency":"btc","turnstileToken":"${activeToken}"}}`;

  let alreadyReported = false;
  activeStakeTabs.forEach(tabId => {
    chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: async (dropCode, dropChannel, readyPayload) => {
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
          return { status: "No Token" };
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
            if (msg.includes('turnstileToken') || msg.includes('captcha')) {
              window.location.href = `https://stake.com/settings/offers?currency=btc&type=drop&code=${dropCode}&channel=${dropChannel}&modal=redeemBonus`;
              return { status: "REDIRECTED" };
            }
            return { status: msg };
          }
          return { status: "Success" };
        } catch (e) { return { status: "Fetch Error" }; }
      },
      args: [code, channel, payload]
    }).then((results) => {
      const status = results[0]?.result?.status;
      if (status && !["REDIRECTED", "No Token"].includes(status)) {
        if (!alreadyReported) {
            alreadyReported = true;
            reportResult(status, code, channel);
        }
      }
    });
  });
}

function reportResult(status, code, channel) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "REPORT", status: status, code: code, channel: channel }));
    }
    if (lastSignalTime > 0) {
        const speed = Date.now() - lastSignalTime;
        chrome.storage.local.set({ lastClaimSpeed: speed });
        lastSignalTime = 0; 
    }
    if (status === "Success") { try { new Audio(SUCCESS_SOUND_URL).play(); } catch(e){} }
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'GET_STATUS') sendResponse({ connected: isConnected });
  else if (request.action === 'SET_HOT_TOKEN') {
    hotTurnstileToken = { value: request.token, timestamp: Date.now() };
  }
  else if (request.action === 'RECONNECT') { 
    if (socket) socket.close(); 
    processedCodes.clear(); 
    connect(); 
  }
  else if (request.action === 'FINAL_REPORT') {
      reportResult(request.status, request.code, request.channel);
  }
});

// ⚡ RE-INJECTION LOGIC (The UI Auto-Clicker)
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && tab.url.includes('modal=redeemBonus')) {
    const url = new URL(tab.url);
    const code = url.searchParams.get('code');
    const channel = url.searchParams.get('channel');
    if (!code || code === 'None' || code === 'null') return;

    chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: (dropCode, dropChannel) => {
        const run = () => {
          const bodyText = document.body.innerText;
          const isFinished = /invalid|unavailable|claimed|Success|found|limit|Expired|already/i.test(bodyText);
          if (isFinished) {
            let status = "Unavailable";
            if (bodyText.includes('Success')) status = "Success";
            chrome.runtime.sendMessage({ action: 'FINAL_REPORT', status: status, code: dropCode, channel: dropChannel });
            
            // UI CLICKER: Find ANY button that looks like a close button
            const close = document.querySelector('button[aria-label="Close"]') || 
                          document.querySelector('.modal-close') ||
                          Array.from(document.querySelectorAll('button')).find(b => /Dismiss|Close|Confirm/i.test(b.innerText));
            if (close) close.click();
            return;
          }
          const btn = Array.from(document.querySelectorAll('button')).find(b => 
            /Redeem|Submit|Claim/i.test(b.innerText) && b.offsetParent !== null && !b.disabled
          );
          if (btn) { btn.click(); setTimeout(run, 500); } else { setTimeout(run, 200); }
        };
        run();
      },
      args: [code, channel]
    });
  }
});
