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
    The main endpoint where Telegram sends all messages.
    This route MUST match the URL you set in the webhook.
    """
    # 1. Get the JSON data Telegram sent
    update = request.get_json()
    
    # 2. Extract the essential parts: chat ID, message text, and user's first name
    try:
        message = update['message']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        # *** FIX: Get the user's actual first name ***
        user_first_name = message['from'].get('first_name', 'User')
    except KeyError:
        # If the request doesn't have the expected structure, ignore it
        return jsonify({'status': 'bad request'}), 400
    
    # 3. Process the command using your accounting engine
    # *** FIX: Pass the user's name to the engine ***
    bot_reply = process_command(text, user_first_name)
    
    # 4. Send the reply back to the user on Telegram
    send_telegram_message(chat_id, bot_reply)
    
    # 5. Return a success response to Telegram
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