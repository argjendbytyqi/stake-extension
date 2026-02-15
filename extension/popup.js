document.addEventListener('DOMContentLoaded', () => {
  const keyInput = document.getElementById('license-key');
  const saveBtn = document.getElementById('save-btn');
  const statusSpan = document.getElementById('conn-status');
  const checkDaily = document.getElementById('check-daily');
  const checkHigh = document.getElementById('check-high');
  const licenseInfo = document.getElementById('license-info');
  const expireDate = document.getElementById('expire-date');
  const claimsCount = document.getElementById('claims-count');

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
    
    // Default to true for daily if never set
    checkDaily.checked = res.monitorDaily !== false;
    checkHigh.checked = !!res.monitorHigh;
  });

  // Save key
  saveBtn.addEventListener('click', () => {
    const key = keyInput.value.trim();
    if (!key) return;
    
    saveBtn.textContent = 'Verifying...';
    
    // Fetch license info from server
    fetch(`http://18.199.98.207:8000/auth/token?license_key=${key}`)
      .then(r => r.json())
      .then(data => {
        if (data.token) {
          // Decode JWT to get expiry (sub is key, exp is timestamp)
          const payload = JSON.parse(atob(data.token.split('.')[1]));
          const expiry = new Date(payload.exp * 1000).toISOString();
          
          chrome.storage.local.set({ 
            licenseKey: key,
            expireAt: expiry,
            totalClaims: data.total_claims || 0
          }, () => {
            chrome.runtime.sendMessage({ action: 'RECONNECT' });
            licenseInfo.style.display = 'block';
            expireDate.textContent = new Date(expiry).toLocaleDateString();
            claimsCount.textContent = data.total_claims || 0;
            saveBtn.textContent = 'License Active';
            setTimeout(() => { saveBtn.textContent = 'Update License'; }, 2000);
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
          statusSpan.textContent = '● Online';
          statusSpan.className = 'on';
          saveBtn.textContent = 'License Active';
          saveBtn.style.background = '#00e676'; // Green when active
        } else {
          statusSpan.textContent = '● Offline';
          statusSpan.className = 'off';
          saveBtn.style.background = '#1475e1'; // Reset to blue
        }
      });
    } catch (e) {}
  };

  setInterval(checkStatus, 2000);
  checkStatus();
});