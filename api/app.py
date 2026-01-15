# api/app.py - HYBRID MODE VERSION
from flask import Flask, request, jsonify
import os
import json
import urllib.request
from engine import process_command, BOT_USERNAME

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN is not set.")

# Get bot username (without @)
TELEGRAM_BOT_USERNAME = os.environ.get('BOT_USERNAME', '').lstrip('@')
if not TELEGRAM_BOT_USERNAME:
    print("⚠️ Warning: BOT_USERNAME not set. Mention mode won't work in groups.")

def send_telegram_message(chat_id, text):
    """Sends a message back to Telegram."""
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = json.dumps({'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'})
    req = urllib.request.Request(url, data=data.encode('utf-8'),
                               headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"⚠️ Failed to send message: {e}")

def is_command_for_bot(text, chat_type):
    """
    Hybrid Mode: Determines if the bot should respond.
    
    In PRIVATE chats: Respond to ALL commands (+, balance, help, /)
    In GROUPS: Respond ONLY to:
      1. Direct commands (starts with +, balance, help, /)
      2. Messages that mention the bot (@bot_username command)
    """
    if not text or not text.strip():
        return False
    
    text_lower = text.lower().strip()
    
    # In PRIVATE chats: respond to all command patterns
    if chat_type == 'private':
        return (text_lower.startswith('+') or 
                text_lower in ['balance', 'help'] or
                text_lower.startswith('/'))
    
    # In GROUPS (or supergroups): stricter filtering
    elif chat_type in ['group', 'supergroup']:
        # Check for direct commands (must be at start of message)
        if (text_lower.startswith('+') or 
            text_lower in ['balance', 'help'] or
            text_lower.startswith('/')):
            return True
        
        # Check if bot is mentioned (anywhere in message)
        if TELEGRAM_BOT_USERNAME:
            # Check for @bot_username in the message
            mention = f"@{TELEGRAM_BOT_USERNAME}".lower()
            if mention in text_lower:
                # Check if there's a command after/before mention
                # Accept any message with bot mention + command
                return True
        
        # Not a command and bot not mentioned
        return False
    
    # For other chat types (channels), don't respond
    else:
        return False

@app.route('/api/app', methods=['POST'])
def webhook():
    """
    Main webhook with Hybrid Mode filtering.
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
        
        # HYBRID MODE: Check if this message is for the bot
        if not is_command_for_bot(text, chat_type):
            print(f"⏭️  Ignoring (not a bot command)")
            return jsonify({'status': 'ok'})

    # 2. IGNORE OTHER UPDATES (Group joins, leaves, etc.)
    elif 'my_chat_member' in update or 'chat_member' in update:
        print("ℹ️  Ignoring chat member update.")
        return jsonify({'status': 'ok'})
    else:
        print(f"⚠️  Ignoring unhandled update type.")
        return jsonify({'status': 'ok'})

    # 3. PROCESS THE COMMAND
    if chat_id is not None and text:
        print(f"🤖 Processing: '{text}' from {user_name} in {chat_type}")
        bot_reply = process_command(text, user_name)
        send_telegram_message(chat_id, bot_reply)

    # 4. ALWAYS RESPOND OK TO TELEGRAM
    return jsonify({'status': 'ok'})

@app.route('/', methods=['GET'])
def index():
    return "🤖 Ledger Bot is running with Hybrid Mode!"

# Optional: Debug endpoint to check bot username
@app.route('/debug', methods=['GET'])
def debug():
    return jsonify({
        'bot_username_set': bool(TELEGRAM_BOT_USERNAME),
        'bot_username': TELEGRAM_BOT_USERNAME,
        'status': 'online'
    })