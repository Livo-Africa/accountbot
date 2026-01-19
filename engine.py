# engine.py - FIXED VERSION
import os
import json
import gspread
import re
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from collections import defaultdict

# ==================== CONFIGURATION ====================
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

TYPE_TO_SHEET = {
    'sale': 'Sales',
    'expense': 'Expenses',
    'income': 'Income'
}

BOT_USERNAME = os.environ.get('BOT_USERNAME', '').lstrip('@')

# Global spreadsheet connection
spreadsheet = None

# ==================== ROBUST CONNECTION ====================
def get_google_sheets_client():
    """Connects to Google Sheets."""
    credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not credentials_json:
        return None
    
    try:
        credentials_info = json.loads(credentials_json)
        creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except:
        return None

def initialize_spreadsheet_connection():
    """Initialize connection to Google Sheets."""
    global spreadsheet
    
    SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    if not SHEET_ID:
        return
    
    try:
        client = get_google_sheets_client()
        if not client:
            return
        
        spreadsheet = client.open_by_key(SHEET_ID)
        
        # Update sheet structure if needed
        update_sheet_structure()
        
    except Exception:
        spreadsheet = None

# Initialize connection
initialize_spreadsheet_connection()

# ==================== HELPER FUNCTIONS ====================
def format_cedi(amount):
    """Format amount as Ghanaian Cedi with proper negative handling."""
    if amount < 0:
        return f"-₵{abs(amount):,.2f}"
    return f"₵{amount:,.2f}"

def get_sheet_headers(sheet_name):
    """Safely get headers from a sheet, returns empty list if fails."""
    if not spreadsheet:
        return []
    
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        headers = worksheet.row_values(1)
        return [h.strip().lower() for h in headers]
    except:
        return []

def find_column_index(headers, column_name):
    """Find column index safely, returns -1 if not found."""
    try:
        return headers.index(column_name.lower())
    except ValueError:
        return -1

# ==================== FIXED: SHEET STRUCTURE MANAGEMENT ====================
def update_sheet_structure():
    """Ensure all sheets have consistent column structure."""
    if not spreadsheet:
        return
    
    # Define the standard column order
    standard_columns = ['date', 'type', 'amount', 'description', 'category', 'user', 'timestamp']
    
    # Sheets to update
    sheets_to_update = ['Sales', 'Expenses', 'Income']
    
    for sheet_name in sheets_to_update:
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            current_headers = [h.strip().lower() for h in worksheet.row_values(1)]
            
            # Check if we need to add missing columns
            missing_columns = [col for col in standard_columns if col not in current_headers]
            
            if missing_columns:
                # Add missing columns
                for col in missing_columns:
                    if col == 'category':
                        # Insert after description
                        desc_idx = find_column_index(current_headers, 'description')
                        if desc_idx != -1:
                            worksheet.insert_cols([[col.capitalize()]], desc_idx + 2)
                    elif col == 'timestamp' and 'timestamp' not in current_headers:
                        # Add timestamp at the end
                        worksheet.insert_cols([[col.capitalize()]], len(current_headers) + 1)
                    
                    # Update current headers
                    current_headers.append(col)
                        
        except Exception:
            continue

# ==================== FIXED: GET TRANSACTIONS ====================
def get_transactions(sheet_name, start_date=None, end_date=None):
    """Get transactions from a specific sheet within a date range."""
    if not spreadsheet:
        return []
    
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        all_rows = worksheet.get_all_values()
        
        if len(all_rows) <= 1:
            return []
        
        # Get headers
        headers = [h.strip().lower() for h in all_rows[0]]
        
        # Find column indices (safe - returns -1 if not found)
        date_idx = find_column_index(headers, 'date')
        amount_idx = find_column_index(headers, 'amount')
        desc_idx = find_column_index(headers, 'description')
        user_idx = find_column_index(headers, 'user')
        category_idx = find_column_index(headers, 'category')
        type_idx = find_column_index(headers, 'type')
        
        # If we can't find essential columns, return empty
        if -1 in [date_idx, amount_idx, desc_idx, user_idx]:
            return []
        
        transactions = []
        
        for row in all_rows[1:]:
            if len(row) <= max(date_idx, amount_idx, desc_idx, user_idx):
                continue
            
            date_str = row[date_idx].strip()
            amount_str = row[amount_idx].strip()
            description = row[desc_idx] if desc_idx < len(row) else ''
            user = row[user_idx] if user_idx < len(row) else ''
            category = row[category_idx] if category_idx != -1 and category_idx < len(row) else ''
            
            # Determine transaction type
            if type_idx != -1 and type_idx < len(row):
                trans_type = row[type_idx].strip().lower()
            else:
                # Infer from sheet name
                trans_type = 'sale' if sheet_name.lower() == 'sales' else 'expense'
            
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
                    'type': trans_type,
                    'sheet': sheet_name
                })
            except ValueError:
                continue
        
        return transactions
        
    except Exception:
        return []

# ==================== FIXED: BALANCE CALCULATION ====================
def get_balance():
    """Calculates the current balance CORRECTLY including negative values."""
    if not spreadsheet:
        return "❌ Bot error: Not connected to the database."
    
    balance = 0.0
    transaction_count = 0
    
    # Read from all transaction sheets
    sheets_to_check = ['Sales', 'Expenses', 'Income', 'Transactions']
    
    for sheet_name in sheets_to_check:
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            all_rows = worksheet.get_all_values()
            
            if len(all_rows) <= 1:
                continue
            
            headers = [h.strip().lower() for h in all_rows[0]]
            amount_idx = find_column_index(headers, 'amount')
            type_idx = find_column_index(headers, 'type')
            
            if amount_idx == -1:
                continue
            
            for row in all_rows[1:]:
                if len(row) > amount_idx:
                    amount_str = row[amount_idx].strip()
                    try:
                        amount_val = float(amount_str) if amount_str else 0.0
                        
                        # Determine if this is income or expense
                        is_income = False
                        if type_idx != -1 and type_idx < len(row):
                            trans_type = row[type_idx].strip().lower()
                            if trans_type in ['sale', 'income']:
                                is_income = True
                            elif trans_type == 'expense':
                                is_income = False
                        else:
                            # Infer from sheet name
                            is_income = sheet_name.lower() in ['sales', 'income']
                        
                        if is_income:
                            balance += amount_val
                        else:
                            balance -= amount_val
                        
                        transaction_count += 1
                        
                    except ValueError:
                        continue
                        
        except Exception:
            continue
    
    # Format with proper negative handling
    if balance < 0:
        return f"💰 Current Balance: -₵{abs(balance):,.2f} ({transaction_count} transactions)"
    elif balance == 0:
        return f"💰 Current Balance: ₵0.00 ({transaction_count} transactions)"
    else:
        return f"💰 Current Balance: +₵{balance:,.2f} ({transaction_count} transactions)"

# ==================== FIXED: RECORD TRANSACTION ====================
def record_transaction(trans_type, amount, description="", user_name="User"):
    """Records a transaction with proper error handling."""
    if not spreadsheet:
        return "❌ Bot error: Not connected to the database."
    
    sheet_name = TYPE_TO_SHEET.get(trans_type.lower())
    if not sheet_name:
        return f"❌ Unknown transaction type: '{trans_type}'. Can't save."
    
    try:
        # Get or create worksheet
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # Create the worksheet
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=7)
            # Add standard headers
            worksheet.append_row(['Date', 'Type', 'Amount', 'Description', 'Category', 'User', 'Timestamp'])
        
        # Extract category from description
        category = ""
        clean_description = description
        
        hashtags = re.findall(r'#(\w+)', description)
        if hashtags:
            category = hashtags[0]
            clean_description = re.sub(r'#\w+', '', description).strip()
            clean_description = re.sub(r'\s+', ' ', clean_description)
        
        # Prepare row with all required columns
        row = [
            datetime.now().strftime('%Y-%m-%d'),
            trans_type.lower(),
            float(amount),
            clean_description,
            category,
            user_name,
            datetime.now().strftime('%I:%M %p')  # 12-hour format
        ]
        
        worksheet.append_row(row)
        
        response = f"✅ Recorded {trans_type} of {format_cedi(float(amount))}"
        if category:
            response += f" in category: #{category}"
        response += f" to '{sheet_name}' tab."
        
        return response
        
    except Exception as e:
        return f"❌ Failed to save: {str(e)[:100]}"

# ==================== FIXED: DELETE FUNCTION ====================
def get_last_transaction_by_user(user_name):
    """Find the user's last transaction safely."""
    if not spreadsheet:
        return None
    
    # Check all transaction sheets
    sheets_to_check = ['Sales', 'Expenses', 'Income', 'Transactions']
    
    for sheet_name in sheets_to_check:
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            all_rows = worksheet.get_all_values()
            
            if len(all_rows) <= 1:
                continue
            
            headers = [h.strip().lower() for h in all_rows[0]]
            user_idx = find_column_index(headers, 'user')
            
            if user_idx == -1:
                continue
            
            # Search from bottom (most recent)
            for i in range(len(all_rows)-1, 0, -1):
                row = all_rows[i]
                if len(row) > user_idx and row[user_idx].strip() == user_name:
                    amount_idx = find_column_index(headers, 'amount')
                    desc_idx = find_column_index(headers, 'description')
                    date_idx = find_column_index(headers, 'date')
                    type_idx = find_column_index(headers, 'type')
                    
                    return {
                        'sheet_name': sheet_name,
                        'row_index': i + 1,
                        'date': row[date_idx] if date_idx != -1 and date_idx < len(row) else '',
                        'type': row[type_idx] if type_idx != -1 and type_idx < len(row) else '',
                        'amount': row[amount_idx] if amount_idx != -1 and amount_idx < len(row) else '0',
                        'description': row[desc_idx] if desc_idx != -1 and desc_idx < len(row) else '',
                        'user': user_name
                    }
                    
        except Exception:
            continue
    
    return None

def delete_last_transaction(user_name):
    """Delete user's last transaction with audit trail."""
    if not spreadsheet:
        return "❌ Bot error: Not connected to the database."
    
    transaction = get_last_transaction_by_user(user_name)
    if not transaction:
        return "❌ No recent transactions found to delete."
    
    try:
        # Create or get DeletedTransactions sheet
        try:
            deleted_sheet = spreadsheet.worksheet('DeletedTransactions')
        except gspread.exceptions.WorksheetNotFound:
            deleted_sheet = spreadsheet.add_worksheet(
                title='DeletedTransactions',
                rows=1000,
                cols=8
            )
            deleted_sheet.append_row([
                'date', 'type', 'amount', 'description', 
                'user', 'original_sheet', 'deleted_at', 'reason'
            ])
        
        # Record deletion
        deleted_sheet.append_row([
            transaction['date'],
            transaction['type'],
            transaction['amount'],
            transaction['description'],
            transaction['user'],
            transaction['sheet_name'],
            datetime.now().strftime('%Y-%m-%d %I:%M %p'),
            f"Deleted by {user_name}"
        ])
        
        # Delete from original
        original_sheet = spreadsheet.worksheet(transaction['sheet_name'])
        original_sheet.delete_rows(transaction['row_index'])
        
        try:
            amount = float(transaction['amount'])
            amount_str = format_cedi(amount)
        except:
            amount_str = f"₵{transaction['amount']}"
        
        return f"✅ Deleted {transaction.get('type', 'transaction')} of {amount_str} from {transaction['sheet_name']} tab."
        
    except Exception as e:
        return f"❌ Failed to delete: {str(e)[:100]}"

# ==================== FIXED: CATEGORIES REPORT ====================
def get_categories_report():
    """Generate categories report safely."""
    if not spreadsheet:
        return "❌ Bot error: Not connected to the database."
    
    category_totals = defaultdict(float)
    category_counts = defaultdict(int)
    
    sheets_to_check = ['Sales', 'Expenses', 'Income']
    
    for sheet_name in sheets_to_check:
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            all_rows = worksheet.get_all_values()
            
            if len(all_rows) <= 1:
                continue
            
            headers = [h.strip().lower() for h in all_rows[0]]
            amount_idx = find_column_index(headers, 'amount')
            category_idx = find_column_index(headers, 'category')
            
            if amount_idx == -1 or category_idx == -1:
                continue
            
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
                        
        except Exception:
            continue
    
    if not category_totals:
        return "📭 No categorized transactions found.\n\n💡 **Tip**: Add #hashtag to descriptions:\nExample: +expense 500 #marketing Facebook ads"
    
    # Sort and build report
    sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    
    report = "📊 **CATEGORIES REPORT**\n\n"
    
    for category, total in sorted_categories:
        count = category_counts[category]
        report += f"**#{category}**: {format_cedi(total)} ({count} transactions)\n"
    
    # Add summary
    total_transactions = sum(category_counts.values())
    total_amount = sum(category_totals.values())
    
    report += f"\n📈 **Summary**:\n"
    report += f"• Categories: {len(category_totals)}\n"
    report += f"• Transactions: {total_transactions}\n"
    report += f"• Total Amount: {format_cedi(total_amount)}\n"
    
    if len(sorted_categories) >= 3:
        report += f"\n🏆 **Top 3**:\n"
        for i, (category, total) in enumerate(sorted_categories[:3], 1):
            emoji = "👑" if i == 1 else "🥈" if i == 2 else "🥉"
            report += f"{emoji} #{category}: {format_cedi(total)}\n"
    
    report += "\n💡 Add #hashtag to any transaction to categorize!"
    
    return report

# ==================== FIXED: TODAY'S SUMMARY ====================
def get_today_summary():
    """Get today's summary with proper error handling."""
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # Get all transactions from all sheets
    all_transactions = []
    for sheet in ['Sales', 'Expenses', 'Income', 'Transactions']:
        all_transactions.extend(get_transactions(sheet, start_date=today_str, end_date=today_str))
    
    if not all_transactions:
        return f"📊 TODAY'S SUMMARY ({today_str})\n\n📭 No transactions today yet."
    
    # Separate by type
    sales = [t for t in all_transactions if t['type'] in ['sale', 'income']]
    expenses = [t for t in all_transactions if t['type'] == 'expense']
    
    total_sales = sum(t['amount'] for t in sales)
    total_expenses = sum(t['amount'] for t in expenses)
    net = total_sales - total_expenses
    
    # Build response
    emoji = "📈" if net > 0 else "📉" if net < 0 else "➖"
    
    message = f"""📊 TODAY'S SUMMARY ({today_str})
{emoji} Net: {format_cedi(net)}

💰 Income/Sales: {format_cedi(total_sales)} ({len(sales)} transactions)"""
    
    if sales:
        top_sale = max(sales, key=lambda x: x['amount'])
        message += f"\n   👑 Top: {format_cedi(top_sale['amount'])} by {top_sale['user']}"
    
    message += f"\n💸 Expenses: {format_cedi(total_expenses)} ({len(expenses)} transactions)"
    
    if expenses:
        top_expense = max(expenses, key=lambda x: x['amount'])
        message += f"\n   💸 Top: {format_cedi(top_expense['amount'])} by {top_expense['user']}"
    
    return message

# ==================== FIXED: PERIOD SUMMARY ====================
def get_period_summary(period):
    """Get summary for week or month."""
    start_date, end_date = get_date_range(period)
    period_name = period.upper()
    
    # Get all transactions
    all_transactions = []
    for sheet in ['Sales', 'Expenses', 'Income', 'Transactions']:
        all_transactions.extend(get_transactions(sheet, start_date=start_date, end_date=end_date))
    
    if not all_transactions:
        return f"📅 {period_name}LY REPORT ({start_date} to {end_date})\n\n📭 No transactions in this period."
    
    sales = [t for t in all_transactions if t['type'] in ['sale', 'income']]
    expenses = [t for t in all_transactions if t['type'] == 'expense']
    
    total_sales = sum(t['amount'] for t in sales)
    total_expenses = sum(t['amount'] for t in expenses)
    net = total_sales - total_expenses
    
    # Group by day
    sales_by_day = defaultdict(float)
    expenses_by_day = defaultdict(float)
    
    for s in sales:
        sales_by_day[s['date']] += s['amount']
    for e in expenses:
        expenses_by_day[e['date']] += e['amount']
    
    best_day = max(sales_by_day.items(), key=lambda x: x[1], default=(None, 0))
    worst_day = max(expenses_by_day.items(), key=lambda x: x[1], default=(None, 0))
    
    # Calculate averages
    days_count = max(len(set(list(sales_by_day.keys()) + list(expenses_by_day.keys()))), 1)
    avg_daily = net / days_count
    
    # Build response
    emoji = "📈" if net > 0 else "📉" if net < 0 else "➖"
    
    message = f"""📅 {period_name}LY REPORT ({start_date} to {end_date})
{emoji} Total Profit: {format_cedi(net)}

💰 Total Income: {format_cedi(total_sales)} ({len(sales)} transactions)
💸 Total Expenses: {format_cedi(total_expenses)} ({len(expenses)} transactions)

📆 Daily Average: {format_cedi(avg_daily)}"""
    
    if best_day[0]:
        message += f"\n🏆 Best Day: {best_day[0]} ({format_cedi(best_day[1])})"
    
    if worst_day[0]:
        message += f"\n💸 Highest Spend Day: {worst_day[0]} ({format_cedi(worst_day[1])})"
    
    return message

def get_date_range(period):
    """Get start and end dates for period."""
    today = datetime.now().date()
    
    if period == 'today':
        date_str = today.strftime('%Y-%m-%d')
        return date_str, date_str
    elif period == 'week':
        start = today - timedelta(days=today.weekday())
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

# ==================== FIXED: HELP MESSAGE ====================
def get_help_message():
    """Returns help message."""
    return """📖 **LEDGER BOT COMMANDS**

**💼 RECORD TRANSACTIONS:**
• `+sale [amount] [description]`
   Example: `+sale 500 Website design #web`
• `+expense [amount] [description]`
   Example: `+expense 100 Office supplies #office`
• `+income [amount] [description]`
   Example: `+income 1000 Investment #investment`

**📊 CHECK FINANCES:**
• `balance` - Current profit/loss (negative if in debt)
• `today` - Today's transactions
• `week` - This week's report
• `month` - This month's report
• `categories` - Category breakdown

**🔄 MANAGE DATA:**
• `delete` - Remove your last transaction
• Works in both private chats and groups

**📝 EXAMPLES:**
• `+sale 1500 Project Alpha #client`
• `+expense 300 #marketing Social media ads`
• `categories`
• `delete`
• `balance`

Need help? Just type `help` anytime!"""

# ==================== COMMAND PROCESSOR ====================
def process_command(user_input, user_name="User"):
    """Process commands from Telegram."""
    if not user_input:
        return "🤔 Please enter a command."
    
    text = user_input.strip()
    text_lower = text.lower()

    # Clean mentions
    if BOT_USERNAME:
        mention_prefix = f"@{BOT_USERNAME}"
        if text_lower.startswith(mention_prefix.lower()):
            text = text[len(mention_prefix):].strip()
            text_lower = text.lower()

    # Clean punctuation
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

    # Today's Summary
    elif text_lower in ['today', 'today?', 'today.']:
        return get_today_summary()

    # Week Summary
    elif text_lower in ['week', 'weekly', 'this week']:
        return get_period_summary('week')

    # Month Summary
    elif text_lower in ['month', 'monthly', 'this month']:
        return get_period_summary('month')

    # Categories Report
    elif text_lower in ['categories', 'category', '/categories']:
        return get_categories_report()

    # Delete Last Transaction
    elif text_lower in ['delete', 'delete last', '/delete']:
        return delete_last_transaction(user_name)

    # Help
    elif text_lower in ['help', '/start', '/help', 'commands', 'menu']:
        return get_help_message()

    # Unknown
    else:
        return f"""🤔 Command not recognized.

Try one of these:
• `+sale 500 [description]`
• `+expense 100 [description]`
• `balance`
• `today`
• `categories`
• `delete`
• `help`

Type `help` for complete list!"""