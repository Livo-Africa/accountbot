# api/app.py - UPDATED FOR PHASE 2
from flask import Flask, request, jsonify
import os
import json
import urllib.request
import re
from engine import process_command, BOT_USERNAME, conversation_memory

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

    # 1. CHECK FOR A TEXT MESSAGE
    if 'message' in update and 'text' in update['message']:
        message = update['message']
        chat_id = message['chat']['id']
        chat_type = message['chat']['type']
        text = message.get('text', '').strip()
        
        # Get user info
        if 'from' in message:
            if 'first_name' in message['from']:
                user_name = message['from']['first_name']
            elif 'username' in message['from']:
                user_name = message['from']['username']
        
        # Clean the message (remove @bot mentions if present)
        clean_text = clean_message_text(text)
        
        # Process EVERY message through the engine
        if chat_id is not None and clean_text:
            bot_reply = process_command(clean_text, user_name)
            
            # Only send response if the engine returned something meaningful
            if bot_reply:
                send_telegram_message(chat_id, bot_reply)
            elif chat_type == 'private':
                # In private chats, always respond
                send_telegram_message(chat_id, "🤔 I'm here to help! Try `tutorial` to get started.")

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
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Ledger AI</h1>
            <div class="status">
                ✅ running and connected
            </div>
           </div>
    </body>
    </html>
    """

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint (minimal information)."""
    from engine import get_status
    status = get_status()
    return jsonify({
        'status': 'healthy' if status['status'] == 'connected' else 'unhealthy',
        'connected': status['status'] == 'connected'
    })

# ==================== PHASE 2 API ENDPOINTS ====================

@app.route('/api/conversation/<user_name>', methods=['GET'])
def get_conversation(user_name):
    """Get conversation context for a user (for debugging)."""
    from engine import get_conversation_context
    context = get_conversation_context(user_name)
    return jsonify({'user': user_name, 'context': context})

@app.route('/api/insights/<user_name>', methods=['GET'])
def get_insights(user_name):
    """Get proactive insights for a user."""
    from engine import get_proactive_insights
    insights = get_proactive_insights(user_name)
    return jsonify({'user': user_name, 'insights': insights})

@app.route('/api/clear_memory/<user_name>', methods=['POST'])
def clear_memory(user_name):
    """Clear conversation memory for a user."""
    from engine import clear_conversation_memory
    result = clear_conversation_memory(user_name)
    return jsonify({'user': user_name, 'result': result})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get bot statistics."""
    from engine import conversation_memory
    return jsonify({
        'active_users': len(conversation_memory.user_memories),
        'status': 'online'
    })

if __name__ == '__main__':
    app.run(debug=True)