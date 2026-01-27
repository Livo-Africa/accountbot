# engine.py - COMPLETE FIXED VERSION WITH PROPER HELP SYSTEM
import os
import json
import gspread
import re
import secrets
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

# ==================== HELPER FUNCTIONS ====================
def generate_transaction_id(trans_type):
    """Generate unique transaction ID: TYPE-ABC123"""
    prefix = trans_type[:3].upper()
    random_part = secrets.token_hex(3).upper()  # 6 random hex chars
    return f"{prefix}-{random_part}"

def format_cedi(amount):
    """Format amount as Ghanaian Cedi with proper negative handling."""
    try:
        amount_float = float(amount)
        if amount_float < 0:
            return f"-₵{abs(amount_float):,.2f}"
        return f"₵{amount_float:,.2f}"
    except (ValueError, TypeError):
        return f"₵{amount}"

def find_column_index(headers, column_name):
    """Find column index safely."""
    if not headers:
        return -1
    headers_lower = [h.lower().strip() for h in headers]
    column_lower = column_name.lower().strip()
    try:
        return headers_lower.index(column_lower)
    except ValueError:
        return -1

# ==================== PRICE TRAINING SYSTEM ====================
def ensure_price_ranges_sheet():
    """Ensure PriceRanges sheet exists with proper structure."""
    if not spreadsheet:
        return False
    
    price_columns = ['Item', 'Type', 'Min_Price', 'Max_Price', 'Unit', 
                    'Confidence', 'Trained_By', 'Last_Trained', 'Notes']
    
    try:
        worksheet = spreadsheet.worksheet('PriceRanges')
        current_headers = worksheet.row_values(1)
        
        # Check if all columns exist
        if len(current_headers) < len(price_columns):
            # Add missing columns
            for i, col in enumerate(price_columns):
                if i >= len(current_headers):
                    worksheet.update_cell(1, i+1, col)
        return True
        
    except gspread.exceptions.WorksheetNotFound:
        # Create new sheet
        worksheet = spreadsheet.add_worksheet(
            title='PriceRanges',
            rows=1000,
            cols=len(price_columns)
        )
        worksheet.append_row(price_columns)
        return True
    except Exception:
        return False

def train_price(item_name, min_price, max_price, unit="", user_name="User"):
    """Train the bot on price ranges for items/categories."""
    if not ensure_price_ranges_sheet():
        return "❌ Cannot access PriceRanges sheet."
    
    try:
        worksheet = spreadsheet.worksheet('PriceRanges')
        all_rows = worksheet.get_all_values()
        
        # Check if item already exists
        item_lower = item_name.strip().lower()
        row_index = None
        
        for i, row in enumerate(all_rows[1:], start=2):
            if row and len(row) > 0 and row[0].strip().lower() == item_lower:
                row_index = i
                break
        
        # Determine type (item or category)
        item_type = "category" if item_name.startswith("#") else "item"
        
        # Prepare training data
        training_data = [
            item_name.strip(),
            item_type,
            float(min_price),
            float(max_price),
            unit.strip(),
            85,  # Initial confidence
            user_name,
            datetime.now().strftime('%Y-%m-%d'),
            f"Trained by {user_name}"
        ]
        
        if row_index:
            # Update existing row
            for col, value in enumerate(training_data, start=1):
                worksheet.update_cell(row_index, col, value)
            action = "updated"
        else:
            # Add new row
            worksheet.append_row(training_data)
            action = "added"
        
        return f"✅ {action.capitalize()} price range for '{item_name}': ₵{min_price:,.2f} - ₵{max_price:,.2f}" + \
               (f" {unit}" if unit else "")
        
    except Exception as e:
        return f"❌ Training failed: {str(e)}"

def forget_price(item_name):
    """Remove price training for an item."""
    try:
        worksheet = spreadsheet.worksheet('PriceRanges')
        all_rows = worksheet.get_all_values()
        
        item_lower = item_name.strip().lower()
        rows_to_delete = []
        
        for i, row in enumerate(all_rows[1:], start=2):
            if row and len(row) > 0 and row[0].strip().lower() == item_lower:
                rows_to_delete.append(i)
        
        if not rows_to_delete:
            return f"❌ No price training found for '{item_name}'"
        
        # Delete from bottom to maintain indices
        for row in sorted(rows_to_delete, reverse=True):
            worksheet.delete_rows(row)
        
        return f"✅ Forgot price training for '{item_name}'"
        
    except gspread.exceptions.WorksheetNotFound:
        return f"❌ No price training found for '{item_name}'"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def check_price(item_name, amount):
    """Check if amount is within trained price range."""
    try:
        worksheet = spreadsheet.worksheet('PriceRanges')
        all_rows = worksheet.get_all_values()
        
        item_lower = item_name.strip().lower()
        matches = []
        
        # Search for exact matches
        for row in all_rows[1:]:
            if row and len(row) > 0 and row[0].strip().lower() == item_lower:
                try:
                    min_price = float(row[2]) if len(row) > 2 and row[2] else 0
                    max_price = float(row[3]) if len(row) > 3 and row[3] else float('inf')
                    unit = row[4] if len(row) > 4 else ""
                    confidence = int(row[5]) if len(row) > 5 and row[5] else 50
                    
                    matches.append({
                        'item': row[0],
                        'min': min_price,
                        'max': max_price,
                        'unit': unit,
                        'confidence': confidence
                    })
                except (ValueError, IndexError):
                    continue
        
        if not matches:
            return None
        
        # Return the best match (highest confidence)
        best_match = max(matches, key=lambda x: x['confidence'])
        
        try:
            amount_float = float(amount)
        except ValueError:
            return None
        
        if amount_float < best_match['min']:
            return {
                'status': 'below',
                'range': best_match,
                'difference': best_match['min'] - amount_float
            }
        elif amount_float > best_match['max']:
            return {
                'status': 'above',
                'range': best_match,
                'difference': amount_float - best_match['max']
            }
        else:
            return {
                'status': 'within',
                'range': best_match
            }
        
    except Exception:
        return None

def list_trained_items():
    """List all trained price ranges."""
    try:
        worksheet = spreadsheet.worksheet('PriceRanges')
        all_rows = worksheet.get_all_values()
        
        if len(all_rows) <= 1:
            return "📭 No items have been trained yet. Use `+train` to add price ranges."
        
        items = []
        for row in all_rows[1:]:
            if row and row[0]:
                try:
                    items.append({
                        'name': row[0],
                        'min': float(row[2]) if len(row) > 2 and row[2] else 0,
                        'max': float(row[3]) if len(row) > 3 and row[3] else 0,
                        'unit': row[4] if len(row) > 4 else "",
                        'confidence': int(row[5]) if len(row) > 5 and row[5] else 50,
                        'trained_by': row[6] if len(row) > 6 else "Unknown",
                        'last_trained': row[7] if len(row) > 7 else "Unknown"
                    })
                except (ValueError, IndexError):
                    continue
        
        if not items:
            return "📭 No valid price training found."
        
        # Sort by confidence (highest first)
        items.sort(key=lambda x: x['confidence'], reverse=True)
        
        response = "📚 **TRAINED PRICE RANGES:**\n\n"
        
        for i, item in enumerate(items[:15], 1):  # Show top 15
            emoji = "✅" if item['confidence'] > 80 else "⚠️" if item['confidence'] > 60 else "🤔"
            response += f"{emoji} **{item['name']}**: ₵{item['min']:,.2f} - ₵{item['max']:,.2f}"
            if item['unit']:
                response += f" {item['unit']}"
            response += f"\n   Confidence: {item['confidence']}% | Trained by: {item['trained_by']}\n\n"
        
        if len(items) > 15:
            response += f"📋 Showing 15 of {len(items)} items. Use `price_check [item]` for details."
        
        return response
        
    except gspread.exceptions.WorksheetNotFound:
        return "📭 No price training data found. Use `+train` to start training."
    except Exception:
        return "❌ Cannot access PriceRanges sheet."

def auto_detect_items_in_description(description):
    """Automatically detect trained items in a description."""
    try:
        worksheet = spreadsheet.worksheet('PriceRanges')
        all_rows = worksheet.get_all_values()
        
        detected = []
        description_lower = description.lower()
        
        for row in all_rows[1:]:
            if row and row[0]:
                item_lower = row[0].lower()
                # Simple word matching (could be improved)
                if item_lower in description_lower or f" {item_lower} " in f" {description_lower} ":
                    try:
                        detected.append({
                            'item': row[0],
                            'min': float(row[2]) if len(row) > 2 and row[2] else 0,
                            'max': float(row[3]) if len(row) > 3 and row[3] else 0,
                            'unit': row[4] if len(row) > 4 else ""
                        })
                    except (ValueError, IndexError):
                        continue
        
        return detected
    except Exception:
        return []

# ==================== FIXED TRAIN COMMAND PARSER ====================
def parse_train_command(text):
    """Parse +train command with proper handling of quotes and units."""
    # Remove the +train prefix
    text = text.strip()
    if text.lower().startswith('+train'):
        text = text[6:].strip()
    
    # Handle quoted item names
    item_name = None
    remaining = text
    
    # Check if text starts with a quote
    if text.startswith('"'):
        # Find the closing quote
        end_quote = text.find('"', 1)
        if end_quote != -1:
            item_name = text[1:end_quote]
            remaining = text[end_quote+1:].strip()
    elif text.startswith("'"):
        # Find the closing single quote
        end_quote = text.find("'", 1)
        if end_quote != -1:
            item_name = text[1:end_quote]
            remaining = text[end_quote+1:].strip()
    else:
        # No quotes, take first word as item name
        parts = text.split()
        if len(parts) >= 3:  # Need at least item name and two numbers
            item_name = parts[0]
            remaining = ' '.join(parts[1:])
    
    if not item_name:
        return None, None, None, "❌ Could not parse item name. Use quotes for multi-word items."
    
    # Parse numbers from remaining text
    parts = remaining.split()
    
    # Find the first two numbers
    numbers = []
    unit_parts = []
    
    for part in parts:
        # Try to parse as float
        try:
            num = float(part)
            if len(numbers) < 2:
                numbers.append(num)
            else:
                unit_parts.append(part)
        except ValueError:
            unit_parts.append(part)
    
    if len(numbers) < 2:
        return None, None, None, "❌ Please provide both minimum and maximum prices."
    
    min_price = numbers[0]
    max_price = numbers[1]
    unit = ' '.join(unit_parts) if unit_parts else ""
    
    return item_name, min_price, max_price, unit

# ==================== CONNECTION & SHEET MANAGEMENT ====================
def get_google_sheets_client():
    """Connects to Google Sheets."""
    credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not credentials_json:
        return None
    
    try:
        credentials_info = json.loads(credentials_json)
        creds = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception:
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
        
        # Ensure all sheets have proper structure
        ensure_sheet_structures()
        
        # Initialize price ranges sheet
        ensure_price_ranges_sheet()
        
    except Exception as e:
        print(f"Connection failed: {e}")
        spreadsheet = None

def ensure_sheet_structures():
    """Ensure all sheets have ID column and proper structure."""
    if not spreadsheet:
        return
    
    # Define standard column order
    transaction_columns = ['ID', 'Date', 'Type', 'Amount', 'Description', 'Category', 'User', 'Timestamp']
    deleted_columns = ['ID', 'Date', 'Type', 'Amount', 'Description', 'Category', 'User', 'Original_Sheet', 'Deleted_Timestamp', 'Reason']
    
    # Update transaction sheets
    for sheet_name in ['Sales', 'Expenses', 'Income']:
        ensure_sheet_structure(sheet_name, transaction_columns)
    
    # Update DeletedTransactions sheet
    ensure_sheet_structure('DeletedTransactions', deleted_columns, create_if_missing=True)

def ensure_sheet_structure(sheet_name, expected_columns, create_if_missing=False):
    """Ensure a sheet has the expected column structure."""
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        if create_if_missing:
            # Create the sheet with expected columns
            worksheet = spreadsheet.add_worksheet(
                title=sheet_name,
                rows=1000,
                cols=len(expected_columns)
            )
            worksheet.append_row(expected_columns)
            print(f"Created {sheet_name} sheet with proper structure")
            return True
        else:
            return False
    
    # Get current headers
    current_headers = worksheet.row_values(1)
    current_headers_lower = [h.strip().lower() for h in current_headers]
    
    # Check if we need to add missing columns
    needs_update = False
    for i, expected_col in enumerate(expected_columns):
        expected_col_lower = expected_col.lower()
        if expected_col_lower not in current_headers_lower:
            # Insert missing column
            worksheet.insert_cols([[expected_col]], i + 1)
            print(f"Added {expected_col} column to {sheet_name}")
            needs_update = True
    
    return needs_update

# Initialize connection
initialize_spreadsheet_connection()

# ==================== TRANSACTION FUNCTIONS ====================
def record_transaction(trans_type, amount, description="", user_name="User"):
    """Record a transaction with unique ID and price checking."""
    if not spreadsheet:
        return "❌ Bot error: Not connected to database."
    
    sheet_name = TYPE_TO_SHEET.get(trans_type.lower())
    if not sheet_name:
        return f"❌ Unknown transaction type: '{trans_type}'."
    
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        
        # Generate unique ID
        transaction_id = generate_transaction_id(trans_type)
        
        # Extract category from description
        category = ""
        clean_description = description
        
        hashtags = re.findall(r'#(\w+)', description)
        if hashtags:
            category = hashtags[0]
            clean_description = re.sub(r'#\w+', '', description).strip()
            clean_description = re.sub(r'\s+', ' ', clean_description)
        
        # Check for price warnings
        price_warnings = []
        
        # 1. Check if the exact item is trained
        detected_items = auto_detect_items_in_description(clean_description)
        
        for item in detected_items:
            price_check = check_price(item['item'], amount)
            if price_check and price_check['status'] != 'within':
                if price_check['status'] == 'above':
                    price_warnings.append(f"⚠️ **{item['item']}** is usually ₵{item['min']:,.2f}-₵{item['max']:,.2f} (your price: ₵{float(amount):,.2f})")
                elif price_check['status'] == 'below':
                    price_warnings.append(f"⚠️ **{item['item']}** is usually ₵{item['min']:,.2f}-₵{item['max']:,.2f} (your price: ₵{float(amount):,.2f} seems low)")
        
        # 2. Check category if present
        if category:
            price_check = check_price(f"#{category}", amount)
            if price_check and price_check['status'] != 'within':
                if price_check['status'] == 'above':
                    price_warnings.append(f"⚠️ **#{category}** expenses are usually ₵{price_check['range']['min']:,.2f}-₵{price_check['range']['max']:,.2f}")
        
        # Prepare row with ID
        row = [
            transaction_id,                           # ID
            datetime.now().strftime('%Y-%m-%d'),     # Date
            trans_type.lower(),                      # Type
            float(amount),                           # Amount
            clean_description,                       # Description
            category,                                # Category
            user_name,                               # User
            datetime.now().strftime('%I:%M %p')      # Timestamp
        ]
        
        worksheet.append_row(row)
        
        response = f"✅ Recorded {trans_type} of {format_cedi(float(amount))}"
        if category:
            response += f" in category: #{category}"
        response += f"\n📝 **ID:** `{transaction_id}`"
        
        # Add price warnings if any
        if price_warnings:
            response += "\n\n" + "\n".join(price_warnings)
            response += "\n\n💡 If this is correct, the bot will learn from it!"
        
        return response
        
    except Exception as e:
        return f"❌ Failed to save: {str(e)[:100]}"

def get_transactions(sheet_name, start_date=None, end_date=None, user_filter=None):
    """Get transactions from a sheet with optional filtering."""
    if not spreadsheet:
        return []
    
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        all_rows = worksheet.get_all_values()
        
        if len(all_rows) <= 1:
            return []
        
        headers = [h.strip().lower() for h in all_rows[0]]
        
        # Find column indices
        id_idx = find_column_index(headers, 'id')
        date_idx = find_column_index(headers, 'date')
        amount_idx = find_column_index(headers, 'amount')
        desc_idx = find_column_index(headers, 'description')
        user_idx = find_column_index(headers, 'user')
        category_idx = find_column_index(headers, 'category')
        type_idx = find_column_index(headers, 'type')
        
        # Essential columns must exist
        if -1 in [date_idx, amount_idx, desc_idx, user_idx]:
            return []
        
        transactions = []
        
        for row in all_rows[1:]:
            if len(row) <= max(date_idx, amount_idx, desc_idx, user_idx):
                continue
            
            # Parse row data
            date_str = row[date_idx].strip()
            amount_str = row[amount_idx].strip()
            description = row[desc_idx] if desc_idx < len(row) else ''
            user = row[user_idx] if user_idx < len(row) else ''
            category = row[category_idx] if category_idx != -1 and category_idx < len(row) else ''
            trans_id = row[id_idx] if id_idx != -1 and id_idx < len(row) else ''
            
            # Determine transaction type
            if type_idx != -1 and type_idx < len(row):
                trans_type = row[type_idx].strip().lower()
            else:
                # Infer from sheet name
                trans_type = 'sale' if sheet_name.lower() == 'sales' else 'expense'
            
            # Apply filters
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            if user_filter and user != user_filter:
                continue
            
            try:
                amount = float(amount_str) if amount_str else 0.0
                transactions.append({
                    'id': trans_id,
                    'date': date_str,
                    'type': trans_type,
                    'amount': amount,
                    'description': description,
                    'user': user,
                    'category': category,
                    'sheet': sheet_name
                })
            except ValueError:
                continue
        
        return transactions
        
    except Exception:
        return []

def get_balance():
    """Calculate current balance with proper negative handling."""
    if not spreadsheet:
        return "❌ Bot error: Not connected to database."
    
    balance = 0.0
    transaction_count = 0
    
    # Check all transaction sheets
    for sheet_name in ['Sales', 'Expenses', 'Income']:
        transactions = get_transactions(sheet_name)
        
        for trans in transactions:
            if trans['type'] in ['sale', 'income']:
                balance += trans['amount']
            elif trans['type'] == 'expense':
                balance -= trans['amount']
            
            transaction_count += 1
    
    # Format with proper negative sign
    if balance < 0:
        return f"💰 Current Balance: -₵{abs(balance):,.2f} ({transaction_count} transactions)"
    elif balance == 0:
        return f"💰 Current Balance: ₵0.00 ({transaction_count} transactions)"
    else:
        return f"💰 Current Balance: +₵{balance:,.2f} ({transaction_count} transactions)"

# ==================== SMART DELETION SYSTEM ====================
def list_user_transactions(user_name, limit=10):
    """List user's recent transactions with IDs."""
    all_transactions = []
    
    # Get transactions from all sheets
    for sheet_name in ['Sales', 'Expenses', 'Income']:
        transactions = get_transactions(sheet_name, user_filter=user_name)
        all_transactions.extend(transactions)
    
    if not all_transactions:
        return "📭 No transactions found."
    
    # Sort by date (newest first)
    all_transactions.sort(key=lambda x: x['date'], reverse=True)
    all_transactions = all_transactions[:limit]
    
    response = "📋 **YOUR RECENT TRANSACTIONS:**\n\n"
    
    for i, trans in enumerate(all_transactions, 1):
        emoji = "💰" if trans['type'] in ['sale', 'income'] else "💸"
        
        response += f"{i}. {emoji} `{trans['id'] if trans['id'] else 'NO-ID'}`\n"
        response += f"   {format_cedi(trans['amount'])} - {trans['description'][:40]}\n"
        response += f"   📅 {trans['date']} | {trans['type'].upper()}"
        if trans['category']:
            response += f" | #{trans['category']}"
        response += "\n\n"
    
    if any(trans['id'] for trans in all_transactions):
        response += "💡 **Delete with:** `/delete ID:YOUR-ID-HERE`"
    else:
        response += "⚠️ **Note:** Older transactions don't have IDs. Use `/delete last`"
    
    return response

def find_transaction_by_id(transaction_id, user_name):
    """Find a specific transaction by ID."""
    if not transaction_id:
        return None
    
    # Determine sheet from ID prefix
    id_prefix = transaction_id.split('-')[0].upper()
    sheet_map = {
        'SAL': 'Sales',
        'EXP': 'Expenses',
        'INC': 'Income'
    }
    
    sheet_name = sheet_map.get(id_prefix)
    if not sheet_name:
        # Search all sheets
        sheet_names = ['Sales', 'Expenses', 'Income']
    else:
        sheet_names = [sheet_name]
    
    for sheet in sheet_names:
        transactions = get_transactions(sheet, user_filter=user_name)
        for trans in transactions:
            if trans['id'] == transaction_id:
                return trans
    
    return None

def delete_transaction_by_id(transaction_id, user_name):
    """Delete a transaction by its ID."""
    if not spreadsheet:
        return "❌ Bot error: Not connected to database."
    
    # Find the transaction
    transaction = find_transaction_by_id(transaction_id, user_name)
    if not transaction:
        return "❌ Transaction not found or you don't have permission to delete it."
    
    try:
        # Get the original worksheet
        original_sheet = spreadsheet.worksheet(transaction['sheet'])
        all_rows = original_sheet.get_all_values()
        
        if len(all_rows) <= 1:
            return "❌ Transaction not found."
        
        headers = [h.strip().lower() for h in all_rows[0]]
        id_idx = find_column_index(headers, 'id')
        
        if id_idx == -1:
            return "❌ This sheet doesn't have ID column yet."
        
        # Find the row index
        row_index = None
        for i, row in enumerate(all_rows[1:], start=2):
            if len(row) > id_idx and row[id_idx].strip() == transaction_id:
                row_index = i
                break
        
        if not row_index:
            return "❌ Transaction not found in sheet."
        
        # Archive to DeletedTransactions
        archive_deleted_transaction(transaction, user_name)
        
        # Delete from original sheet
        original_sheet.delete_rows(row_index)
        
        return f"✅ Deleted transaction `{transaction_id}` ({format_cedi(transaction['amount'])})"
        
    except Exception as e:
        return f"❌ Failed to delete: {str(e)[:100]}"

def archive_deleted_transaction(transaction, deleted_by):
    """Move transaction to DeletedTransactions tab."""
    try:
        # Get or create DeletedTransactions sheet
        try:
            deleted_sheet = spreadsheet.worksheet('DeletedTransactions')
        except gspread.exceptions.WorksheetNotFound:
            deleted_sheet = spreadsheet.add_worksheet(
                title='DeletedTransactions',
                rows=10000,
                cols=10
            )
            deleted_sheet.append_row([
                'ID', 'Date', 'Type', 'Amount', 'Description', 
                'Category', 'User', 'Original_Sheet', 'Deleted_Timestamp', 'Reason'
            ])
        
        # Prepare deleted record
        deleted_row = [
            transaction['id'],                            # ID
            transaction['date'],                          # Date
            transaction['type'],                          # Type
            transaction['amount'],                        # Amount
            transaction['description'],                   # Description
            transaction['category'],                      # Category
            transaction['user'],                          # User
            transaction['sheet'],                         # Original_Sheet
            datetime.now().strftime('%Y-%m-%d %I:%M %p'), # Deleted_Timestamp
            f"Deleted by {deleted_by} via ID"             # Reason
        ]
        
        deleted_sheet.append_row(deleted_row)
        
    except Exception:
        pass  # Archive is optional

def delete_last_transaction(user_name):
    """Delete user's most recent transaction."""
    # Get user's recent transactions
    recent = []
    for sheet in ['Sales', 'Expenses', 'Income']:
        recent.extend(get_transactions(sheet, user_filter=user_name))
    
    if not recent:
        return "❌ No recent transactions found."
    
    # Sort by date (newest first)
    recent.sort(key=lambda x: x['date'], reverse=True)
    last_transaction = recent[0]
    
    if not last_transaction['id']:
        # Old transaction without ID - use old deletion method
        return delete_old_transaction(last_transaction, user_name)
    
    # Delete by ID
    return delete_transaction_by_id(last_transaction['id'], user_name)

def delete_old_transaction(transaction, user_name):
    """Delete old transaction without ID (backward compatibility)."""
    try:
        original_sheet = spreadsheet.worksheet(transaction['sheet'])
        all_rows = original_sheet.get_all_values()
        
        if len(all_rows) <= 1:
            return "❌ Transaction not found."
        
        headers = [h.strip().lower() for h in all_rows[0]]
        date_idx = find_column_index(headers, 'date')
        amount_idx = find_column_index(headers, 'amount')
        user_idx = find_column_index(headers, 'user')
        
        # Find the row by matching multiple fields
        for i, row in enumerate(all_rows[1:], start=2):
            if (len(row) > max(date_idx, amount_idx, user_idx) and
                row[date_idx].strip() == transaction['date'] and
                row[user_idx].strip() == user_name and
                abs(float(row[amount_idx]) - transaction['amount']) < 0.01):
                
                # Archive
                archive_deleted_transaction(transaction, user_name)
                
                # Delete
                original_sheet.delete_rows(i)
                
                return f"✅ Deleted old transaction ({format_cedi(transaction['amount'])})"
        
        return "❌ Could not find matching transaction."
        
    except Exception as e:
        return f"❌ Failed to delete old transaction: {str(e)[:100]}"

# ==================== REPORT FUNCTIONS ====================
def get_today_summary():
    """Get today's sales and expenses summary."""
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # Get all transactions from today
    all_today = []
    for sheet in ['Sales', 'Expenses', 'Income']:
        all_today.extend(get_transactions(sheet, start_date=today_str, end_date=today_str))
    
    if not all_today:
        return f"📊 TODAY'S SUMMARY ({today_str})\n\n📭 No transactions today yet."
    
    # Separate by type
    income = [t for t in all_today if t['type'] in ['sale', 'income']]
    expenses = [t for t in all_today if t['type'] == 'expense']
    
    total_income = sum(t['amount'] for t in income)
    total_expenses = sum(t['amount'] for t in expenses)
    net = total_income - total_expenses
    
    emoji = "📈" if net > 0 else "📉" if net < 0 else "➖"
    
    message = f"""📊 TODAY'S SUMMARY ({today_str})
{emoji} Net: {format_cedi(net)}

💰 Income/Sales: {format_cedi(total_income)} ({len(income)} transactions)
💸 Expenses: {format_cedi(total_expenses)} ({len(expenses)} transactions)"""
    
    if income:
        top_income = max(income, key=lambda x: x['amount'])
        message += f"\n\n👑 Top Income: {format_cedi(top_income['amount'])}"
    
    if expenses:
        top_expense = max(expenses, key=lambda x: x['amount'])
        message += f"\n💸 Top Expense: {format_cedi(top_expense['amount'])}"
    
    return message

def get_categories_report():
    """Generate categories report."""
    if not spreadsheet:
        return "❌ Bot error: Not connected to database."
    
    category_totals = defaultdict(float)
    category_counts = defaultdict(int)
    
    # Check all transaction sheets
    for sheet_name in ['Sales', 'Expenses', 'Income']:
        transactions = get_transactions(sheet_name)
        
        for trans in transactions:
            category = trans['category'] if trans['category'] else "Uncategorized"
            category_totals[category] += trans['amount']
            category_counts[category] += 1
    
    if not category_totals:
        return "📭 No categorized transactions found.\n\n💡 **Tip:** Add #hashtag to descriptions:\nExample: +expense 500 #marketing Facebook ads"
    
    # Sort by total amount
    sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
    
    report = "📊 **CATEGORIES REPORT**\n\n"
    
    for category, total in sorted_categories:
        count = category_counts[category]
        report += f"**#{category}**: {format_cedi(total)} ({count} transactions)\n"
    
    # Add summary
    total_transactions = sum(category_counts.values())
    total_amount = sum(category_totals.values())
    
    report += f"\n📈 **Summary:**\n"
    report += f"• Total Categories: {len(category_totals)}\n"
    report += f"• Total Transactions: {total_transactions}\n"
    report += f"• Total Amount: {format_cedi(total_amount)}\n"
    
    if len(sorted_categories) >= 3:
        report += f"\n🏆 **Top 3 Categories:**\n"
        for i, (category, total) in enumerate(sorted_categories[:3], 1):
            emoji = "👑" if i == 1 else "🥈" if i == 2 else "🥉"
            report += f"{emoji} #{category}: {format_cedi(total)}\n"
    
    report += "\n💡 Add #hashtag to any transaction to categorize it!"
    
    return report

def get_period_summary(period):
    """Get summary for week or month."""
    start_date, end_date = get_date_range(period)
    period_name = period.upper()
    
    # Get all transactions in period
    all_period = []
    for sheet in ['Sales', 'Expenses', 'Income']:
        all_period.extend(get_transactions(sheet, start_date=start_date, end_date=end_date))
    
    if not all_period:
        return f"📅 {period_name}LY REPORT ({start_date} to {end_date})\n\n📭 No transactions in this period."
    
    income = [t for t in all_period if t['type'] in ['sale', 'income']]
    expenses = [t for t in all_period if t['type'] == 'expense']
    
    total_income = sum(t['amount'] for t in income)
    total_expenses = sum(t['amount'] for t in expenses)
    net = total_income - total_expenses
    
    emoji = "📈" if net > 0 else "📉" if net < 0 else "➖"
    
    message = f"""📅 {period_name}LY REPORT ({start_date} to {end_date})
{emoji} Total Profit: {format_cedi(net)}

💰 Total Income: {format_cedi(total_income)} ({len(income)} transactions)
💸 Total Expenses: {format_cedi(total_expenses)} ({len(expenses)} transactions)"""
    
    if income:
        avg_income = total_income / len(income)
        message += f"\n📊 Avg Income: {format_cedi(avg_income)}"
    
    if expenses:
        avg_expense = total_expenses / len(expenses)
        message += f"\n📊 Avg Expense: {format_cedi(avg_expense)}"
    
    return message

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
    
    return None, None

def get_status():
    """Get bot status information."""
    return {
        'status': 'connected' if spreadsheet else 'disconnected',
        'price_training': 'enabled'
    }

# ==================== COMPREHENSIVE HELP & TUTORIAL SYSTEM ====================
def get_tutorial_message():
    """Returns step-by-step tutorial for new users."""
    return """🎓 **LEDGER BOT TUTORIAL - GET STARTED IN 5 MINUTES**

**STEP 1: RECORD YOUR FIRST TRANSACTION**
Try this:
`+expense 150 Lunch with client #meeting`

You'll see:
✅ Recorded expense of ₵150.00 in category: #meeting
📝 **ID:** EXP-ABC123

**STEP 2: RECORD A SALE**
`+sale 500 Website design #freelance`

**STEP 3: CHECK YOUR BALANCE**
`balance`
→ Shows your current profit/loss

**STEP 4: SEE TODAY'S SUMMARY**
`today`
→ Shows income vs expenses for today

**STEP 5: TRAIN PRICE RANGES (Optional but useful)**
`+train "printer paper" 60 80 per ream`
Now if you record: `+expense 200 printer paper`
→ Bot warns: "⚠️ printer paper is usually ₵60-₵80"

**STEP 6: LIST YOUR TRANSACTIONS**
`list`
→ Shows recent transactions with IDs

**STEP 7: DELETE IF NEEDED**
`/delete ID:EXP-ABC123`
→ Deletes that specific transaction

**STEP 8: EXPLORE MORE**
• `week` - Weekly report
• `month` - Monthly report  
• `categories` - Spending breakdown
• `show_prices` - See all trained items

📌 **QUICK TIPS:**
• Use #hashtags to categorize (e.g., #office, #marketing)
• Every transaction gets a unique ID for easy deletion
• Price training helps catch unusual expenses

Type `help` for complete command reference, or just start recording!"""

def get_quick_start_guide():
    """Quick start guide for immediate use."""
    return """🚀 **QUICK START GUIDE**

**JUST NEED TO RECORD SOMETHING?**
1. Expense: `+expense [amount] [what it was for]`
   Example: `+expense 300 Office supplies #office`

2. Sale: `+sale [amount] [description]`
   Example: `+sale 1000 Client payment #web_design`

3. Check: `balance` or `today`

**NEED TO DELETE?**
1. See recent: `list` or `/delete`
2. Delete by ID: `/delete ID:XXX-XXX`
3. Delete last: `/delete last`

**WANT TO ORGANIZE?**
Add #hashtags to descriptions:
• `+expense 500 #marketing Facebook ads`
• `+sale 2000 #web_design Website project`

**THAT'S IT!** Start recording and the bot will guide you."""

def get_help_message():
    """Returns comprehensive help message."""
    return """📖 **LEDGER BOT - COMPLETE COMMAND REFERENCE**

**📝 RECORD TRANSACTIONS:**
• `+sale [amount] [description]`
  Example: `+sale 500 Website design #web`
• `+expense [amount] [description]`
  Example: `+expense 100 Office supplies #office`
• `+income [amount] [description]`
  Example: `+income 1000 Investment #investment`

**💰 PRICE TRAINING (Prevent overpaying):**
• `+train "item name" min max [unit]`
  Example: `+train "printer paper" 60 80 per ream`
  Example: `+train "birthday basic" 40 45 per package`
• `+forget "item"` - Remove price training
• `price_check "item"` - Check price range
• `show_prices` - List all trained items

**📊 VIEW FINANCES:**
• `balance` - Current profit/loss (shows negative if in debt)
• `today` - Today's income vs expenses
• `week` - This week's summary
• `month` - This month's summary
• `categories` - Spending by category
• `list` - Your recent transactions with IDs

**🗑️ SMART DELETION:**
• `/delete` - Show recent transactions
• `/delete ID:XXX-XXX` - Delete by ID (shown when recording)
• `/delete last` - Delete most recent transaction
• `/delete list` - List your transactions with IDs

**🎓 LEARNING RESOURCES:**
• `tutorial` - Step-by-step beginner guide
• `quickstart` - Immediate getting started
• `examples` - Practical usage examples

**💡 PRO TIPS:**
1. Add #hashtags to automatically categorize
2. Every transaction gets a unique ID for safe deletion
3. Train common items to get price warnings
4. Use `list` before deleting to see transaction IDs

Need specific help? Try a command and the bot will guide you!"""

def get_examples_message():
    """Show practical examples of usage."""
    return """💡 **PRACTICAL EXAMPLES**

**BUSINESS SCENARIOS:**
1. Record client payment:
   `+sale 2000 Website redesign #client_project`

2. Record business expense:
   `+expense 300 Office rent #overhead`

3. Record software purchase:
   `+expense 150 Adobe Creative Cloud #software`

**PERSONAL FINANCE:**
1. Record grocery shopping:
   `+expense 250 Groceries #food`

2. Record salary:
   `+income 5000 Monthly salary #salary`

3. Record utility bill:
   `+expense 150 Electricity bill #utilities`

**PRICE TRAINING EXAMPLES:**
1. Train coffee prices:
   `+train "coffee" 10 20 per cup`

2. Train taxi fares:
   `+train "taxi" 20 50 per ride`

3. Train lunch prices:
   `+train "business lunch" 50 150 per person`

**CATEGORIZATION EXAMPLES:**
• Marketing: `#ads`, `#social_media`, `#seo`
• Office: `#supplies`, `#rent`, `#utilities`
• Services: `#web_hosting`, `#software`, `#consulting`
• Personal: `#food`, `#transport`, `#entertainment`

**TRY THESE:**
1. `+expense 80 Lunch with team #team_building`
2. `+sale 1500 Mobile app development #freelance`
3. Check: `balance`
4. See: `categories`"""

# ==================== COMMAND PROCESSOR ====================
def process_command(user_input, user_name="User"):
    """Main command processor."""
    if not user_input:
        return "🤔 I'm ready to help! Need to record a transaction or check your finances?"
    
    text = user_input.strip()
    text_lower = text.lower()

    # Clean bot mentions
    if BOT_USERNAME:
        mention_prefix = f"@{BOT_USERNAME}"
        if text_lower.startswith(mention_prefix.lower()):
            text = text[len(mention_prefix):].strip()
            text_lower = text.lower()

    # Clean punctuation
    text_lower = re.sub(r'^[:\s]+|[:\s]+$', '', text_lower)

    # ==================== LEARNING & HELP COMMANDS ====================
    
    # Tutorial
    if text_lower in ['tutorial', 'guide', 'walkthrough', 'learn', 'howto']:
        return get_tutorial_message()
    
    # Quick Start
    elif text_lower in ['quickstart', 'quick', 'start', 'getting started']:
        return get_quick_start_guide()
    
    # Examples
    elif text_lower in ['examples', 'example', 'show me']:
        return get_examples_message()
    
    # Help
    elif text_lower in ['help', '/start', '/help', 'commands', 'menu', 'what can you do']:
        return get_help_message()

    # ==================== PRICE TRAINING COMMANDS ====================
    
    # Train Price - FIXED VERSION
    elif text_lower.startswith('+train'):
        # Use the fixed parser function
        item_name, min_price, max_price, unit = parse_train_command(text)
        
        if item_name is None:
            # Error message is in the min_price variable
            return min_price  # This contains the error message
        
        # Validate the prices
        try:
            min_price = float(min_price)
            max_price = float(max_price)
        except (ValueError, TypeError):
            return "❌ Invalid price format. Use numbers like: 40 45"
        
        if min_price >= max_price:
            return "❌ Minimum price must be less than maximum price."
        
        if max_price > 10000000:  # 10 million cedis sanity check
            return "❌ Price seems unrealistic. Please check the amount."
        
        return train_price(item_name, min_price, max_price, unit, user_name)

    # Forget Price
    elif text_lower.startswith('+forget'):
        parts = text.split()
        if len(parts) < 2:
            return "❌ Format: +forget [item]\nExample: +forget \"printer paper\""
        
        item_name = ' '.join(parts[1:])
        # Remove quotes if present
        if item_name.startswith('"') and item_name.endswith('"'):
            item_name = item_name[1:-1]
        
        return forget_price(item_name)

    # Price Check
    elif text_lower.startswith('price_check'):
        parts = text.split()
        if len(parts) < 2:
            return "❌ Format: price_check [item]\nExample: price_check \"printer paper\""
        
        item_name = ' '.join(parts[1:])
        # Remove quotes if present
        if item_name.startswith('"') and item_name.endswith('"'):
            item_name = item_name[1:-1]
        
        price_info = check_price(item_name, 0)  # Check without amount
        
        if not price_info:
            return f"❌ No price training found for '{item_name}'\n💡 Train it first with: +train \"{item_name}\" [min] [max]"
        
        range_info = price_info['range']
        
        response = f"💰 **PRICE CHECK: {range_info['item']}**\n\n"
        response += f"Expected Range: ₵{range_info['min']:,.2f} - ₵{range_info['max']:,.2f}"
        if range_info['unit']:
            response += f" {range_info['unit']}"
        response += f"\nConfidence: {range_info['confidence']}%"
        
        return response

    # Show Prices
    elif text_lower in ['show_prices', 'list_prices', 'trained_items', 'prices']:
        return list_trained_items()

    # ==================== ORIGINAL TRANSACTION COMMANDS ====================
    
    # Record Sale
    elif text_lower.startswith('+sale'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +sale [amount] [description]\nExample: +sale 500 Website design\n💡 Add #hashtag to categorize: +sale 500 Website design #web"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('sale', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number.\n💡 Example: +sale 500 Website design"

    # Record Expense
    elif text_lower.startswith('+expense'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +expense [amount] [description]\nExample: +expense 100 Office supplies\n💡 Add #hashtag to categorize: +expense 100 Office supplies #office"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('expense', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number.\n💡 Example: +expense 100 Office supplies"

    # Record Income
    elif text_lower.startswith('+income'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +income [amount] [description]\nExample: +income 1000 Investment\n💡 Add #hashtag to categorize: +income 1000 Investment #investment"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('income', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number.\n💡 Example: +income 1000 Investment"

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

    # List Transactions
    elif text_lower in ['list', 'transactions', '/list']:
        try:
            parts = text_lower.split()
            limit = int(parts[1]) if len(parts) > 1 else 10
            return list_user_transactions(user_name, limit=min(limit, 20))
        except:
            return list_user_transactions(user_name, limit=10)

    # Smart Deletion
    elif text_lower.startswith('delete') or text_lower.startswith('/delete'):
        delete_part = text_lower.replace('delete', '', 1).replace('/', '', 1).strip()
        
        if not delete_part:
            return list_user_transactions(user_name, limit=5)
        
        elif delete_part == 'last':
            return delete_last_transaction(user_name)
        
        elif delete_part.startswith('id:'):
            transaction_id = delete_part[3:].strip().upper()
            return delete_transaction_by_id(transaction_id, user_name)
        
        elif delete_part == 'list':
            return list_user_transactions(user_name, limit=10)
        
        else:
            return """🗑️ **DELETION HELP**

**HOW TO DELETE:**
1. First, find the transaction ID:
   • Type `list` to see your recent transactions
   • Each transaction shows an ID like `EXP-ABC123`

2. Then delete it:
   • `/delete ID:EXP-ABC123` - Delete specific transaction
   • `/delete last` - Delete most recent
   • `/delete` - Show options

**EXAMPLE:**
You record: `+expense 500 Test`
It shows: "Recorded... ID: EXP-ABC123"
You delete: `/delete ID:EXP-ABC123`"""

    # ==================== GREETINGS & MISCELLANEOUS ====================
    
    # Greetings
    elif text_lower in ['hi', 'hello', 'hey', 'hola', 'greetings']:
        return f"Hello {user_name}! 👋 Ready to manage your finances?\n💡 Try `tutorial` for a step-by-step guide, or `quickstart` to jump right in!"
    
    # Thanks
    elif 'thank' in text_lower or 'thanks' in text_lower:
        return "You're welcome! 😊 Let me know if you need anything else.\n💡 Need help? Try `tutorial` or `examples` for guidance."
    
    # Unknown command - HELPFUL RESPONSE
    else:
        return f"""🤔 I didn't understand that.

**QUICK OPTIONS:**
• Record transaction: `+expense 100 Lunch` or `+sale 500 Project`
• Check finances: `balance`, `today`, `week`
• Learn how: `tutorial` (beginner guide) or `quickstart` (fast start)
• See all commands: `help`

**OR TRY THESE:**
1. `+train "item" 100 200` - Train price ranges
2. `list` - See your recent transactions
3. `categories` - View spending breakdown
4. `show_prices` - See trained items

What would you like to do?"""