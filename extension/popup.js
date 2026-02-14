document.addEventListener('DOMContentLoaded', () => {
  const keyInput = document.getElementById('license-key');
  const saveBtn = document.getElementById('save-btn');
  const statusSpan = document.getElementById('conn-status');
  const checkDaily = document.getElementById('check-daily');
  const checkHigh = document.getElementById('check-high');

  // Load existing settings
  chrome.storage.local.get(['licenseKey', 'monitorDaily', 'monitorHigh'], (res) => {
    if (res.licenseKey) keyInput.value = res.licenseKey;
    
    // Default to true for daily if never set
    checkDaily.checked = res.monitorDaily !== false;
    checkHigh.checked = !!res.monitorHigh;
  });

  // Save key
  saveBtn.addEventListener('click', () => {
    const key = keyInput.value.trim();
    if (!key) return;
    chrome.storage.local.set({ licenseKey: key }, () => {
      chrome.runtime.sendMessage({ action: 'RECONNECT' });
      saveBtn.textContent = 'Connecting...';
      setTimeout(() => { saveBtn.textContent = 'Activate'; }, 2000);
    });
  });

  // Save toggles immediately on click
  checkDaily.addEventListener('change', () => {
    chrome.storage.local.set({ monitorDaily: checkDaily.checked });
  });

  checkHigh.addEventListener('change', () => {
    chrome.storage.local.set({ monitorHigh: checkHigh.checked });
  });

  // Periodically check status
  const checkStatus = () => {
    try {
      chrome.runtime.sendMessage({ action: 'GET_STATUS' }, (response) => {
        if (chrome.runtime.lastError) return;
        if (response && response.connected) {
          statusSpan.textContent = 'Active & Waiting';
          statusSpan.className = 'on';
        } else {
          statusSpan.textContent = 'Disconnected';
          statusSpan.className = 'off';
        }
      });
    } catch (e) {}
  };

  setInterval(checkStatus, 2000);
  checkStatus();
});