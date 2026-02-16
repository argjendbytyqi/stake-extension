// WARMER.JS - The token harvester
// This script runs on stake.com/settings/offers

function harvestToken() {
    // 1. Try to find the Turnstile token in the hidden input
    const turnstileInput = document.querySelector('input[name="cf-turnstile-response"]');
    if (turnstileInput && turnstileInput.value) {
        const token = turnstileInput.value;
        console.log("🔥 [Warmer] Token harvested!");
        
        // 2. Send it to the background script
        chrome.runtime.sendMessage({ action: 'SET_HOT_TOKEN', token: token });
        
        // 3. Clear the input so we don't send the same token twice
        // Stake will re-generate a new one if it's cleared
        turnstileInput.value = "";
    }
}

// Check every 2 seconds
setInterval(harvestToken, 2000);
console.log("🔥 [Warmer] Token harvester active.");
