const chatContainer = document.getElementById('chat');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const loadingIndicator = document.getElementById('loading');
const accountStatus = document.getElementById('account-status');
const detailedStatus = document.getElementById('detailed-status');

// Load initial status
async function loadStatus() {
    try {
        const res = await fetch('/status');
        const data = await res.json();
        
        accountStatus.textContent = `${data.active} active accounts | ${data.remaining_requests_today} requests left today`;
        
        detailedStatus.innerHTML = `
            <span><strong>Total:</strong> ${data.total_accounts}</span>
            <span><strong>Active:</strong> ${data.active}</span>
            <span><strong>Exhausted today:</strong> ${data.exhausted}</span>
            <span><strong>Errors:</strong> ${data.errors}</span>
            <span><strong>Banned:</strong> ${data.banned}</span>
            <span><strong>Total Requests Done:</strong> ${data.total_requests_made}</span>
        `;
    } catch (e) {
        console.error("Failed to load status:", e);
    }
}

function appendMessage(text, sender, meta = '') {
    const div = document.createElement('div');
    div.className = `message ${sender}`;
    div.innerText = text;
    
    if (meta) {
        const metaSpan = document.createElement('span');
        metaSpan.className = 'meta';
        metaSpan.innerText = meta;
        div.appendChild(metaSpan);
    }
    
    chatContainer.insertBefore(div, loadingIndicator);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;
    
    // UI update
    messageInput.value = '';
    appendMessage(text, 'user');
    sendButton.disabled = true;
    loadingIndicator.style.display = 'block';
    
    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, model: 'default' })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            appendMessage(data.reply, 'bot', `via ${data.account} in ${data.duration}s`);
            loadStatus(); // Refresh limits
        } else {
            appendMessage(`Error: ${data.detail || data.message || 'Unknown error'}`, 'bot');
        }
    } catch (err) {
        appendMessage(`Connection Error: ${err.message}`, 'bot');
    } finally {
        sendButton.disabled = false;
        loadingIndicator.style.display = 'none';
        messageInput.focus();
    }
}

sendButton.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});

// Init
loadStatus();
setInterval(loadStatus, 30000); // Check status every 30s
