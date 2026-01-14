# engine.py - MULTI-TAB VERSION
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==================== CONFIGURATION ====================
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Define which transaction type goes to which sheet
# This is the KEY CONFIGURATION for your new tabs
TYPE_TO_SHEET = {
    'sale': 'Sales',
    'expense': 'Expenses',
    'income': 'Income'  # For future use
}
# List all sheets that should be included in balance calculation
SHEETS_FOR_BALANCE = ['Sales', 'Income', 'Expenses']  # Expenses will be subtracted

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

    # Determine which sheet to use based on transaction type
    sheet_name = TYPE_TO_SHEET.get(trans_type)
    if not sheet_name:
        return f"❌ Unknown transaction type: '{trans_type}'. Can't save."

    try:
        # Open the specific worksheet (e.g., "Sales", "Expenses")
        target_sheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return f"❌ Error: The '{sheet_name}' tab was not found in the Google Sheet. Please create it."

    try:
        # Prepare the row data (same structure as before)
        row = [
            datetime.now().strftime('%Y-%m-%d'),
            trans_type,
            float(amount),
            description,
            user_name,
            datetime.now().isoformat()
        ]
        # Append to the CORRECT sheet
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
            
            if len(all_rows) <= 1:  # Only headers or empty
                print(f"  📭 {sheet_name}: No data (only headers)")
                continue

            # Find column indices
            headers = all_rows[0]
            header_lower = [h.strip().lower() for h in headers]
            try:
                amount_col_index = header_lower.index('amount')
            except ValueError:
                print(f"  ⚠️  {sheet_name}: No 'amount' column. Skipping.")
                continue

            # Sum the 'amount' column, skipping header row
            sheet_total = 0.0
            for row in all_rows[1:]:  # Skip header row
                if len(row) > amount_col_index:
                    amount_str = row[amount_col_index].strip()
                    try:
                        amount_val = float(amount_str) if amount_str else 0.0
                        sheet_total += amount_val
                    except ValueError:
                        pass  # Skip non-numeric values

            # Add or subtract based on sheet type
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
    return f"💰 Current Balance: {balance:.2f}"

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