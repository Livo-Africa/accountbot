# api/app.py - UPDATED FOR CONVERSATION
from flask import Flask, request, jsonify
import os
import json
import urllib.request
import re
from engine import process_command_with_conversation, BOT_USERNAME, get_status

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set.")

def send_telegram_message(chat_id, text):
    """Sends a message back to Telegram."""
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = json.dumps({'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'})
    req = urllib.request.Request(url, data=data.encode('utf-8'),
                               headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Failed to send message: {e}")

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
    user_id = None

    # 1. CHECK FOR A TEXT MESSAGE
    if 'message' in update and 'text' in update['message']:
        message = update['message']
        chat_id = message['chat']['id']
        chat_type = message['chat']['type']
        text = message.get('text', '').strip()
        user_name = message['from'].get('first_name', 'User')
        user_id = str(message['from'].get('id', ''))
        
        # Clean the message (remove @bot mentions if present)
        clean_text = clean_message_text(text)
        
        # Process EVERY message through the enhanced engine
        if chat_id is not None and clean_text:
            # Use the conversational processor
            bot_reply = process_command_with_conversation(clean_text, user_name, user_id)
            
            # Only send response if the engine returned something meaningful
            if bot_reply and not bot_reply.startswith("🤔 Command not recognized"):
                send_telegram_message(chat_id, bot_reply)
            elif bot_reply and chat_type == 'private':
                # In private chats, always respond
                send_telegram_message(chat_id, bot_reply)

    # 2. IGNORE OTHER UPDATES
    elif 'my_chat_member' in update or 'chat_member' in update:
        return jsonify({'status': 'ok'})
    else:
        return jsonify({'status': 'ok'})

    return jsonify({'status': 'ok'})

@app.route('/', methods=['GET'])
def index():
    """Simple status page - no sensitive information."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ledger Bot</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; text-align: center; }
            .container { max-width: 600px; margin: 0 auto; }
            .status { background: #4CAF50; color: white; padding: 10px; border-radius: 5px; }
            .features { text-align: left; margin: 20px 0; }
            .feature { background: #f5f5f5; padding: 10px; margin: 5px 0; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Ledger Bot</h1>
            <div class="status">
                ✅ Bot is running and connected
            </div>
            
            <div class="features">
                <h3>🌟 Features:</h3>
                <div class="feature">💰 <strong>Price Training</strong> - Learn item prices</div>
                <div class="feature">💬 <strong>Conversational AI</strong> - Natural language support</div>
                <div class="feature">📊 <strong>Financial Reports</strong> - Balance, today, week, month</div>
                <div class="feature">🏷️ <strong>Smart Categorization</strong> - Automatic with #hashtags</div>
                <div class="feature">🗑️ <strong>Safe Deletion</strong> - ID-based transaction removal</div>
            </div>
            
            <p>Use Telegram to interact with the bot naturally!</p>
            <p><strong>Try saying:</strong> "I spent 100 on lunch" or "What's my balance today?"</p>
        </div>
    </body>
    </html>
    """

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    status = get_status()
    return jsonify({
        'status': 'healthy' if status['status'] == 'connected' else 'unhealthy',
        'connected': status['status'] == 'connected',
        'price_training': 'enabled',
        'conversational_ai': 'enabled',
        'version': '2.0.0'
    })

if __name__ == '__main__':
    app.run(debug=True)