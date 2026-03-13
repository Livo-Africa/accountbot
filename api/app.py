# api/app.py - OPTIONAL ENHANCEMENT
from flask import Flask, request, jsonify
import os
import json
import urllib.request
import re
from engine import process_command, BOT_USERNAME

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

def send_telegram_document(chat_id, pdf_buffer, filename):
    """Sends a document back to Telegram."""
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument'
    
    # Multipart/form-data boundary
    boundary = '----TelegramBoundary'
    
    parts = []
    # chat_id field
    parts.append(f'--{boundary}')
    parts.append('Content-Disposition: form-data; name="chat_id"')
    parts.append('')
    parts.append(str(chat_id))
    
    # document field
    parts.append(f'--{boundary}')
    parts.append(f'Content-Disposition: form-data; name="document"; filename="{filename}"')
    parts.append('Content-Type: application/pdf')
    parts.append('')
    parts.append(pdf_buffer.read())
    
    parts.append(f'--{boundary}--')
    parts.append('')
    
    body = b'\r\n'.join(p if isinstance(p, bytes) else p.encode('utf-8') for p in parts)
    
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Failed to send document: {e}")

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
        
        # Clean the message (remove @bot mentions if present)
        clean_text = clean_message_text(text)
        
        # Process EVERY message through the engine
        if chat_id is not None and clean_text:
            bot_reply = process_command(clean_text, user_name)
            
            # Only send response if the engine returned something meaningful
            if bot_reply:
                if isinstance(bot_reply, dict) and bot_reply.get('type') == 'document':
                    send_telegram_document(chat_id, bot_reply['buffer'], bot_reply['filename'])
                else:
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
            <h1>🤖 Ledger Bot</h1>
            <div class="status">
                ✅ Bot is running and connected
            </div>
            <p>Use Telegram to interact with the bot.</p>
            <p><strong>Getting Started:</strong> Message the bot and type "tutorial"</p>
            <p><strong>Quick Help:</strong> Type "help" for all commands</p>
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

if __name__ == '__main__':
    app.run(debug=True)