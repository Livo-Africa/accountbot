# engine.py - TIER 1 COMPLETE (Cedi, Delete, Categories, Timestamp)
import os
import json
import gspread
import re
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from collections import defaultdict

# ==================== DEBUG ====================
print("🟢 DEBUG: engine.py is starting...")
print(f"🟢 DEBUG: SHEET_ID exists: {bool(os.environ.get('GOOGLE_SHEET_ID'))}")
print(f"🟢 DEBUG: CREDENTIALS exist: {bool(os.environ.get('GOOGLE_CREDENTIALS'))}")

# Add a test connection block
try:
    # Re-use your existing connection function
    from . import get_google_sheets_client  # Adjust import if needed
    test_client = get_google_sheets_client()
    test_spreadsheet = test_client.open_by_key(os.environ.get('GOOGLE_SHEET_ID'))
    print(f"✅ DEBUG: Test connection SUCCESS to: {test_spreadsheet.title}")
except Exception as e:
    print(f"❌ DEBUG: Test connection FAILED with error: {repr(e)}")
# ==================== END DEBUG ====================

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
    
    # One-time: Add category column if needed
    add_category_column_if_needed()
    
except Exception as e:
    print(f"⚠️ Initial connection failed: {e}")
    spreadsheet = None

# ==================== HELPER FUNCTIONS ====================
def format_cedi(amount):
    """Format amount as Ghanaian Cedi."""
    return f"₵{abs(amount):,.2f}"

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
            # Try to find category column (might not exist in old sheets)
            category_idx = headers.index('category') if 'category' in headers else -1
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
                continue
        
        return transactions
    except Exception as e:
        print(f"⚠️ Error reading {sheet_name}: {e}")
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
                    # gspread uses 1-indexed columns
                    worksheet.insert_cols([['category']], desc_index + 2)  # +2 for 1-indexed and after
                    print(f"✅ Added category column to {tab_name}")
                except ValueError:
                    print(f"⚠️ Could not find 'description' column in {tab_name}")
            else:
                print(f"✅ Category column already exists in {tab_name}")
                
        except gspread.exceptions.WorksheetNotFound:
            print(f"⚠️ Tab {tab_name} not found, skipping category column setup")
        except Exception as e:
            print(f"⚠️ Error setting up category column in {tab_name}: {e}")

# ==================== CEDI, DELETE, CATEGORIES ====================

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
        
        # Append to the CORRECT sheet
        target_sheet.append_row(row)
        
        # Build response message
        response = f"✅ Recorded {trans_type} of {format_cedi(amount)}"
        if category:
            response += f" in category: #{category}"
        response += f" to '{sheet_name}' tab."
        
        return response
        
    except Exception as e:
        return f"❌ Failed to save to {sheet_name}: {str(e)}"

def get_last_transaction_by_user(user_name):
    """Find the last transaction added by a specific user."""
    if spreadsheet is None:
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
    
    return None

def delete_last_transaction(user_name):
    """Delete the user's last transaction and move to Deleted tab."""
    if spreadsheet is None:
        return "❌ Bot error: Not connected to the database."
    
    # Find the transaction
    transaction = get_last_transaction_by_user(user_name)
    if not transaction:
        return "❌ No recent transactions found to delete."
    
    try:
        # 1. Move to DeletedTransactions tab
        deleted_sheet_name = "DeletedTransactions"
        
        # Create DeletedTransactions tab if it doesn't exist
        try:
            deleted_sheet = spreadsheet.worksheet(deleted_sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # Create the tab
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
            print(f"✅ Created {deleted_sheet_name} tab")
        
        # Record to deleted tab
        deleted_timestamp = datetime.now().strftime('%Y-%m-%d %I:%M %p')
        deleted_sheet.append_row([
            transaction['date'],
            transaction['type'],
            transaction['amount'],
            transaction['description'],
            transaction['user'],
            datetime.now().strftime('%Y-%m-%d %I:%M %p'),  # Original timestamp (approximate)
            deleted_timestamp,
            f"Deleted by {user_name} via /delete command"
        ])
        
        # 2. Delete from original sheet
        original_sheet = spreadsheet.worksheet(transaction['sheet_name'])
        original_sheet.delete_rows(transaction['row_index'])
        
        # Format the amount nicely
        try:
            amount = float(transaction['amount'])
            amount_str = format_cedi(amount)
        except:
            amount_str = transaction['amount']
        
        return f"✅ Deleted {transaction['type']} of {amount_str} from {transaction['sheet_name']} tab."
        
    except Exception as e:
        return f"❌ Failed to delete transaction: {str(e)}"

def get_categories_report():
    """Generate a report of all categories and their totals."""
    if spreadsheet is None:
        return "❌ Bot error: Not connected to the database."
    
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
                # Try to find category column (might not exist in old sheets)
                if 'category' in headers:
                    category_idx = headers.index('category')
                else:
                    continue  # Skip if no category column
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
        return "📭 No categorized transactions found.\n\n💡 **Tip**: Add #hashtag to your descriptions:\nExample: +expense 500 #marketing Facebook ads"
    
    # Sort categories by total amount (descending)
    sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    
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
    
    return report

# ==================== EXISTING CORE FUNCTIONS (UPDATED WITH CEDI) ====================

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

    return f"💰 Current Balance: {format_cedi(balance)}"

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
{emoji} Net: {format_cedi(net)}

💰 Sales: {format_cedi(total_sales)} ({len(sales)} transaction{'s' if len(sales) != 1 else ''})"""
    
    if top_sale:
        message += f"\n   👑 Top Sale: {format_cedi(top_sale['amount'])} by {top_sale['user']}"
        message += f"\n      \"{top_sale['description'][:40]}{'...' if len(top_sale['description']) > 40 else ''}\""
    
    message += f"\n💸 Expenses: {format_cedi(total_expenses)} ({len(expenses)} transaction{'s' if len(expenses) != 1 else ''})"
    
    if top_expense:
        message += f"\n   💸 Top Expense: {format_cedi(top_expense['amount'])} by {top_expense['user']}"
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
{emoji} Net: {format_cedi(net)}

💰 Sales: {format_cedi(total_sales)} ({len(sales)} transactions)
💸 Expenses: {format_cedi(total_expenses)} ({len(expenses)} transactions)"""
    
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
{emoji} Total Profit: {format_cedi(net)}

💰 Total Sales: {format_cedi(total_sales)} ({len(sales)} transactions)
💸 Total Expenses: {format_cedi(total_expenses)} ({len(expenses)} transactions)

📆 Daily Average: {format_cedi(avg_daily_profit)}"""
    
    if best_day[0]:
        message += f"\n🏆 Best Day: {best_day[0]} ({format_cedi(best_day[1])} in sales)"
    
    if worst_day[0]:
        message += f"\n💸 Heaviest Spending Day: {worst_day[0]} ({format_cedi(worst_day[1])} in expenses)"
    
    # Add top transactions
    if sales:
        top_sale = max(sales, key=lambda x: x['amount'])
        message += f"\n\n👑 Top Sale: {format_cedi(top_sale['amount'])}"
        message += f"\n   By: {top_sale['user']} | {top_sale['description'][:40]}"
    
    if expenses:
        top_expense = max(expenses, key=lambda x: x['amount'])
        message += f"\n💸 Top Expense: {format_cedi(top_expense['amount'])}"
        message += f"\n   By: {top_expense['user']} | {top_expense['description'][:40]}"
    
    return message

def get_stats():
    """Get comprehensive business statistics."""
    sales = get_transactions('Sales')
    expenses = get_transactions('Expenses')
    
    total_sales = sum(t['amount'] for t in sales)
    total_expenses = sum(t['amount'] for t in expenses)
    total_profit = total_sales - total_expenses
    
    avg_sale = total_sales / len(sales) if sales else 0
    avg_expense = total_expenses / len(expenses) if expenses else 0
    
    # Simple health score calculation (0-100)
    profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0
    expense_ratio = (total_expenses / total_sales * 100) if total_sales > 0 else 100
    
    # Calculate health score
    cash_flow_score = 40 if total_profit > 0 else 20 if total_profit == 0 else 0
    expense_score = 30 * max(0, 1 - min(expense_ratio/100, 1))
    consistency_score = 20 if len(sales + expenses) >= 10 else 10
    growth_score = 10  # Simplified for now
    
    health_score = min(100, cash_flow_score + expense_score + consistency_score + growth_score)
    health_emoji = "🟢" if health_score >= 70 else "🟡" if health_score >= 40 else "🔴"
    
    message = f"""📈 **BUSINESS STATISTICS** (All Time)

{health_emoji} **Health Score:** {health_score:.0f}/100

💰 **Financial Overview:**
   • Total Sales: {format_cedi(total_sales)}
   • Total Expenses: {format_cedi(total_expenses)}
   • Net Profit: {format_cedi(total_profit)}
   • Profit Margin: {profit_margin:.1f}%

📊 **Transaction Counts:**
   • Sales: {len(sales)} transactions
   • Expenses: {len(expenses)} transactions
   • Total: {len(sales) + len(expenses)} transactions

📈 **Averages:**
   • Avg Sale: {format_cedi(avg_sale)}
   • Avg Expense: {format_cedi(avg_expense)}
   • Avg Daily Profit: {format_cedi(total_profit / 30 if total_profit else 0)} (estimated)

💡 **Tips:**
   • Type 'today' for daily summary
   • Type 'categories' for category breakdown
   • Type 'delete' to remove last transaction"""
    
    return message

def get_help_message():
    """Returns a comprehensive help message."""
    return """📖 **LEDGER BOT COMMANDS**

**💼 RECORD TRANSACTIONS:**
• `+sale [amount] [description]`
   Example: `+sale 500 Website design #web`
• `+expense [amount] [description]`
   Example: `+expense 100 Office supplies #office`
• `+income [amount] [description]`
   Example: `+income 1000 Investment #investment`

**📊 CHECK FINANCES:**
• `balance` - Current profit/loss
• `today` - Today's transactions
• `yesterday` - Yesterday's summary
• `week` - This week's report
• `month` - This month's report
• `stats` - All-time statistics
• `top sale` - Largest sale ever
• `top expense` - Largest expense ever

**🗂️  CATEGORIES:**
• Add `#hashtag` to any description to categorize
• `categories` - Show all categories and totals
• Example: `+expense 500 #marketing Facebook ads`

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
    """The main function that processes any command from Telegram."""
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

    # Categories Report
    elif text_lower in ['categories', 'category', '/categories']:
        return get_categories_report()

    # Stats
    elif text_lower in ['stats', 'statistics', 'overview']:
        return get_stats()

    # Delete Last Transaction
    elif text_lower in ['delete', 'delete last', '/delete']:
        return delete_last_transaction(user_name)

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
• `help` - Show all commands

Type `help` for complete list!"""