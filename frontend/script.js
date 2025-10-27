// API base URL - use relative path to work from any host
const API_URL = '/api';

// Global state
let currentSessionId = null;

// DOM elements
let chatMessages, chatInput, sendButton, totalPapers, paperTopics;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Get DOM elements after page loads
    chatMessages = document.getElementById('chatMessages');
    chatInput = document.getElementById('chatInput');
    sendButton = document.getElementById('sendButton');
    totalPapers = document.getElementById('totalPapers');
    paperTopics = document.getElementById('paperTopics');

    setupEventListeners();
    createNewSession();
    loadPaperStats();
});

// Event Listeners
function setupEventListeners() {
    // Chat functionality
    sendButton.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
    
    
    // Suggested questions
    document.querySelectorAll('.suggested-item').forEach(button => {
        button.addEventListener('click', (e) => {
            const question = e.target.getAttribute('data-question');
            chatInput.value = question;
            sendMessage();
        });
    });
}


// Chat Functions
async function sendMessage() {
    const query = chatInput.value.trim();
    if (!query) return;

    // Disable input
    chatInput.value = '';
    chatInput.disabled = true;
    sendButton.disabled = true;

    // Add user message
    addMessage(query, 'user');

    // Add loading message - create a unique container for it
    const loadingMessage = createLoadingMessage();
    chatMessages.appendChild(loadingMessage);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        const response = await fetch(`${API_URL}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                session_id: currentSessionId
            })
        });

        if (!response.ok) throw new Error('Query failed');

        const data = await response.json();
        
        // Update session ID if new
        if (!currentSessionId) {
            currentSessionId = data.session_id;
        }

        // Replace loading message with response
        loadingMessage.remove();
        addMessage(data.answer, 'assistant', data.sources);

    } catch (error) {
        // Replace loading message with error
        loadingMessage.remove();
        addMessage(`Error: ${error.message}`, 'assistant');
    } finally {
        chatInput.disabled = false;
        sendButton.disabled = false;
        chatInput.focus();
    }
}

function createLoadingMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.innerHTML = `
        <div class="message-content">
            <div class="loading">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    return messageDiv;
}

function addMessage(content, type, sources = null, isWelcome = false) {
    const messageId = Date.now();
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}${isWelcome ? ' welcome-message' : ''}`;
    messageDiv.id = `message-${messageId}`;
    
    // Convert markdown to HTML for assistant messages
    const displayContent = type === 'assistant' ? marked.parse(content) : escapeHtml(content);
    
    let html = `<div class="message-content">${displayContent}</div>`;
    
    if (sources && sources.length > 0) {
        // Display sources as plain text badges (students will add hyperlinks as an exercise)
        const sourceLinks = sources.map(source => {
            // Handle both old format (string) and new format (object)
            if (typeof source === 'string') {
                return `<span class="source-badge">${escapeHtml(source)}</span>`;
            }
            // New format with text and url (ignoring url for now)
            const text = escapeHtml(source.text || 'Unknown Source');
            return `<span class="source-badge">${text}</span>`;
        }).join('');

        html += `
            <details class="sources-collapsible">
                <summary class="sources-header">Sources</summary>
                <div class="sources-content">${sourceLinks}</div>
            </details>
        `;
    }
    
    messageDiv.innerHTML = html;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    return messageId;
}

// Helper function to escape HTML for user messages
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Removed removeMessage function - no longer needed since we handle loading differently

async function createNewSession() {
    currentSessionId = null;
    chatMessages.innerHTML = '';
    addMessage('Welcome to the Medical Research Assistant! I can help you search medical research literature on various health topics. What would you like to know? (Remember: This is for educational purposes only, not medical advice.)', 'assistant', null, true);
}

// Load paper statistics
async function loadPaperStats() {
    try {
        console.log('Loading paper stats...');
        const response = await fetch(`${API_URL}/papers`);
        if (!response.ok) throw new Error('Failed to load paper stats');

        const data = await response.json();
        console.log('Paper data received:', data);

        // Update stats in UI
        if (totalPapers) {
            totalPapers.textContent = data.total_papers;
        }

        // Update paper topics
        if (paperTopics) {
            if (data.topics && data.topics.length > 0) {
                paperTopics.innerHTML = data.topics
                    .map(topic => `<div class="topic-badge">${escapeHtml(topic)}</div>`)
                    .join('');
            } else {
                paperTopics.innerHTML = '<span class="no-topics">No topics available</span>';
            }
        }

    } catch (error) {
        console.error('Error loading paper stats:', error);
        // Set default values on error
        if (totalPapers) {
            totalPapers.textContent = '0';
        }
        if (paperTopics) {
            paperTopics.innerHTML = '<span class="error">Failed to load papers</span>';
        }
    }
}