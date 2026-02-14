document.addEventListener('DOMContentLoaded', () => {
  const keyInput = document.getElementById('license-key');
  const saveBtn = document.getElementById('save-btn');
  const statusSpan = document.getElementById('conn-status');

  // Load existing key
  chrome.storage.local.get(['licenseKey'], (res) => {
    if (keyInput && res.licenseKey) {
      keyInput.value = res.licenseKey;
    }
  });

  // Save key and notify background
  saveBtn.addEventListener('click', () => {
    const key = keyInput.value.trim();
    if (!key) return;
    chrome.storage.local.set({ licenseKey: key }, () => {
      chrome.runtime.sendMessage({ action: 'RECONNECT' });
      saveBtn.textContent = 'Connecting...';
      setTimeout(() => { saveBtn.textContent = 'Activate'; }, 2000);
    });
  });

  // Periodically check status (Check if extension context is valid)
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