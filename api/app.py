# api/app.py - OPTIONAL ENHANCEMENT
from flask import Flask, request, jsonify
import os
import json
import urllib.request
import re
from engine import process_command, BOT_USERNAME, add_to_conversation_history

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


# Wake words the bot responds to in group chats (case-insensitive)
WAKE_WORDS = ['bottie', 'botti']

# Command prefixes that don't need a wake word
COMMAND_PREFIXES = ('+', '/')

# Exact command words that don't need a wake word
EXACT_COMMANDS = {
    'help', 'balance', 'today', 'week', 'month', 'tutorial', 'guide',
    'quickstart', 'examples', 'commands', 'menu', 'budgets', 'orders',
    'clients', 'insights', 'reminders', 'goals'
}

# Junk messages to ignore entirely (saves API calls)
JUNK_MESSAGES = {
    'ok', 'okay', 'k', 'kk', 'lol', 'lmao', 'haha', 'hehe', 'hmm',
    'nice', 'true', 'yes', 'no', 'yep', 'nah', 'nope', 'sure', 'cool',
    'wow', 'damn', 'bruh', 'fr', 'gg', 'smh', 'tbh', 'ikr', 'idk',
    'same', 'facts', 'bet', 'say less', 'aight'
}

def is_bot_triggered(text, chat_type):
    """
    Determine if the bot should respond to this message.
    Returns (should_respond: bool, cleaned_text: str)
    """
    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    # --- Private chats: always respond ---
    if chat_type == 'private':
        # Still filter junk in private chats to save Gemini calls
        if text_lower in JUNK_MESSAGES:
            return False, ""
        # Filter very short non-command messages (emojis, single chars)
        if len(text_stripped) <= 2 and not text_lower.startswith(('+', '/')):
            return False, ""
        return True, text_stripped

    # --- Group chats: only respond if triggered ---

    # 1. Check for @bot mention
    if BOT_USERNAME:
        mention = f"@{BOT_USERNAME}".lower()
        if mention in text_lower:
            # Remove the mention and clean up
            pattern = re.compile(re.escape(f"@{BOT_USERNAME}"), re.IGNORECASE)
            cleaned = pattern.sub('', text_stripped)
            cleaned = re.sub(r'^[:\s,]+|[:\s,]+$', '', cleaned).strip()
            return True, cleaned if cleaned else "help"

    # 2. Check for wake words ("bottie", "botti")
    for wake_word in WAKE_WORDS:
        if text_lower.startswith(wake_word):
            # Strip the wake word and clean up
            cleaned = text_stripped[len(wake_word):].strip()
            cleaned = re.sub(r'^[:\s,]+', '', cleaned).strip()
            return True, cleaned if cleaned else "help"

    # 3. Check for command prefixes (+sale, /help, etc.)
    if text_lower.startswith(COMMAND_PREFIXES):
        return True, text_stripped

    # 4. Check for exact command words
    first_word = text_lower.split()[0] if text_lower.split() else ""
    if first_word in EXACT_COMMANDS:
        return True, text_stripped

    # Not triggered — stay silent
    return False, ""

def clean_message_text(text):
    """Clean message text by removing bot mentions and wake words."""
    if not text:
        return text.strip()

    cleaned = text.strip()

    # Remove @bot_username
    if BOT_USERNAME:
        mention = f"@{BOT_USERNAME}"
        if mention.lower() in cleaned.lower():
            pattern = re.compile(re.escape(mention), re.IGNORECASE)
            cleaned = pattern.sub('', cleaned)
            cleaned = re.sub(r'^[:\s,]+|[:\s,]+$', '', cleaned).strip()

    # Remove wake words from start
    for wake_word in WAKE_WORDS:
        if cleaned.lower().startswith(wake_word):
            cleaned = cleaned[len(wake_word):].strip()
            cleaned = re.sub(r'^[:\s,]+', '', cleaned).strip()
            break

    return cleaned if cleaned else "help"

@app.route('/api/app', methods=['POST'])
def webhook():
    """
    Main webhook: Smart filtering — only responds when triggered.
    Private chats: always responds (except junk).
    Group chats: only responds to wake word 'bottie', @mention, or command prefix.
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

        # Smart filtering: should the bot respond?
        should_respond, clean_text = is_bot_triggered(text, chat_type)

        if not should_respond:
            # Stay silent — don't waste API calls
            return jsonify({'status': 'ok'})

        # Process the cleaned message through the engine
        if chat_id is not None and clean_text:
            bot_reply = process_command(clean_text, user_name)

            # Only send response if the engine returned something meaningful
            if bot_reply:
                # Record bot response in conversation history
                if isinstance(bot_reply, str):
                    add_to_conversation_history(user_name, 'bot', bot_reply)
                
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