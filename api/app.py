# api/app.py - SIMPLE UNIVERSAL MODE
from flask import Flask, request, jsonify
import os
import json
import urllib.request
import re
from engine import process_command, BOT_USERNAME

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
    Simple webhook: Process ALL commands in ALL chat types.
    The engine.py will handle command recognition.
    """
    update = request.get_json()
    
    chat_id = None
    text = ""
    user_name = "User"

    # 1. CHECK FOR A TEXT MESSAGE
    if 'message' in update and 'text' in update['message']:
        message = update['message']
        chat_id = message['chat']['id']
        chat_type = message['chat']['type']  # 'private', 'group', 'supergroup'
        text = message.get('text', '').strip()
        user_name = message['from'].get('first_name', 'User')
        
        print(f"📨 Received ({chat_type}): '{text}' from {user_name}")
        
        # Clean the message (remove @bot mentions if present)
        clean_text = clean_message_text(text)
        
        # Process EVERY message through the engine
        # The engine will decide if it's a valid command
        if chat_id is not None and clean_text:
            print(f"🤖 Processing: '{clean_text}' from {user_name}")
            bot_reply = process_command(clean_text, user_name)
            
            # Only send response if the engine returned something meaningful
            # (not the "Command not recognized" message for casual chat)
            if bot_reply and not bot_reply.startswith("🤔 Command not recognized"):
                send_telegram_message(chat_id, bot_reply)
            elif bot_reply and chat_type == 'private':
                # In private chats, always respond (even to say "command not recognized")
                send_telegram_message(chat_id, bot_reply)

    # 2. IGNORE OTHER UPDATES (Group joins, leaves, etc.)
    elif 'my_chat_member' in update or 'chat_member' in update:
        print("ℹ️  Ignoring chat member update.")
        return jsonify({'status': 'ok'})
    else:
        print(f"⚠️  Ignoring unhandled update type.")
        return jsonify({'status': 'ok'})

    # 3. ALWAYS RESPOND OK TO TELEGRAM
    return jsonify({'status': 'ok'})

@app.route('/', methods=['GET'])
def index():
    return "🤖 Ledger Bot is running! All commands available everywhere."

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'bot_username': BOT_USERNAME,
        'mode': 'universal_commands'
    })