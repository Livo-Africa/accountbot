# api/app.py - The webhook server for your Accounting Bot
from flask import Flask, request, jsonify
import os
import json
import urllib.request
from engine import process_command  # Import your accounting logic

app = Flask(__name__)

# ==================== CONFIGURATION ====================
# Load the Telegram Bot Token from Vercel's environment variable
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    # This error will be visible in the logs if the variable is missing
    raise RuntimeError("❌ The 'TELEGRAM_TOKEN' environment variable is not set. Please add it in Vercel.")

# ==================== HELPER FUNCTION ====================
def send_telegram_message(chat_id, text):
    """
    Sends a message back to a user on Telegram.
    """
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = json.dumps({'chat_id': chat_id, 'text': text})
    
    # Create and send the request
    req = urllib.request.Request(url, data=data.encode('utf-8'),
                               headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        # Log any errors sending the message (visible in Vercel logs)
        print(f"⚠️ Failed to send Telegram message: {e}")

# ==================== ROUTES ====================
@app.route('/api/app', methods=['POST'])
def webhook():
    """
    The main endpoint where Telegram sends all updates.
    Safely handles different update types (messages, joins, etc.).
    """
    # 1. Get the JSON data Telegram sent
    update = request.get_json()
    
    # 2. Initialize variables (safer than assuming they exist)
    chat_id = None
    text = ""
    user_first_name = "User"

    # 3. Check if this is a MESSAGE with TEXT (the only type we process)
    if 'message' in update and 'text' in update['message']:
        message = update['message']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        user_first_name = message['from'].get('first_name', 'User')
    
    # 4. If it's a different update (user joined, left, etc.), ignore it.
    #    Telegram expects a 200 OK response even for ignored updates.
    elif 'my_chat_member' in update or 'chat_member' in update:
        # These are group membership updates. Log and ignore.
        print("ℹ️  Debug: Received a chat member update, ignoring.")
        return jsonify({'status': 'ok'})
    
    else:
        # Log other unexpected updates for debugging but ignore them
        print(f"⚠️  Debug: Received an unhandled update type: {update.keys()}")
        return jsonify({'status': 'ok'})

    # 5. If we have a valid text command, process it
    if chat_id is not None and text:
        bot_reply = process_command(text, user_first_name)
        send_telegram_message(chat_id, bot_reply)

    # 6. Always return success to Telegram
    return jsonify({'status': 'ok'})
@app.route('/', methods=['GET'])
def index():
    """
    A simple test route to verify the app is running.
    Visiting your Vercel URL in a browser triggers this.
    """
    return "🤖 Accounting Bot is running! The webhook is active at /api/app"

# ==================== START APPLICATION ====================
# This block is for running the app locally for testing.
# Vercel uses a different server, so this is ignored in production.
if __name__ == '__main__':
    app.run(debug=True)