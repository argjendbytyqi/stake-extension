// WARMER.JS - The token harvester
// This script runs on stake.com/settings/offers

function harvestToken() {
    // 1. Keep tab alive by simulating minor activity
    window.dispatchEvent(new Event('mousemove'));
    
    // 2. Try to find the Turnstile token
    const turnstileInput = document.querySelector('input[name="cf-turnstile-response"]');
    if (turnstileInput && turnstileInput.value) {
        const token = turnstileInput.value;
        console.log("🔥 [Warmer] Token harvested!");
        
        chrome.runtime.sendMessage({ action: 'SET_HOT_TOKEN', token: token });
        
        // Stake re-generates token if cleared or after use
        turnstileInput.value = ""; 
    }
}

// 3. Prevent Chrome from discarding this tab
chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === "HEARTBEAT") {
        console.log("💓 [Warmer] Heartbeat received.");
    }
});

// Check every 2 seconds
setInterval(harvestToken, 2000);
console.log("🔥 [Warmer] Token harvester active with Heartbeat.");
