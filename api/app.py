# api/app.py - STABLE VERSION (Handles group events)
from flask import Flask, request, jsonify
import os
import json
import urllib.request
from engine import process_command

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

@app.route('/api/app', methods=['POST'])
def webhook():
    """
    Main webhook. Safely handles messages AND group events (joins/leaves).
    This stops the 400 errors.
    """
    update = request.get_json()
    print(f"🔔 Debug: Received update type: {list(update.keys())}") # Logs what Telegram sent

    chat_id = None
    text = ""
    user_name = "User"

    # 1. CHECK FOR A TEXT MESSAGE
    if 'message' in update and 'text' in update['message']:
        message = update['message']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        user_name = message['from'].get('first_name', 'User')

    # 2. IGNORE OTHER UPDATES (Group joins, leaves, etc.) BUT RETURN 'OK'
    elif 'my_chat_member' in update or 'chat_member' in update:
        print("ℹ️  Ignoring chat member update.")
        return jsonify({'status': 'ok'})
    else:
        # If it's another unexpected type, log it but don't crash.
        print(f"⚠️  Ignoring unhandled update.")
        return jsonify({'status': 'ok'})

    # 3. PROCESS THE TEXT COMMAND
    if chat_id is not None and text:
        print(f"📨 Processing: '{text}' from {user_name}")
        bot_reply = process_command(text, user_name)
        send_telegram_message(chat_id, bot_reply)

    # 4. ALWAYS RESPOND OK TO TELEGRAM
    return jsonify({'status': 'ok'})

@app.route('/', methods=['GET'])
def index():
    return "🤖 Accounting Bot is running!"