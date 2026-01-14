# engine.py - FIXED VERSION (With working balance calculator)
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==================== GOOGLE SHEETS SETUP ====================
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

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

# Initialize connection
try:
    client = get_google_sheets_client()
    SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    if not SHEET_ID:
        print("⚠️ Warning: GOOGLE_SHEET_ID is not set.")
    spreadsheet = client.open_by_key(SHEET_ID) if SHEET_ID else None
    transactions_sheet = spreadsheet.worksheet("Transactions") if spreadsheet else None
    print("✅ Successfully connected to Google Sheets.")
except Exception as e:
    print(f"⚠️ Initial connection failed: {e}")
    transactions_sheet = None

# ==================== CORE FUNCTIONS ====================
def record_transaction(trans_type, amount, description="", user_name="User"):
    """Records a transaction to the Google Sheet."""
    if transactions_sheet is None:
        return "❌ Bot error: Not connected to the database."

    try:
        # YOUR SHEET STRUCTURE: date | type | amount | description | user | timestamp
        row = [
            datetime.now().strftime('%Y-%m-%d'),
            trans_type,        # 'sale', 'expense', 'income'
            float(amount),
            description,
            user_name,         # Now uses real user name
            datetime.now().isoformat()
        ]
        transactions_sheet.append_row(row)
        return f"✅ Recorded {trans_type} of {amount} for '{description}'"
    except Exception as e:
        return f"❌ Failed to save: {str(e)}"

def get_balance():
    """
    FIXED FUNCTION: Calculates current balance.
    Provides detailed debug info in Vercel logs.
    """
    if transactions_sheet is None:
        return "❌ Bot error: Not connected to the database."

    try:
        # Get all data
        all_rows = transactions_sheet.get_all_values() # Gets everything, including headers
        if not all_rows or len(all_rows) <= 1:
            print("📊 Debug: Sheet is empty (only headers or no data).")
            return "💰 Current Balance: 0.00"

        # Extract headers (first row) and data (subsequent rows)
        headers = all_rows[0]
        data_rows = all_rows[1:]

        print(f"📊 Debug: Sheet Headers -> {headers}")
        print(f"📊 Debug: Found {len(data_rows)} data rows to process.")

        # Find column indices (case-insensitive)
        header_lower = [h.strip().lower() for h in headers]
        try:
            type_col_index = header_lower.index('type')
            amount_col_index = header_lower.index('amount')
        except ValueError as e:
            error_msg = f"❌ Critical: Could not find 'type' or 'amount' column. Headers are: {headers}"
            print(error_msg)
            return error_msg

        balance = 0.0
        for i, row in enumerate(data_rows):
            # Ensure row has enough columns
            if len(row) <= max(type_col_index, amount_col_index):
                print(f"⚠️  Row {i+2} has too few columns: {row}. Skipping.")
                continue

            trans_type = row[type_col_index].strip().lower()
            amount_str = row[amount_col_index].strip()

            # Skip rows where type is empty (like your old manual data)
            if not trans_type:
                print(f"⏭️  Skipping row {i+2}: Empty 'type'. Data: {row}")
                continue

            # Convert amount
            try:
                amount_val = float(amount_str) if amount_str else 0.0
            except ValueError:
                print(f"⚠️  Row {i+2}: Cannot convert amount '{amount_str}' to number. Using 0.")
                amount_val = 0.0

            # Calculate
            if trans_type in ['sale', 'income']:
                balance += amount_val
                print(f"  ➕ Row {i+2}: Added {amount_val} ({trans_type})")
            elif trans_type == 'expense':
                balance -= amount_val
                print(f"  ➖ Row {i+2}: Subtracted {amount_val} ({trans_type})")
            else:
                print(f"  ❓ Row {i+2}: Unknown type '{trans_type}'. Skipping.")

        print(f"📈 Debug: Final calculated balance: {balance:.2f}")
        return f"💰 Current Balance: {balance:.2f}"

    except Exception as e:
        error_msg = f"❌ Error calculating balance: {str(e)}"
        print(error_msg)
        return error_msg

# ==================== COMMAND PROCESSOR ====================
def process_command(user_input, user_name="User"):
    """The main function that processes any command from Telegram."""
    text = user_input.strip().lower()

    # Record Sale
    if text.startswith('+sale'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +sale [amount] [description]"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('sale', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number."

    # Record Expense
    elif text.startswith('+expense'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +expense [amount] [description]"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('expense', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number."

    # Check Balance
    elif text == 'balance':
        return get_balance()

    # Help
    elif text in ['help', '/start', '/help']:
        return """📖 **Accounting Bot Commands:**
+sale [amount] [description]
+expense [amount] [description]
balance
help"""

    # Unknown
    else:
        return "🤔 Command not recognized. Type 'help'."