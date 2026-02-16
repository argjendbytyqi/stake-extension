document.addEventListener('DOMContentLoaded', () => {
  const keyInput = document.getElementById('license-key');
  const saveBtn = document.getElementById('save-btn');
  const statusSpan = document.getElementById('conn-status');
  const checkDaily = document.getElementById('check-daily');
  const checkHigh = document.getElementById('check-high');
  const licenseInfo = document.getElementById('license-info');
  const expireDate = document.getElementById('expire-date');
  const claimsCount = document.getElementById('claims-count');
  const strikeSpeed = document.getElementById('strike-speed');

  let isCurrentlyConnected = false;

  // Load existing settings
  chrome.storage.local.get(['licenseKey', 'monitorDaily', 'monitorHigh', 'expireAt', 'totalClaims', 'lastClaimSpeed'], (res) => {
    if (res.licenseKey) {
      keyInput.value = res.licenseKey;
      if (res.expireAt) {
        licenseInfo.style.display = 'block';
        const date = new Date(res.expireAt);
        expireDate.textContent = `${date.getMonth()+1}/${date.getDate()}`;
        claimsCount.textContent = res.totalClaims || 0;
        if (res.lastClaimSpeed) {
            strikeSpeed.textContent = `${res.lastClaimSpeed}ms`;
        }
      }
    }
    checkDaily.checked = res.monitorDaily !== false;
    checkHigh.checked = !!res.monitorHigh;
  });

  // Action Button
  saveBtn.addEventListener('click', () => {
    if (isCurrentlyConnected) {
      chrome.storage.local.set({ connectionActive: false }, () => {
        chrome.runtime.sendMessage({ action: 'RECONNECT' }); 
        updateUI(false);
      });
      return;
    }

    const key = keyInput.value.trim();
    if (!key) return;
    
    saveBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Initializing...';
    
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
            const date = new Date(expiry);
            expireDate.textContent = `${date.getMonth()+1}/${date.getDate()}`;
            claimsCount.textContent = data.total_claims || 0;
          });
        } else {
          saveBtn.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Invalid Key';
          saveBtn.classList.add('btn-danger');
          setTimeout(() => { 
            saveBtn.innerHTML = '<i class="fa-solid fa-key"></i> Activate System';
            saveBtn.classList.remove('btn-danger');
          }, 2000);
        }
      })
      .catch(() => {
        saveBtn.innerHTML = '<i class="fa-solid fa-server"></i> Server Offline';
        setTimeout(() => { 
            saveBtn.innerHTML = '<i class="fa-solid fa-key"></i> Activate System'; 
        }, 2000);
      });
  });

  function updateUI(online) {
    isCurrentlyConnected = online;
    if (online) {
      statusSpan.textContent = 'ACTIVE';
      statusSpan.className = 'status-online';
      saveBtn.innerHTML = '<i class="fa-solid fa-power-off"></i> Terminate Link';
      saveBtn.className = 'btn btn-danger';
    } else {
      statusSpan.textContent = 'OFFLINE';
      statusSpan.className = 'status-offline';
      saveBtn.innerHTML = '<i class="fa-solid fa-key"></i> Activate System';
      saveBtn.className = 'btn btn-primary';
    }
  }

  checkDaily.addEventListener('change', () => {
    chrome.storage.local.set({ monitorDaily: checkDaily.checked });
  });

  checkHigh.addEventListener('change', () => {
    chrome.storage.local.set({ monitorHigh: checkHigh.checked });
  });

  const checkStatus = () => {
    try {
      chrome.runtime.sendMessage({ action: 'GET_STATUS' }, (response) => {
        if (chrome.runtime.lastError) return;
        updateUI(!!(response && response.connected));
      });
    } catch (e) {}
  };

  setInterval(checkStatus, 1500);
  checkStatus();
});
