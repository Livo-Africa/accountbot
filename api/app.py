# api/app.py - SIMPLE HYBRID MODE
from flask import Flask, request, jsonify
import os
import json
import urllib.request
import re
from engine import process_command

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN is not set.")

# Get bot username from environment (without @)
BOT_USERNAME = os.environ.get('BOT_USERNAME', '').lstrip('@')

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

def should_process_message(text, chat_type):
    """
    SIMPLE HYBRID MODE:
    
    In PRIVATE CHATS (1-on-1):
    - Respond to ALL messages (current behavior)
    
    In GROUPS:
    - Respond ONLY to:
      1. Messages starting with '/' (commands)
      2. Messages containing @bot_username anywhere
      3. Current +commands, balance, help
    """
    if not text:
        return False
    
    text_lower = text.lower().strip()
    
    # In PRIVATE chats: Keep current behavior (respond to everything)
    if chat_type == 'private':
        return True
    
    # In GROUPS: Only respond to specific triggers
    elif chat_type in ['group', 'supergroup']:
        # 1. Messages starting with command prefixes
        if text_lower.startswith(('+', '/')):  # +sale, +expense, /start, etc.
            return True
        
        # 2. Exact command words
        if text_lower in ['balance', 'help']:
            return True
        
        # 3. Messages mentioning the bot
        if BOT_USERNAME and f"@{BOT_USERNAME}".lower() in text_lower:
            return True
        
        # 4. Ignore everything else
        return False
    
    # For other chat types
    return False

def clean_message_text(text, chat_type):
    """
    If in group and message contains @bot, remove the mention
    to process the command cleanly.
    """
    if not BOT_USERNAME or chat_type == 'private':
        return text.strip()
    
    # Remove @bot_username from message in groups
    mention = f"@{BOT_USERNAME}"
    text_lower = text.lower()
    mention_lower = mention.lower()
    
    if mention_lower in text_lower:
        # Remove the mention (case insensitive)
        cleaned = re.sub(re.escape(mention), '', text, flags=re.IGNORECASE)
        # Clean up extra spaces or punctuation
        cleaned = re.sub(r'^\s*[,:\s]+', '', cleaned)  # Remove leading punctuation
        cleaned = cleaned.strip()
        return cleaned if cleaned else text.strip()
    
    return text.strip()

@app.route('/api/app', methods=['POST'])
def webhook():
    """
    Main webhook with simple hybrid mode.
    """
    update = request.get_json()
    
    chat_id = None
    text = ""
    user_name = "User"
    chat_type = "private"

    # 1. CHECK FOR A TEXT MESSAGE
    if 'message' in update and 'text' in update['message']:
        message = update['message']
        chat_id = message['chat']['id']
        chat_type = message['chat']['type']  # 'private', 'group', 'supergroup'
        text = message.get('text', '').strip()
        user_name = message['from'].get('first_name', 'User')
        
        print(f"📨 Received ({chat_type}): '{text}' from {user_name}")
        
        # Check if we should process this message
        if not should_process_message(text, chat_type):
            print(f"⏭️  Ignoring non-command message in {chat_type}")
            return jsonify({'status': 'ok'})

    # 2. IGNORE OTHER UPDATES (Group joins, leaves, etc.)
    elif 'my_chat_member' in update or 'chat_member' in update:
        print("ℹ️  Ignoring chat member update.")
        return jsonify({'status': 'ok'})
    else:
        print(f"⚠️  Ignoring unhandled update type.")
        return jsonify({'status': 'ok'})

    # 3. CLEAN AND PROCESS THE MESSAGE
    if chat_id is not None and text:
        # Clean the message (remove @bot mentions if present)
        clean_text = clean_message_text(text, chat_type)
        print(f"🤖 Processing: '{clean_text}' from {user_name}")
        
        bot_reply = process_command(clean_text, user_name)
        send_telegram_message(chat_id, bot_reply)

    # 4. ALWAYS RESPOND OK TO TELEGRAM
    return jsonify({'status': 'ok'})

@app.route('/', methods=['GET'])
def index():
    return "🤖 Accounting Bot is running with Simple Hybrid Mode!"