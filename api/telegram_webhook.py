# api/telegram_webhook.py - Updated for Flask
from flask import Flask, request, jsonify
import os
import json
import urllib.request
from engine import process_command  # This imports your accounting logic

app = Flask(__name__)

# Load your config (make sure your .env variables are set in Vercel)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

def send_telegram_message(chat_id, text):
    """Helper function to send replies back to Telegram."""
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = json.dumps({'chat_id': chat_id, 'text': text})
    req = urllib.request.Request(url, data=data.encode('utf-8'),
                               headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req)

@app.route('/api/telegram_webhook', methods=['POST'])
def webhook():
    """The main endpoint where Telegram sends messages."""
    update = request.get_json()
    
    # Extract the message and chat ID
    try:
        message = update['message']
        chat_id = message['chat']['id']
        text = message.get('text', '')
    except KeyError:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400
    
    # Process the command using your existing engine
    bot_reply = process_command(text)
    
    # Send the reply back to the user on Telegram
    send_telegram_message(chat_id, bot_reply)
    
    # Return a successful response to Telegram
    return jsonify({'status': 'ok'})

@app.route('/')
def index():
    """A simple test route to check if the app is running."""
    return "🤖 Accounting Bot is running!"

# This is the 'app' object Vercel looks for
if __name__ == '__main__':
    app.run(debug=True)