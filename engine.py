# engine.py - FIXED VERSION WITH DEBUGGING
import os
import json
import gspread
import re
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from collections import defaultdict

# ==================== DEBUG LOGGING ====================
DEBUG_LOG = []

def debug_log(message):
    """Log debug messages to memory and print them."""
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    DEBUG_LOG.append(log_entry)
    print(log_entry)
    # Keep only last 100 log entries
    if len(DEBUG_LOG) > 100:
        DEBUG_LOG.pop(0)

# Start debug logging
debug_log("🟢 engine.py is starting...")

# ==================== CONFIGURATION ====================
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Define which transaction type goes to which sheet
TYPE_TO_SHEET = {
    'sale': 'Sales',
    'expense': 'Expenses',
    'income': 'Income'
}

# Get bot username from environment (for cleaning mentions)
BOT_USERNAME = os.environ.get('BOT_USERNAME', '').lstrip('@')
debug_log(f"🔧 BOT_USERNAME: {BOT_USERNAME if BOT_USERNAME else 'Not set'}")

# Global spreadsheet connection
spreadsheet = None
connection_error = None

def get_google_sheets_client():
    """Connects to Google Sheets using the Vercel environment variable."""
    debug_log("🔌 Attempting to connect to Google Sheets...")
    
    credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not credentials_json:
        error_msg = "❌ GOOGLE_CREDENTIALS environment variable is not set."
        debug_log(error_msg)
        raise ValueError(error_msg)
    
    try:
        debug_log("📝 Parsing GOOGLE_CREDENTIALS JSON...")
        credentials_info = json.loads(credentials_json)
        debug_log("✅ JSON parsed successfully")
        
        debug_log("🔐 Creating credentials object...")
        creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        
        debug_log("🔑 Authorizing gspread client...")
        client = gspread.authorize(creds)
        debug_log("✅ Successfully authorized Google Sheets client")
        return client
        
    except json.JSONDecodeError as e:
        error_msg = f"❌ GOOGLE_CREDENTIALS contains invalid JSON: {str(e)}"
        debug_log(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"❌ Failed to connect to Google Sheets: {str(e)}"
        debug_log(error_msg)
        raise Exception(error_msg)

def initialize_spreadsheet_connection():
    """Initialize the connection to Google Sheets."""
    global spreadsheet, connection_error
    
    debug_log("🔧 Initializing spreadsheet connection...")
    
    # Check environment variables
    SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    debug_log(f"📄 GOOGLE_SHEET_ID: {'Set' if SHEET_ID else 'NOT SET'}")
    
    if not SHEET_ID:
        connection_error = "GOOGLE_SHEET_ID environment variable is not set"
        debug_log(f"❌ {connection_error}")
        return
    
    try:
        debug_log("🔄 Creating Google Sheets client...")
        client = get_google_sheets_client()
        
        debug_log(f"📂 Opening spreadsheet with ID: {SHEET_ID[:10]}...")
        spreadsheet = client.open_by_key(SHEET_ID)
        
        debug_log(f"✅ Successfully connected to: {spreadsheet.title}")
        debug_log(f"📊 Available worksheets: {[ws.title for ws in spreadsheet.worksheets()]}")
        
        # One-time: Add category column if needed
        add_category_column_if_needed()
        
    except gspread.exceptions.SpreadsheetNotFound:
        connection_error = f"Spreadsheet not found with ID: {SHEET_ID}"
        debug_log(f"❌ {connection_error}")
    except Exception as e:
        connection_error = str(e)
        debug_log(f"❌ Connection failed: {connection_error}")

# Initialize connection when module loads
initialize_spreadsheet_connection()

# ==================== HELPER FUNCTIONS ====================
def format_cedi(amount):
    """Format amount as Ghanaian Cedi."""
    return f"₵{abs(amount):,.2f}"

def get_transactions(sheet_name, start_date=None, end_date=None):
    """Get transactions from a specific sheet within a date range."""
    if spreadsheet is None:
        debug_log(f"❌ Cannot get transactions: spreadsheet is None")
        return []
    
    try:
        debug_log(f"📖 Reading from sheet: {sheet_name}")
        worksheet = spreadsheet.worksheet(sheet_name)
        all_rows = worksheet.get_all_values()
        
        if len(all_rows) <= 1:  # Only headers
            debug_log(f"📭 {sheet_name}: No data (only headers)")
            return []
        
        # Parse headers
        headers = [h.strip().lower() for h in all_rows[0]]
        debug_log(f"📋 Headers in {sheet_name}: {headers}")
        
        try:
            date_idx = headers.index('date')
            amount_idx = headers.index('amount')
            desc_idx = headers.index('description')
            user_idx = headers.index('user')
            # Try to find category column
            category_idx = headers.index('category') if 'category' in headers else -1
        except ValueError as e:
            debug_log(f"⚠️ Missing column in {sheet_name}: {e}")
            return []
        
        transactions = []
        debug_log(f"🔍 Processing {len(all_rows)-1} rows in {sheet_name}")
        
        for row_idx, row in enumerate(all_rows[1:], start=2):
            if len(row) <= max(date_idx, amount_idx, desc_idx, user_idx):
                continue
            
            date_str = row[date_idx].strip()
            amount_str = row[amount_idx].strip()
            description = row[desc_idx] if desc_idx < len(row) else ''
            user = row[user_idx] if user_idx < len(row) else ''
            category = row[category_idx] if category_idx != -1 and category_idx < len(row) else ''
            
            # Filter by date if specified
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            
            try:
                amount = float(amount_str) if amount_str else 0.0
                transactions.append({
                    'date': date_str,
                    'amount': amount,
                    'description': description,
                    'user': user,
                    'category': category,
                    'type': 'sale' if sheet_name == 'Sales' else 'expense'
                })
            except ValueError:
                debug_log(f"⚠️ Invalid amount in row {row_idx}: {amount_str}")
                continue
        
        debug_log(f"✅ Found {len(transactions)} transactions in {sheet_name}")
        return transactions
        
    except gspread.exceptions.WorksheetNotFound:
        debug_log(f"❌ Worksheet not found: {sheet_name}")
        return []
    except Exception as e:
        debug_log(f"❌ Error reading {sheet_name}: {str(e)}")
        return []

def get_date_range(period):
    """Get start and end dates for period."""
    today = datetime.now().date()
    
    if period == 'today':
        date_str = today.strftime('%Y-%m-%d')
        return date_str, date_str
    
    elif period == 'week':
        start = today - timedelta(days=today.weekday())  # Monday
        end = today
        return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')
    
    elif period == 'month':
        start = today.replace(day=1)
        end = today
        return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')
    
    elif period == 'yesterday':
        yesterday = today - timedelta(days=1)
        date_str = yesterday.strftime('%Y-%m-%d')
        return date_str, date_str
    
    return None, None

def add_category_column_if_needed():
    """One-time function to add category column to transaction sheets."""
    if spreadsheet is None:
        debug_log("❌ Cannot add category column: spreadsheet is None")
        return
    
    tabs = ['Sales', 'Expenses', 'Income']
    
    for tab_name in tabs:
        try:
            worksheet = spreadsheet.worksheet(tab_name)
            # Get current headers
            headers = worksheet.row_values(1)
            
            # Check if category column already exists
            if 'category' not in [h.lower() for h in headers]:
                # Find description column index (0-indexed)
                try:
                    desc_index = [h.lower() for h in headers].index('description')
                    # Insert category column after description
                    debug_log(f"➕ Adding category column to {tab_name}...")
                    worksheet.insert_cols([['category']], desc_index + 2)
                    debug_log(f"✅ Added category column to {tab_name}")
                except ValueError:
                    debug_log(f"⚠️ Could not find 'description' column in {tab_name}")
            else:
                debug_log(f"✅ Category column already exists in {tab_name}")
                
        except gspread.exceptions.WorksheetNotFound:
            debug_log(f"⚠️ Tab {tab_name} not found, skipping")
        except Exception as e:
            debug_log(f"⚠️ Error setting up category column in {tab_name}: {e}")

# ==================== CORE FUNCTIONS ====================

def record_transaction(trans_type, amount, description="", user_name="User"):
    """Records a transaction to the SPECIFIC Google Sheet tab based on type."""
    debug_log(f"💾 Recording {trans_type} transaction: {amount} - {description}")
    
    if spreadsheet is None:
        error_msg = "❌ Bot error: Not connected to the database."
        debug_log(error_msg)
        return error_msg

    sheet_name = TYPE_TO_SHEET.get(trans_type)
    if not sheet_name:
        error_msg = f"❌ Unknown transaction type: '{trans_type}'. Can't save."
        debug_log(error_msg)
        return error_msg

    try:
        debug_log(f"📝 Opening worksheet: {sheet_name}")
        target_sheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        error_msg = f"❌ Error: The '{sheet_name}' tab was not found in the Google Sheet."
        debug_log(error_msg)
        return error_msg

    try:
        # Extract category from description (format: #category)
        category = ""
        clean_description = description
        
        # Find hashtags in description
        hashtags = re.findall(r'#(\w+)', description)
        if hashtags:
            # Use the first hashtag as category
            category = hashtags[0]
            # Remove the hashtag from description for cleaner display
            clean_description = re.sub(r'#\w+', '', description).strip()
            # Clean up multiple spaces
            clean_description = re.sub(r'\s+', ' ', clean_description)
            debug_log(f"🏷️  Extracted category: #{category}")
        
        # Prepare the row data with category column
        row = [
            datetime.now().strftime('%Y-%m-%d'),           # date
            trans_type,                                     # type
            float(amount),                                  # amount
            clean_description,                              # description (cleaned)
            category,                                       # category
            user_name,                                      # user
            datetime.now().strftime('%I:%M %p')            # timestamp (12-hour format)
        ]
        
        debug_log(f"📝 Appending row to {sheet_name}: {row}")
        
        # Append to the CORRECT sheet
        target_sheet.append_row(row)
        
        # Build response message
        response = f"✅ Recorded {trans_type} of {format_cedi(amount)}"
        if category:
            response += f" in category: #{category}"
        response += f" to '{sheet_name}' tab."
        
        debug_log(f"✅ Transaction recorded successfully")
        return response
        
    except Exception as e:
        error_msg = f"❌ Failed to save to {sheet_name}: {str(e)}"
        debug_log(error_msg)
        return error_msg

def get_last_transaction_by_user(user_name):
    """Find the last transaction added by a specific user."""
    if spreadsheet is None:
        debug_log("❌ Cannot get last transaction: spreadsheet is None")
        return None
    
    # Check all transaction tabs in reverse chronological order
    tabs_to_check = ['Sales', 'Expenses', 'Income']
    
    for sheet_name in tabs_to_check:
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            all_rows = worksheet.get_all_values()
            
            if len(all_rows) <= 1:  # Only headers
                continue
            
            # Find column indices
            headers = [h.strip().lower() for h in all_rows[0]]
            try:
                user_idx = headers.index('user')
                date_idx = headers.index('date')
                amount_idx = headers.index('amount')
                desc_idx = headers.index('description')
                type_idx = headers.index('type')
            except ValueError:
                continue
            
            # Search from bottom (most recent) to top
            for i in range(len(all_rows)-1, 0, -1):
                row = all_rows[i]
                if len(row) > user_idx and row[user_idx] == user_name:
                    debug_log(f"🔍 Found last transaction by {user_name} in {sheet_name}")
                    return {
                        'sheet_name': sheet_name,
                        'row_index': i + 1,  # 1-indexed for gspread
                        'date': row[date_idx] if date_idx < len(row) else '',
                        'type': row[type_idx] if type_idx < len(row) else '',
                        'amount': row[amount_idx] if amount_idx < len(row) else '0',
                        'description': row[desc_idx] if desc_idx < len(row) else '',
                        'user': user_name
                    }
                    
        except gspread.exceptions.WorksheetNotFound:
            continue
    
    debug_log(f"📭 No recent transactions found for {user_name}")
    return None

def delete_last_transaction(user_name):
    """Delete the user's last transaction and move to Deleted tab."""
    debug_log(f"🗑️  Attempting to delete last transaction by {user_name}")
    
    if spreadsheet is None:
        error_msg = "❌ Bot error: Not connected to the database."
        debug_log(error_msg)
        return error_msg
    
    # Find the transaction
    transaction = get_last_transaction_by_user(user_name)
    if not transaction:
        error_msg = "❌ No recent transactions found to delete."
        debug_log(error_msg)
        return error_msg
    
    try:
        # 1. Move to DeletedTransactions tab
        deleted_sheet_name = "DeletedTransactions"
        
        # Create DeletedTransactions tab if it doesn't exist
        try:
            deleted_sheet = spreadsheet.worksheet(deleted_sheet_name)
            debug_log(f"✅ Found existing {deleted_sheet_name} tab")
        except gspread.exceptions.WorksheetNotFound:
            # Create the tab
            debug_log(f"➕ Creating new {deleted_sheet_name} tab")
            deleted_sheet = spreadsheet.add_worksheet(
                title=deleted_sheet_name,
                rows=1000,
                cols=8
            )
            # Add headers
            deleted_sheet.append_row([
                'date', 'type', 'amount', 'description', 
                'user', 'original_timestamp', 'deleted_timestamp', 'reason'
            ])
            debug_log(f"✅ Created {deleted_sheet_name} tab")
        
        # Record to deleted tab
        deleted_timestamp = datetime.now().strftime('%Y-%m-%d %I:%M %p')
        deleted_sheet.append_row([
            transaction['date'],
            transaction['type'],
            transaction['amount'],
            transaction['description'],
            transaction['user'],
            datetime.now().strftime('%Y-%m-%d %I:%M %p'),
            deleted_timestamp,
            f"Deleted by {user_name} via /delete command"
        ])
        
        debug_log(f"📝 Recorded to {deleted_sheet_name} tab")
        
        # 2. Delete from original sheet
        debug_log(f"🗑️  Deleting row {transaction['row_index']} from {transaction['sheet_name']}")
        original_sheet = spreadsheet.worksheet(transaction['sheet_name'])
        original_sheet.delete_rows(transaction['row_index'])
        
        # Format the amount nicely
        try:
            amount = float(transaction['amount'])
            amount_str = format_cedi(amount)
        except:
            amount_str = transaction['amount']
        
        response = f"✅ Deleted {transaction['type']} of {amount_str} from {transaction['sheet_name']} tab."
        debug_log(f"✅ {response}")
        return response
        
    except Exception as e:
        error_msg = f"❌ Failed to delete transaction: {str(e)}"
        debug_log(error_msg)
        return error_msg

def get_categories_report():
    """Generate a report of all categories and their totals."""
    debug_log("📊 Generating categories report")
    
    if spreadsheet is None:
        error_msg = "❌ Bot error: Not connected to the database."
        debug_log(error_msg)
        return error_msg
    
    category_totals = defaultdict(float)
    category_counts = defaultdict(int)
    
    # Check all transaction tabs
    tabs_to_check = ['Sales', 'Expenses', 'Income']
    
    for sheet_name in tabs_to_check:
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            all_rows = worksheet.get_all_values()
            
            if len(all_rows) <= 1:
                continue
            
            # Find column indices
            headers = [h.strip().lower() for h in all_rows[0]]
            try:
                amount_idx = headers.index('amount')
                # Try to find category column
                if 'category' in headers:
                    category_idx = headers.index('category')
                else:
                    debug_log(f"⚠️ No category column in {sheet_name}")
                    continue
            except ValueError:
                continue
            
            # Process each transaction
            for row in all_rows[1:]:
                if len(row) > max(amount_idx, category_idx):
                    category = row[category_idx].strip()
                    if not category:
                        category = "Uncategorized"
                    
                    amount_str = row[amount_idx].strip()
                    try:
                        amount = float(amount_str) if amount_str else 0.0
                        category_totals[category] += amount
                        category_counts[category] += 1
                    except ValueError:
                        pass
                        
        except gspread.exceptions.WorksheetNotFound:
            continue
    
    if not category_totals:
        debug_log("📭 No categorized transactions found")
        return "📭 No categorized transactions found.\n\n💡 **Tip**: Add #hashtag to your descriptions:\nExample: +expense 500 #marketing Facebook ads"
    
    # Sort categories by total amount (descending)
    sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    
    debug_log(f"📊 Found {len(sorted_categories)} categories")
    
    # Build the report
    report = "📊 **CATEGORIES REPORT**\n\n"
    
    for category, total in sorted_categories:
        count = category_counts[category]
        report += f"**#{category}**: {format_cedi(total)} ({count} transactions)\n"
    
    # Add summary
    total_transactions = sum(category_counts.values())
    total_amount = sum(category_totals.values())
    
    report += f"\n📈 **Summary**:\n"
    report += f"• Total Categories: {len(category_totals)}\n"
    report += f"• Total Transactions: {total_transactions}\n"
    report += f"• Total Amount: {format_cedi(total_amount)}\n"
    
    # Add top 3 categories
    if len(sorted_categories) >= 3:
        report += f"\n🏆 **Top 3 Categories**:\n"
        for i, (category, total) in enumerate(sorted_categories[:3], 1):
            emoji = "👑" if i == 1 else "🥈" if i == 2 else "🥉"
            report += f"{emoji} #{category}: {format_cedi(total)}\n"
    
    report += "\n💡 **Tip**: Add #hashtag to any transaction to categorize it!"
    
    debug_log("✅ Categories report generated successfully")
    return report

# ==================== EXISTING CORE FUNCTIONS ====================

def get_balance():
    """Calculates the current balance."""
    debug_log("💰 Calculating balance...")
    
    if spreadsheet is None:
        error_msg = "❌ Bot error: Not connected to the database."
        debug_log(error_msg)
        return error_msg

    balance = 0.0
    
    for sheet_name in ['Sales', 'Income', 'Expenses']:
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            all_rows = worksheet.get_all_values()
            
            if len(all_rows) <= 1:
                continue

            headers = [h.strip().lower() for h in all_rows[0]]
            try:
                amount_idx = headers.index('amount')
            except ValueError:
                continue

            sheet_total = 0.0
            for row in all_rows[1:]:
                if len(row) > amount_idx:
                    amount_str = row[amount_idx].strip()
                    try:
                        amount_val = float(amount_str) if amount_str else 0.0
                        sheet_total += amount_val
                    except ValueError:
                        pass

            if sheet_name in ['Sales', 'Income']:
                balance += sheet_total
                debug_log(f"➕ {sheet_name}: +{sheet_total:.2f}")
            elif sheet_name == 'Expenses':
                balance -= sheet_total
                debug_log(f"➖ {sheet_name}: -{sheet_total:.2f}")

        except gspread.exceptions.WorksheetNotFound:
            debug_log(f"⚠️ {sheet_name}: Tab not found")
        except Exception as e:
            debug_log(f"⚠️ {sheet_name}: Error reading - {str(e)}")

    debug_log(f"📈 Final calculated balance: {balance:.2f}")
    return f"💰 Current Balance: {format_cedi(balance)}"

# ... [Rest of the functions like get_today_summary, get_stats, etc. remain the same] ...
# I'm truncating to save space, but keep all your existing functions

def get_status():
    """Get the current bot status for debugging."""
    status = {
        'spreadsheet_connected': spreadsheet is not None,
        'connection_error': connection_error,
        'google_sheet_id_set': bool(os.environ.get('GOOGLE_SHEET_ID')),
        'google_credentials_set': bool(os.environ.get('GOOGLE_CREDENTIALS')),
        'telegram_token_set': bool(os.environ.get('TELEGRAM_TOKEN')),
        'bot_username': BOT_USERNAME,
        'debug_log_count': len(DEBUG_LOG),
        'recent_logs': DEBUG_LOG[-10:] if DEBUG_LOG else []
    }
    
    if spreadsheet:
        try:
            status['spreadsheet_title'] = spreadsheet.title
            status['worksheets'] = [ws.title for ws in spreadsheet.worksheets()]
        except:
            status['spreadsheet_title'] = "Error getting title"
            status['worksheets'] = []
    
    return status

# ==================== COMMAND PROCESSOR ====================
def process_command(user_input, user_name="User"):
    """The main function that processes any command from Telegram."""
    debug_log(f"📨 Processing command from {user_name}: '{user_input}'")
    
    text = user_input.strip()
    text_lower = text.lower()

    # Clean the input if it contains bot mention
    if BOT_USERNAME:
        mention_prefix = f"@{BOT_USERNAME}"
        if text_lower.startswith(mention_prefix.lower()):
            text = text[len(mention_prefix):].strip()
            text_lower = text.lower()

    # Remove any leading/trailing punctuation
    text_lower = re.sub(r'^[:\s]+|[:\s]+$', '', text_lower)

    # Record Sale
    if text_lower.startswith('+sale'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +sale [amount] [description]\nExample: +sale 500 Website design #web"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('sale', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number.\nExample: +sale 500 Website design #web"

    # Record Expense
    elif text_lower.startswith('+expense'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +expense [amount] [description]\nExample: +expense 100 Coffee supplies #office"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('expense', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number.\nExample: +expense 100 Coffee supplies #office"

    # Record Income
    elif text_lower.startswith('+income'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +income [amount] [description]\nExample: +income 1000 Investment #investment"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('income', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number.\nExample: +income 1000 Investment #investment"

    # Check Balance
    elif text_lower in ['balance', 'profit', 'net']:
        return get_balance()

    # Categories Report
    elif text_lower in ['categories', 'category', '/categories']:
        return get_categories_report()

    # Delete Last Transaction
    elif text_lower in ['delete', 'delete last', '/delete']:
        return delete_last_transaction(user_name)

    # Status/debug command
    elif text_lower in ['status', 'debug', '/status']:
        status = get_status()
        response = "🔧 **BOT STATUS**\n\n"
        
        if status['spreadsheet_connected']:
            response += "✅ **Connected to Google Sheets**\n"
            response += f"📊 Spreadsheet: {status.get('spreadsheet_title', 'Unknown')}\n"
            response += f"📁 Worksheets: {', '.join(status.get('worksheets', []))}\n"
        else:
            response += "❌ **NOT CONNECTED to Google Sheets**\n"
            if status['connection_error']:
                response += f"📛 Error: {status['connection_error']}\n"
        
        response += f"\n🔑 **Environment Variables:**\n"
        response += f"• GOOGLE_SHEET_ID: {'✅ Set' if status['google_sheet_id_set'] else '❌ NOT SET'}\n"
        response += f"• GOOGLE_CREDENTIALS: {'✅ Set' if status['google_credentials_set'] else '❌ NOT SET'}\n"
        response += f"• TELEGRAM_TOKEN: {'✅ Set' if status['telegram_token_set'] else '❌ NOT SET'}\n"
        response += f"• BOT_USERNAME: {status['bot_username'] or 'Not set'}\n"
        
        response += f"\n📋 **Recent Logs ({len(status['recent_logs'])}):**\n"
        for log in status['recent_logs']:
            response += f"• {log}\n"
        
        return response

    # Help
    elif text_lower in ['help', '/start', '/help', 'commands', 'menu']:
        return get_help_message()

    # Unknown - but be helpful
    else:
        return f"""🤔 Command not recognized.

Try one of these:
• `+sale 500 [description]` - Record income
• `+expense 100 [description]` - Record cost
• `balance` - Check current balance
• `today` - Today's summary
• `categories` - Category breakdown
• `delete` - Remove last transaction
• `status` - Check bot connection status
• `help` - Show all commands

Type `help` for complete list!"""