# engine.py - ENHANCED VERSION WITH HYBRID MODE SUPPORT
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==================== CONFIGURATION ====================
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Define which transaction type goes to which sheet
TYPE_TO_SHEET = {
    'sale': 'Sales',
    'expense': 'Expenses',
    'income': 'Income'
}

# List all sheets that should be included in balance calculation
SHEETS_FOR_BALANCE = ['Sales', 'Income', 'Expenses']

# Get bot username from environment (for help messages)
BOT_USERNAME = os.environ.get('BOT_USERNAME', '').lstrip('@')

def get_google_sheets_client():
    """Connects to Google Sheets using the Vercel environment variable."""
    credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not credentials_json:
        raise ValueError("❌ GOOGLE_CREDENTIALS environment variable is not set.")
    try:
        credentials_info = json.loads(credentials_json)
        creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except json.JSONDecodeError:
        raise ValueError("❌ GOOGLE_CREDENTIALS contains invalid JSON.")
    except Exception as e:
        raise Exception(f"❌ Failed to connect: {str(e)}")

# Initialize connection to the main spreadsheet
try:
    client = get_google_sheets_client()
    SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    if not SHEET_ID:
        print("⚠️ Warning: GOOGLE_SHEET_ID is not set.")
    spreadsheet = client.open_by_key(SHEET_ID) if SHEET_ID else None
    print("✅ Successfully connected to Google Sheets.")
except Exception as e:
    print(f"⚠️ Initial connection failed: {e}")
    spreadsheet = None

# ==================== CORE FUNCTIONS ====================
def record_transaction(trans_type, amount, description="", user_name="User"):
    """Records a transaction to the SPECIFIC Google Sheet tab based on type."""
    if spreadsheet is None:
        return "❌ Bot error: Not connected to the database."

    sheet_name = TYPE_TO_SHEET.get(trans_type)
    if not sheet_name:
        return f"❌ Unknown transaction type: '{trans_type}'. Can't save."

    try:
        target_sheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return f"❌ Error: The '{sheet_name}' tab was not found in the Google Sheet. Please create it."

    try:
        row = [
            datetime.now().strftime('%Y-%m-%d'),
            trans_type,
            float(amount),
            description,
            user_name,
            datetime.now().isoformat()
        ]
        target_sheet.append_row(row)
        return f"✅ Recorded {trans_type} of {amount} in '{sheet_name}' tab."
    except Exception as e:
        return f"❌ Failed to save to {sheet_name}: {str(e)}"

def get_balance():
    """
    Calculates the current balance by reading from MULTIPLE sheets.
    Reads all 'Sales' and 'Income', subtracts all 'Expenses'.
    """
    if spreadsheet is None:
        return "❌ Bot error: Not connected to the database."

    balance = 0.0
    print("📊 Starting balance calculation from multiple tabs...")

    for sheet_name in SHEETS_FOR_BALANCE:
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            all_rows = worksheet.get_all_values()
            
            if len(all_rows) <= 1:
                print(f"  📭 {sheet_name}: No data (only headers)")
                continue

            headers = all_rows[0]
            header_lower = [h.strip().lower() for h in headers]
            try:
                amount_col_index = header_lower.index('amount')
            except ValueError:
                print(f"  ⚠️  {sheet_name}: No 'amount' column. Skipping.")
                continue

            sheet_total = 0.0
            for row in all_rows[1:]:
                if len(row) > amount_col_index:
                    amount_str = row[amount_col_index].strip()
                    try:
                        amount_val = float(amount_str) if amount_str else 0.0
                        sheet_total += amount_val
                    except ValueError:
                        pass

            if sheet_name in ['Sales', 'Income']:
                balance += sheet_total
                print(f"  ➕ {sheet_name}: +{sheet_total:.2f}")
            elif sheet_name == 'Expenses':
                balance -= sheet_total
                print(f"  ➖ {sheet_name}: -{sheet_total:.2f}")

        except gspread.exceptions.WorksheetNotFound:
            print(f"  ❌ {sheet_name}: Tab not found (ignoring)")
        except Exception as e:
            print(f"  ⚠️  {sheet_name}: Error reading - {str(e)}")

    print(f"📈 Final calculated balance: {balance:.2f}")
    return f"💰 Current Balance: ${balance:.2f}"

def get_help_message():
    """Returns a comprehensive help message with examples."""
    mention_example = f"@{BOT_USERNAME}" if BOT_USERNAME else "@YourBotUsername"
    
    return f"""📖 **LEDGER BOT COMMANDS**

**💼 RECORD TRANSACTIONS:**
• `+sale 500 Website design`
• `+expense 100 Office supplies`
• `+income 1000 Investment`

**📊 CHECK FINANCES:**
• `balance` - Current profit/loss
• `today` - Today's transactions (coming soon)
• `report week` - Weekly summary (coming soon)
• `report month` - Monthly summary (coming soon)

**👥 IN GROUPS:**
Use commands directly OR mention me:
• `{mention_example} balance`
• `{mention_example} +sale 300 Client payment`

**🔧 OTHER COMMANDS:**
• `help` - Show this message
• `/start` - Welcome message

**📝 EXAMPLES:**
Private chat:
  → `+sale 1500 Project Alpha`
  → `balance`

Group chat:
  → `{mention_example} +expense 75 Lunch meeting`
  → `{mention_example} balance`

Need help? Just type 'help' anytime!"""

# ==================== COMMAND PROCESSOR ====================
def process_command(user_input, user_name="User"):
    """The main function that processes any command from Telegram."""
    text = user_input.strip()
    text_lower = text.lower()

    # Clean the input if it contains bot mention
    if BOT_USERNAME:
        # Remove @bot_username from the beginning of the text
        mention_prefix = f"@{BOT_USERNAME}"
        if text_lower.startswith(mention_prefix.lower()):
            text = text[len(mention_prefix):].strip()
            text_lower = text.lower()

    # Record Sale
    if text_lower.startswith('+sale'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +sale [amount] [description]\nExample: +sale 500 Website design"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('sale', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number.\nExample: +sale 500 Website design"

    # Record Expense
    elif text_lower.startswith('+expense'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +expense [amount] [description]\nExample: +expense 100 Coffee supplies"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('expense', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number.\nExample: +expense 100 Coffee supplies"

    # Check Balance
    elif text_lower == 'balance':
        return get_balance()

    # Help
    elif text_lower in ['help', '/start', '/help']:
        return get_help_message()

    # Unknown
    else:
        return "🤔 Command not recognized.\nType 'help' for available commands and examples."