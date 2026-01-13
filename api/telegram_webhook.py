# api/telegram_webhook.py - The webhook handler for Vercel
from http.server import BaseHTTPRequestHandler
import json
import config
from engine import process_command  # Import your logic

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 1. Telegram sends messages here
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        update = json.loads(post_data)
        
        # 2. Extract chat ID and message text
        try:
            message = update['message']
            chat_id = message['chat']['id']
            text = message.get('text', '')
        except KeyError:
            self.send_response(400)
            self.end_headers()
            return
        
        # 3. Process the command using your engine
        reply = process_command(text)
        
        # 4. Send the reply back to Telegram
        self.send_telegram_message(chat_id, reply)
        
        # 5. Send success response
        self.send_response(200)
        self.end_headers()
        return
    
    def send_telegram_message(self, chat_id, text):
        """Helper to send messages via Telegram API."""
        import urllib.request
        url = f'https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage'
        data = json.dumps({'chat_id': chat_id, 'text': text})
        req = urllib.request.Request(url, data=data.encode('utf-8'), 
                                   headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req)
    
    def do_GET(self):
        # Simple response for browser visits (optional)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")