# engine.py - All your business logic
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import config

# --- Setup Google Sheets ---
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
client = gspread.authorize(creds)
sheet = client.open_by_key(config.GOOGLE_SHEET_ID)
transactions_sheet = sheet.worksheet("Transactions")

def record_transaction(trans_type, amount, description="", client_name=""):
    """Records a transaction to Google Sheets."""
    try:
        row = [
            datetime.now().strftime('%Y-%m-%d'),
            trans_type,
            float(amount),
            description,
            client_name,
            "user",  # You can replace with actual user ID later
            datetime.now().isoformat()
        ]
        transactions_sheet.append_row(row)
        return f"✅ Recorded {trans_type} of {amount} for {description}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def get_balance():
    """Calculates the current balance from all transactions."""
    try:
        records = transactions_sheet.get_all_records()
        balance = 0
        for record in records:
            if record['type'] in ['sale', 'income']:
                balance += record['amount']
            elif record['type'] == 'expense':
                balance -= record['amount']
        return f"💰 Current Balance: {balance}"
    except Exception as e:
        return f"❌ Error calculating balance: {str(e)}"

def process_command(text):
    """The main function that processes any user command."""
    text = text.strip().lower()
    
    if text.startswith('+sale'):
        # Example: "+sale 2500 Website client=Kojo"
        parts = text[1:].split()  # Remove the '+' and split
        if len(parts) < 2:
            return "❌ Format: +sale [amount] [description]"
        return record_transaction('sale', parts[1], ' '.join(parts[2:]))
    
    elif text.startswith('+expense'):
        parts = text[1:].split()
        if len(parts) < 2:
            return "❌ Format: +expense [amount] [description]"
        return record_transaction('expense', parts[1], ' '.join(parts[2:]))
    
    elif text == 'balance':
        return get_balance()
    
    elif text == 'help':
        return """📖 **Available Commands:**
+sale [amount] [description]
+expense [amount] [description]
balance - Check current balance
help - Show this message"""
    
    else:
        return "🤔 Command not recognized. Type 'help' for options."