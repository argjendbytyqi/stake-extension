document.addEventListener('DOMContentLoaded', () => {
  const keyInput = document.getElementById('license-key');
  const saveBtn = document.getElementById('save-btn');
  const statusSpan = document.getElementById('conn-status');
  const checkDaily = document.getElementById('check-daily');
  const checkHigh = document.getElementById('check-high');
  const licenseInfo = document.getElementById('license-info');
  const expireDate = document.getElementById('expire-date');
  const claimsCount = document.getElementById('claims-count');

  let isCurrentlyConnected = false;

  // Load existing settings
  chrome.storage.local.get(['licenseKey', 'monitorDaily', 'monitorHigh', 'expireAt', 'totalClaims'], (res) => {
    if (res.licenseKey) {
      keyInput.value = res.licenseKey;
      if (res.expireAt) {
        licenseInfo.style.display = 'block';
        expireDate.textContent = new Date(res.expireAt).toLocaleDateString();
        claimsCount.textContent = res.totalClaims || 0;
      }
    }
    checkDaily.checked = res.monitorDaily !== false;
    checkHigh.checked = !!res.monitorHigh;
  });

  // Action Button (Activate / Disconnect)
  saveBtn.addEventListener('click', () => {
    if (isCurrentlyConnected) {
      // DISCONNECT LOGIC (Keep the key, stop the socket)
      chrome.storage.local.set({ connectionActive: false }, () => {
        chrome.runtime.sendMessage({ action: 'RECONNECT' }); 
        statusSpan.textContent = 'Offline';
        statusSpan.className = 'off';
        isCurrentlyConnected = false;
        saveBtn.textContent = 'Activate License';
        saveBtn.style.background = '#1475e1';
      });
      return;
    }

    // ACTIVATE LOGIC
    const key = keyInput.value.trim();
    if (!key) return;
    
    saveBtn.textContent = 'Connecting...';
    
    fetch(`http://18.199.98.207:8000/auth/token?license_key=${key}`)
      .then(r => r.json())
      .then(data => {
        if (data.token) {
          const payload = JSON.parse(atob(data.token.split('.')[1]));
          const expiry = new Date(payload.exp * 1000).toISOString();
          
          chrome.storage.local.set({ 
            licenseKey: key,
            connectionActive: true,
            expireAt: expiry,
            totalClaims: data.total_claims || 0
          }, () => {
            chrome.runtime.sendMessage({ action: 'RECONNECT' });
            licenseInfo.style.display = 'block';
            expireDate.textContent = new Date(expiry).toLocaleDateString();
            claimsCount.textContent = data.total_claims || 0;
          });
        } else {
          saveBtn.textContent = 'Invalid Key';
          saveBtn.style.background = '#ff5252';
          setTimeout(() => { 
            saveBtn.textContent = 'Activate License'; 
            saveBtn.style.background = '#1475e1';
          }, 2000);
        }
      })
      .catch(() => {
        saveBtn.textContent = 'Server Error';
        setTimeout(() => { saveBtn.textContent = 'Activate License'; }, 2000);
      });
  });

  checkDaily.addEventListener('change', () => {
    chrome.storage.local.set({ monitorDaily: checkDaily.checked });
  });

  checkHigh.addEventListener('change', () => {
    chrome.storage.local.set({ monitorHigh: checkHigh.checked });
  });

  // UI Sync with Background State
  const checkStatus = () => {
    try {
      chrome.runtime.sendMessage({ action: 'GET_STATUS' }, (response) => {
        if (chrome.runtime.lastError) return;
        if (response && response.connected) {
          isCurrentlyConnected = true;
          statusSpan.textContent = 'Online';
          statusSpan.className = 'on';
          saveBtn.textContent = 'Disconnect License';
          saveBtn.style.background = '#ff5252'; // Red for disconnect
        } else {
          isCurrentlyConnected = false;
          statusSpan.textContent = 'Offline';
          statusSpan.className = 'off';
          if (saveBtn.textContent !== 'Connecting...') {
            saveBtn.textContent = 'Activate License';
            saveBtn.style.background = '#1475e1'; // Blue for activate
          }
        }
      });
    } catch (e) {}
  };

  setInterval(checkStatus, 1500);
  checkStatus();
});
