# engine.py - COMPREHENSIVE VERSION (All commands available everywhere)
import os
import json
import gspread
import re
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from collections import defaultdict

# ==================== CONFIGURATION ====================
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Define which transaction type goes to which sheet
TYPE_TO_SHEET = {
    'sale': 'Sales',
    'expense': 'Expenses',
    'income': 'Income'
}

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

# ==================== HELPER FUNCTIONS ====================
def get_transactions(sheet_name, start_date=None, end_date=None):
    """Get transactions from a specific sheet within a date range."""
    if spreadsheet is None:
        return []
    
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        all_rows = worksheet.get_all_values()
        
        if len(all_rows) <= 1:  # Only headers
            return []
        
        # Parse headers
        headers = [h.strip().lower() for h in all_rows[0]]
        try:
            date_idx = headers.index('date')
            amount_idx = headers.index('amount')
            desc_idx = headers.index('description')
            user_idx = headers.index('user')
        except ValueError:
            return []
        
        transactions = []
        for row in all_rows[1:]:
            if len(row) <= max(date_idx, amount_idx, desc_idx, user_idx):
                continue
            
            date_str = row[date_idx].strip()
            amount_str = row[amount_idx].strip()
            description = row[desc_idx] if desc_idx < len(row) else ''
            user = row[user_idx] if user_idx < len(row) else ''
            
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
                    'type': 'sale' if sheet_name == 'Sales' else 'expense'
                })
            except ValueError:
                continue
        
        return transactions
    except Exception as e:
        print(f"⚠️ Error reading {sheet_name}: {e}")
        return []

def format_currency(amount):
    """Format amount as currency."""
    return f"${abs(amount):,.2f}"

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

def get_all_time_stats():
    """Get all-time statistics."""
    sales = get_transactions('Sales')
    expenses = get_transactions('Expenses')
    
    total_sales = sum(t['amount'] for t in sales)
    total_expenses = sum(t['amount'] for t in expenses)
    total_profit = total_sales - total_expenses
    
    avg_sale = total_sales / len(sales) if sales else 0
    avg_expense = total_expenses / len(expenses) if expenses else 0
    
    return {
        'total_sales': total_sales,
        'total_expenses': total_expenses,
        'total_profit': total_profit,
        'sales_count': len(sales),
        'expenses_count': len(expenses),
        'avg_sale': avg_sale,
        'avg_expense': avg_expense
    }

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
        return f"❌ Error: The '{sheet_name}' tab was not found in the Google Sheet."

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
        return f"✅ Recorded {trans_type} of {format_currency(amount)} in '{sheet_name}' tab."
    except Exception as e:
        return f"❌ Failed to save to {sheet_name}: {str(e)}"

def get_balance():
    """Calculates the current balance."""
    if spreadsheet is None:
        return "❌ Bot error: Not connected to the database."

    balance = 0.0
    print("📊 Starting balance calculation from multiple tabs...")

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
            elif sheet_name == 'Expenses':
                balance -= sheet_total

        except gspread.exceptions.WorksheetNotFound:
            pass
        except Exception as e:
            print(f"⚠️ {sheet_name}: Error reading - {str(e)}")

    return f"💰 Current Balance: {format_currency(balance)}"

def get_today_summary():
    """Get today's sales and expenses summary."""
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    sales = get_transactions('Sales', start_date=today_str, end_date=today_str)
    expenses = get_transactions('Expenses', start_date=today_str, end_date=today_str)
    
    total_sales = sum(t['amount'] for t in sales)
    total_expenses = sum(t['amount'] for t in expenses)
    net = total_sales - total_expenses
    
    # Find top expense
    top_expense = max(expenses, key=lambda x: x['amount'], default=None)
    top_sale = max(sales, key=lambda x: x['amount'], default=None)
    
    # Build response
    emoji = "📈" if net > 0 else "📉" if net < 0 else "➖"
    
    message = f"""📊 TODAY'S SUMMARY ({today_str})
{emoji} Net: {format_currency(net)}

💰 Sales: {format_currency(total_sales)} ({len(sales)} transaction{'s' if len(sales) != 1 else ''})"""
    
    if top_sale:
        message += f"\n   👑 Top Sale: {format_currency(top_sale['amount'])} by {top_sale['user']}"
        message += f"\n      \"{top_sale['description'][:40]}{'...' if len(top_sale['description']) > 40 else ''}\""
    
    message += f"\n💸 Expenses: {format_currency(total_expenses)} ({len(expenses)} transaction{'s' if len(expenses) != 1 else ''})"
    
    if top_expense:
        message += f"\n   💸 Top Expense: {format_currency(top_expense['amount'])} by {top_expense['user']}"
        message += f"\n      \"{top_expense['description'][:40]}{'...' if len(top_expense['description']) > 40 else ''}\""
    
    if not sales and not expenses:
        message += "\n\n📭 No transactions today yet."
    
    return message

def get_yesterday_summary():
    """Get yesterday's summary."""
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    sales = get_transactions('Sales', start_date=yesterday_str, end_date=yesterday_str)
    expenses = get_transactions('Expenses', start_date=yesterday_str, end_date=yesterday_str)
    
    total_sales = sum(t['amount'] for t in sales)
    total_expenses = sum(t['amount'] for t in expenses)
    net = total_sales - total_expenses
    
    emoji = "📈" if net > 0 else "📉" if net < 0 else "➖"
    
    message = f"""📊 YESTERDAY'S SUMMARY ({yesterday_str})
{emoji} Net: {format_currency(net)}

💰 Sales: {format_currency(total_sales)} ({len(sales)} transactions)
💸 Expenses: {format_currency(total_expenses)} ({len(expenses)} transactions)"""
    
    if not sales and not expenses:
        message += "\n\n📭 No transactions yesterday."
    
    return message

def get_period_summary(period):
    """Get summary for week or month."""
    start_date, end_date = get_date_range(period)
    period_name = period.upper()
    
    sales = get_transactions('Sales', start_date=start_date, end_date=end_date)
    expenses = get_transactions('Expenses', start_date=start_date, end_date=end_date)
    
    total_sales = sum(t['amount'] for t in sales)
    total_expenses = sum(t['amount'] for t in expenses)
    net = total_sales - total_expenses
    
    # Group by day for insights
    sales_by_day = defaultdict(float)
    expenses_by_day = defaultdict(float)
    
    for s in sales:
        sales_by_day[s['date']] += s['amount']
    for e in expenses:
        expenses_by_day[e['date']] += e['amount']
    
    best_day = max(sales_by_day.items(), key=lambda x: x[1], default=(None, 0))
    worst_day = max(expenses_by_day.items(), key=lambda x: x[1], default=(None, 0))
    
    # Calculate averages
    days_count = len(set(list(sales_by_day.keys()) + list(expenses_by_day.keys()))) or 1
    avg_daily_profit = net / days_count
    
    # Build response
    emoji = "📈" if net > 0 else "📉" if net < 0 else "➖"
    period_display = f"{period_name}LY ({start_date} to {end_date})"
    
    message = f"""📅 {period_display} REPORT
{emoji} Total Profit: {format_currency(net)}

💰 Total Sales: {format_currency(total_sales)} ({len(sales)} transactions)
💸 Total Expenses: {format_currency(total_expenses)} ({len(expenses)} transactions)

📆 Daily Average: {format_currency(avg_daily_profit)}"""
    
    if best_day[0]:
        message += f"\n🏆 Best Day: {best_day[0]} ({format_currency(best_day[1])} in sales)"
    
    if worst_day[0]:
        message += f"\n💸 Heaviest Spending Day: {worst_day[0]} ({format_currency(worst_day[1])} in expenses)"
    
    # Add top transactions
    if sales:
        top_sale = max(sales, key=lambda x: x['amount'])
        message += f"\n\n👑 Top Sale: {format_currency(top_sale['amount'])}"
        message += f"\n   By: {top_sale['user']} | {top_sale['description'][:40]}"
    
    if expenses:
        top_expense = max(expenses, key=lambda x: x['amount'])
        message += f"\n💸 Top Expense: {format_currency(top_expense['amount'])}"
        message += f"\n   By: {top_expense['user']} | {top_expense['description'][:40]}"
    
    return message

def get_top_transaction(trans_type):
    """Get the largest transaction of a specific type."""
    sheet_name = 'Sales' if trans_type == 'sale' else 'Expenses'
    transactions = get_transactions(sheet_name)
    
    if not transactions:
        return f"❌ No {trans_type}s found."
    
    top = max(transactions, key=lambda x: x['amount'])
    
    emoji = "👑" if trans_type == 'sale' else "💸"
    title = "TOP SALE" if trans_type == 'sale' else "TOP EXPENSE"
    
    message = f"""{emoji} {title} (All Time)
💰 Amount: {format_currency(top['amount'])}
📅 Date: {top['date']}
👤 By: {top['user']}
📝 {top['description']}"""
    
    # Add context if available
    stats = get_all_time_stats()
    if trans_type == 'sale' and stats['sales_count'] > 0:
        avg = stats['avg_sale']
        message += f"\n\n📊 This is {top['amount']/avg:.1f}x larger than average sale ({format_currency(avg)})"
    elif trans_type == 'expense' and stats['expenses_count'] > 0:
        avg = stats['avg_expense']
        message += f"\n\n📊 This is {top['amount']/avg:.1f}x larger than average expense ({format_currency(avg)})"
    
    return message

def get_stats():
    """Get comprehensive business statistics."""
    stats = get_all_time_stats()
    
    message = f"""📈 BUSINESS STATISTICS (All Time)

💰 Financial Overview:
   • Total Sales: {format_currency(stats['total_sales'])}
   • Total Expenses: {format_currency(stats['total_expenses'])}
   • Net Profit: {format_currency(stats['total_profit'])}

📊 Transaction Counts:
   • Sales: {stats['sales_count']} transactions
   • Expenses: {stats['expenses_count']} transactions
   • Total: {stats['sales_count'] + stats['expenses_count']} transactions

📈 Averages:
   • Avg Sale: {format_currency(stats['avg_sale'])}
   • Avg Expense: {format_currency(stats['avg_expense'])}
   • Profit Margin: {(stats['total_profit'] / stats['total_sales'] * 100) if stats['total_sales'] > 0 else 0:.1f}%

💡 Tips:
   • Type 'today' for daily summary
   • Type 'week' for weekly report
   • Type 'top sale' or 'top expense' for records"""
    
    return message

def get_help_message():
    """Returns a comprehensive help message."""
    return """📖 **LEDGER BOT COMMANDS**

**💼 RECORD TRANSACTIONS:**
• `+sale [amount] [description]`
   Example: `+sale 500 Website design`
• `+expense [amount] [description]`
   Example: `+expense 100 Office supplies`
• `+income [amount] [description]`
   Example: `+income 1000 Investment`

**📊 CHECK FINANCES:**
• `balance` - Current profit/loss
• `today` - Today's transactions
• `yesterday` - Yesterday's summary
• `week` - This week's report
• `month` - This month's report
• `stats` - All-time statistics
• `top sale` - Largest sale ever
• `top expense` - Largest expense ever

**🎯 QUICK TIPS:**
• Works in both private chats and groups
• No need to mention bot in groups
• All commands available everywhere
• Automatic daily summaries coming soon!

**📝 EXAMPLES:**
In any chat:
  → `+sale 1500 Project Alpha`
  → `balance`
  → `today`
  → `week`
  → `top expense`

Need help? Just type `help` anytime!"""

# ==================== COMMAND PROCESSOR ====================
def process_command(user_input, user_name="User"):
    """The main function that processes any command from Telegram."""
    text = user_input.strip()
    text_lower = text.lower()

    # Clean the input if it contains bot mention
    if BOT_USERNAME:
        mention_prefix = f"@{BOT_USERNAME}"
        if text_lower.startswith(mention_prefix.lower()):
            text = text[len(mention_prefix):].strip()
            text_lower = text.lower()

    # Remove any leading/trailing punctuation from common phrases
    text_lower = re.sub(r'^[:\s]+|[:\s]+$', '', text_lower)

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

    # Record Income
    elif text_lower.startswith('+income'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +income [amount] [description]\nExample: +income 1000 Investment"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('income', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number.\nExample: +income 1000 Investment"

    # Check Balance
    elif text_lower in ['balance', 'profit', 'net']:
        return get_balance()

    # Today's Summary
    elif text_lower in ['today', 'today?', 'today.']:
        return get_today_summary()

    # Yesterday's Summary
    elif text_lower in ['yesterday', 'yesterday?']:
        return get_yesterday_summary()

    # Week Summary
    elif text_lower in ['week', 'weekly', 'this week']:
        return get_period_summary('week')

    # Month Summary
    elif text_lower in ['month', 'monthly', 'this month']:
        return get_period_summary('month')

    # Stats
    elif text_lower in ['stats', 'statistics', 'overview']:
        return get_stats()

    # Top Sale
    elif text_lower in ['top sale', 'biggest sale', 'largest sale']:
        return get_top_transaction('sale')

    # Top Expense
    elif text_lower in ['top expense', 'biggest expense', 'largest expense']:
        return get_top_transaction('expense')

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
• `week` - Weekly report
• `help` - Show all commands

Type `help` for complete list!"""