# engine.py - The core logic for your Accounting Bot
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==================== CONFIGURATION ====================
# Define what parts of Google Sheets we can access
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# ==================== GOOGLE SHEETS SETUP ====================
def get_google_sheets_client():
    """
    Connects to Google Sheets using credentials from the Vercel environment variable.
    This is the secure way to do it on platforms like Vercel.
    """
    # 1. Get the credentials JSON string from the environment variable
    credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
    
    if not credentials_json:
        # This error will appear in your Vercel logs if the variable is missing
        raise ValueError("❌ CRITICAL ERROR: The 'GOOGLE_CREDENTIALS' environment variable is not set. Please add it in your Vercel project settings.")
    
    try:
        # 2. Convert the JSON string into a Python dictionary
        credentials_info = json.loads(credentials_json)
        
        # 3. Create credentials using the dictionary (not a file)
        creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        
        # 4. Authorize and return the gspread client
        client = gspread.authorize(creds)
        return client
    except json.JSONDecodeError:
        raise ValueError("❌ The 'GOOGLE_CREDENTIALS' environment variable contains invalid JSON. Please check it in Vercel.")
    except Exception as e:
        raise Exception(f"❌ Failed to connect to Google Sheets: {str(e)}")

# Create the client connection (this runs once when the module loads)
try:
    client = get_google_sheets_client()
    # Get your Google Sheet using its ID from the environment
    SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    if not SHEET_ID:
        print("⚠️ Warning: GOOGLE_SHEET_ID environment variable is not set.")
    
    spreadsheet = client.open_by_key(SHEET_ID) if SHEET_ID else None
    transactions_sheet = spreadsheet.worksheet("Transactions") if spreadsheet else None
except Exception as e:
    # If setup fails, the error will be logged, but we allow the app to start
    # so you can see the error when you try to use a command.
    print(f"⚠️ Initial Google Sheets connection failed: {e}")
    transactions_sheet = None

# ==================== CORE FUNCTIONS ====================
def record_transaction(trans_type, amount, description="", user_name="User"):
    """
    Records a transaction (sale, expense, income) to the Google Sheet.
    *** FIX: Now accepts and uses the actual user_name. ***
    Returns a message string for the user.
    """
    # Check if we have a working connection
    if transactions_sheet is None:
        return "❌ Bot error: Not connected to the database. Check server logs."
    
    try:
        # Prepare the row of data according to YOUR sheet structure:
        # date | type | amount | description | user | timestamp
        row = [
            datetime.now().strftime('%Y-%m-%d'),  # date
            trans_type,                           # type (sale/expense/income)
            float(amount),                        # amount
            description,                          # description
            user_name,                            # *** FIX: Now uses the real user name ***
            datetime.now().isoformat()            # timestamp
        ]
        
        # Add the row to the bottom of the sheet
        transactions_sheet.append_row(row)
        
        # Success message
        return f"✅ Recorded {trans_type} of {amount} for '{description}'"
        
    except Exception as e:
        # Catch any error and return a user-friendly message
        return f"❌ Failed to save: {str(e)}"

def get_balance():
    """
    Calculates the current balance by adding all income/sales and subtracting expenses.
    *** FIX: More robust handling of data types and debug logging. ***
    """
    if transactions_sheet is None:
        return "❌ Bot error: Not connected to the database."
    
    try:
        # Get all records from the sheet
        records = transactions_sheet.get_all_records()
        # Print to logs for debugging (check Vercel logs after this)
        print(f"📊 Debug: Found {len(records)} records to process.")

        balance = 0.0
        for i, record in enumerate(records):
            # 1. Convert amount to float, safely
            try:
                # Try to get amount, handle if it's missing or a string
                amount_str = str(record.get('amount', 0)).replace(',', '').strip()
                amount_val = float(amount_str) if amount_str else 0.0
            except (ValueError, TypeError):
                print(f"⚠️ Debug: Could not convert amount in row {i+2}: {record.get('amount')}")
                amount_val = 0.0

            # 2. Check the type (case-insensitive)
            trans_type = str(record.get('type', '')).strip().lower()

            if trans_type in ['sale', 'income']:
                balance += amount_val
                print(f"  + Added {amount_val} from {trans_type}")
            elif trans_type == 'expense':
                balance -= amount_val
                print(f"  - Subtracted {amount_val} from {trans_type}")
            else:
                print(f"  ? Skipped row {i+2} with unknown type: '{trans_type}'")

        print(f"📈 Debug: Final calculated balance: {balance}")
        return f"💰 Current Balance: {balance:.2f}"

    except Exception as e:
        # This error will appear in your Vercel logs
        error_msg = f"❌ Error calculating balance: {str(e)}"
        print(error_msg)
        return error_msg

# ==================== COMMAND PROCESSOR ====================
def process_command(user_input, user_name="User"):
    """
    The main function that processes any command from Telegram.
    *** FIX: Now accepts the user_name parameter. ***
    Takes the user's text, figures out what they want, and returns a reply.
    """
    # Convert to lowercase and remove extra spaces
    text = user_input.strip().lower()
    
    # ----- Record a Sale -----
    # *** FIX: Now passes user_name to record_transaction ***
    if text.startswith('+sale'):
        # Example: "+sale 2500 Website Design"
        parts = text.split()
        
        if len(parts) < 3:  # Need at least: +sale, amount, description
            return "❌ Format: +sale [amount] [description] (e.g., +sale 1500 Website project)"
        
        try:
            amount = float(parts[1])  # Second item should be the amount
            description = ' '.join(parts[2:])  # Everything else is the description
            return record_transaction('sale', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number. Example: +sale 1500 Website project"
    
    # ----- Record an Expense -----
    # *** FIX: Now passes user_name to record_transaction ***
    elif text.startswith('+expense'):
        parts = text.split()
        
        if len(parts) < 3:
            return "❌ Format: +expense [amount] [description] (e.g., +expense 50 Office supplies)"
        
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('expense', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number. Example: +expense 50 Office supplies"
    
    # ----- Check Balance -----
    elif text == 'balance':
        return get_balance()
    
    # ----- Help Command -----
    elif text == 'help' or text == '/start':
        return """📖 **Accounting Bot Commands:**
        
*Record Transactions:*
`+sale [amount] [description]` - Record income
`+expense [amount] [description]` - Record a cost

*Get Information:*
`balance` - Check your current balance
`help` - Show this message

*Examples:*
`+sale 2000 Website design`
`+expense 300 Marketing ads`
`balance`"""
    
    # ----- Unknown Command -----
    else:
        return "🤔 Command not recognized. Type `help` to see available commands."