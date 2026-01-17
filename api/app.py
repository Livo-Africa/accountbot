# api/app.py - WITH DEBUG ENDPOINT
from flask import Flask, request, jsonify, render_template_string
import os
import json
import urllib.request
import re
from engine import process_command, BOT_USERNAME, DEBUG_LOG

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN is not set.")

def send_telegram_message(chat_id, text):
    """Sends a message back to Telegram."""
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = json.dumps({'chat_id': chat_id, 'text': text})
    req = urllib.request.Request(url, data=data.encode('utf-8'),
                               headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"⚠️ Failed to send message: {e}")

def clean_message_text(text):
    """Clean message text by removing bot mentions."""
    if not text or not BOT_USERNAME:
        return text.strip()
    
    # Remove @bot_username from message (case insensitive)
    mention = f"@{BOT_USERNAME}"
    text_lower = text.lower()
    mention_lower = mention.lower()
    
    if mention_lower in text_lower:
        # Find and remove the mention
        pattern = re.compile(re.escape(mention), re.IGNORECASE)
        cleaned = pattern.sub('', text)
        # Clean up extra spaces or punctuation
        cleaned = re.sub(r'^[:\s,]+|[:\s,]+$', '', cleaned)
        return cleaned.strip()
    
    return text.strip()

@app.route('/api/app', methods=['POST'])
def webhook():
    """
    Main webhook: Process ALL commands in ALL chat types.
    """
    update = request.get_json()
    
    chat_id = None
    text = ""
    user_name = "User"

    # 1. CHECK FOR A TEXT MESSAGE
    if 'message' in update and 'text' in update['message']:
        message = update['message']
        chat_id = message['chat']['id']
        chat_type = message['chat']['type']
        text = message.get('text', '').strip()
        user_name = message['from'].get('first_name', 'User')
        
        print(f"📨 Received ({chat_type}): '{text}' from {user_name}")
        
        # Clean the message (remove @bot mentions if present)
        clean_text = clean_message_text(text)
        
        # Process EVERY message through the engine
        if chat_id is not None and clean_text:
            print(f"🤖 Processing: '{clean_text}' from {user_name}")
            bot_reply = process_command(clean_text, user_name)
            
            # Only send response if the engine returned something meaningful
            if bot_reply and not bot_reply.startswith("🤔 Command not recognized"):
                send_telegram_message(chat_id, bot_reply)
            elif bot_reply and chat_type == 'private':
                # In private chats, always respond
                send_telegram_message(chat_id, bot_reply)

    # 2. IGNORE OTHER UPDATES
    elif 'my_chat_member' in update or 'chat_member' in update:
        print("ℹ️  Ignoring chat member update.")
        return jsonify({'status': 'ok'})
    else:
        print(f"⚠️  Ignoring unhandled update type.")
        return jsonify({'status': 'ok'})

    return jsonify({'status': 'ok'})

@app.route('/', methods=['GET'])
def index():
    """Main page with debug info."""
    from engine import get_status
    
    status = get_status()
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ledger Bot Debug</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .card { background: #f5f5f5; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
            .success { color: green; }
            .error { color: red; }
            .warning { color: orange; }
            .log { background: #333; color: #fff; padding: 10px; border-radius: 5px; font-family: monospace; }
            pre { white-space: pre-wrap; word-wrap: break-word; }
        </style>
    </head>
    <body>
        <h1>🤖 Ledger Bot Debug Dashboard</h1>
        
        <div class="card">
            <h2>🔧 Connection Status</h2>
            {% if status.spreadsheet_connected %}
                <p class="success">✅ Connected to Google Sheets</p>
                <p><strong>Spreadsheet:</strong> {{ status.spreadsheet_title }}</p>
                <p><strong>Worksheets:</strong> {{ ', '.join(status.worksheets) }}</p>
            {% else %}
                <p class="error">❌ NOT CONNECTED to Google Sheets</p>
                {% if status.connection_error %}
                    <p><strong>Error:</strong> {{ status.connection_error }}</p>
                {% endif %}
            {% endif %}
        </div>
        
        <div class="card">
            <h2>🔑 Environment Variables</h2>
            <ul>
                <li>GOOGLE_SHEET_ID: {% if status.google_sheet_id_set %}<span class="success">✅ Set</span>{% else %}<span class="error">❌ NOT SET</span>{% endif %}</li>
                <li>GOOGLE_CREDENTIALS: {% if status.google_credentials_set %}<span class="success">✅ Set</span>{% else %}<span class="error">❌ NOT SET</span>{% endif %}</li>
                <li>TELEGRAM_TOKEN: {% if status.telegram_token_set %}<span class="success">✅ Set</span>{% else %}<span class="error">❌ NOT SET</span>{% endif %}</li>
                <li>BOT_USERNAME: {{ status.bot_username or 'Not set' }}</li>
            </ul>
        </div>
        
        <div class="card">
            <h2>📋 Debug Logs ({{ status.debug_log_count }} total)</h2>
            <div class="log">
                {% for log in status.recent_logs %}
                    <div>{{ log }}</div>
                {% endfor %}
            </div>
        </div>
        
        <div class="card">
            <h2>🚀 Bot is Running!</h2>
            <p>Use these commands in Telegram:</p>
            <ul>
                <li><code>+sale 500 Description #category</code></li>
                <li><code>+expense 100 Description #category</code></li>
                <li><code>balance</code></li>
                <li><code>categories</code></li>
                <li><code>delete</code></li>
                <li><code>status</code> - Check connection</li>
                <li><code>help</code> - All commands</li>
            </ul>
        </div>
    </body>
    </html>
    """
    
    return render_template_string(html, status=status)

@app.route('/api/debug', methods=['GET'])
def debug_api():
    """API endpoint for debug info."""
    from engine import get_status
    status = get_status()
    return jsonify(status)

if __name__ == '__main__':
    app.run(debug=True)