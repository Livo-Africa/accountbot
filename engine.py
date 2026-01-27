# engine.py - COMPLETE WITH FIXED TRAIN COMMAND AND CONVERSATION
import os
import json
import gspread
import re
import secrets
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from collections import defaultdict
from conversation import conversation_agent, nlp_processor

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
        
        response = f"✅ {action.capitalize()} price range for '{item_name}': ₵{min_price:,.2f} - ₵{max_price:,.2f}" + \
               (f" {unit}" if unit else "")
        
        # Enhance with conversation
        return conversation_agent.enhance_transaction_response(response, 'success')
        
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
        
        response = f"✅ Forgot price training for '{item_name}'"
        return conversation_agent.enhance_transaction_response(response, 'success')
        
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
        
        # Enhance with conversation
        enhanced_response = conversation_agent.enhance_transaction_response(response, trans_type)
        enhanced_response = conversation_agent.add_personality(enhanced_response, user_name)
        
        return enhanced_response
        
    except Exception as e:
        error_response = f"❌ Failed to save: {str(e)[:100]}"
        return conversation_agent.enhance_transaction_response(error_response, 'error')

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
        
        response = f"✅ Deleted transaction `{transaction_id}` ({format_cedi(transaction['amount'])})"
        return conversation_agent.enhance_transaction_response(response, 'success')
        
    except Exception as e:
        error_response = f"❌ Failed to delete: {str(e)[:100]}"
        return conversation_agent.enhance_transaction_response(error_response, 'error')

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
                
                response = f"✅ Deleted old transaction ({format_cedi(transaction['amount'])})"
                return conversation_agent.enhance_transaction_response(response, 'success')
        
        return "❌ Could not find matching transaction."
        
    except Exception as e:
        error_response = f"❌ Failed to delete old transaction: {str(e)[:100]}"
        return conversation_agent.enhance_transaction_response(error_response, 'error')

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
        'price_training': 'enabled',
        'conversational_ai': 'enabled'
    }

# ==================== CONVERSATIONAL COMMAND PROCESSOR ====================
def get_help_message():
    """Returns comprehensive help message."""
    return """📖 **LEDGER BOT COMMANDS**

**💼 RECORD TRANSACTIONS:**
• `+sale [amount] [description]`
• `+expense [amount] [description]`
• `+income [amount] [description]`

**🗣️ NATURAL LANGUAGE (NEW!):**
• "I spent 100 on lunch"
• "Made 500 from client"
• "Paid 200 for electricity"
• "What's my balance today?"
• "How much did I spend this week?"

**💰 PRICE TRAINING:**
• `+train "item" min max [unit]`
  Example: `+train "birthday basic" 40 45 per package`
• `+forget "item"`
• `price_check "item"`
• `show_prices`

**📊 VIEW FINANCES:**
• `balance` - Current profit/loss
• `today` - Today's summary
• `week` - Weekly report
• `month` - Monthly report
• `categories` - Category breakdown
• `list` - Your recent transactions

**🗑️  SMART DELETION:**
• `/delete` - Show deletion options
• `/delete ID:XXX-XXX` - Delete by ID
• `/delete last` - Delete most recent
• `/delete list` - List your transactions

**💡 EXAMPLES:**
• `+train "lunch" 20 50 per person`
• "I spent 300 on printer paper"
• Bot will warn if price is unusual!
• `show_prices` - See all trained items

Need help? Just type `help` or ask naturally!"""

def process_command_with_conversation(user_input, user_name="User", user_id=None):
    """Main command processor with conversation support."""
    if not user_input:
        return "🤔 Please enter a command or ask me something."
    
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
    
    # ==================== CONVERSATION FIRST ====================
    
    # 1. Check for conversational intent
    intent = conversation_agent.detect_intent(text)
    conversational_response = conversation_agent.generate_response(intent, user_name)
    
    if conversational_response:
        return conversation_agent.add_personality(conversational_response, user_name)
    
    # 2. Try natural language transaction parsing
    transaction_details = conversation_agent.extract_transaction_details(text)
    if transaction_details and transaction_details['confidence'] > 0.6:
        # We have a natural language transaction!
        trans_type = transaction_details['type']
        amount = transaction_details['amount']
        description = transaction_details['description']
        
        # Add hashtag extraction from description
        hashtags = re.findall(r'#(\w+)', description)
        if hashtags:
            # Remove hashtags from description
            description = re.sub(r'#\w+', '', description).strip()
            description = re.sub(r'\s+', ' ', description)
        
        # Record the transaction
        return record_transaction(trans_type, amount, description, user_name)
    
    # 3. Try natural language command parsing
    nl_command = nlp_processor.parse_to_command(text)
    if nl_command:
        # Process the natural language command
        return process_basic_command(nl_command, user_name, text_lower)
    
    # ==================== BASIC COMMANDS (Original System) ====================
    return process_basic_command(text, user_name, text_lower)

def process_basic_command(text, user_name, text_lower=None):
    """Process basic commands (original system)."""
    if text_lower is None:
        text_lower = text.lower()
    
    # ==================== PRICE TRAINING COMMANDS ====================
    
    # Train Price - USING FIXED PARSER
    if text_lower.startswith('+train'):
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
            return f"❌ No price training found for '{item_name}'"
        
        range_info = price_info['range']
        
        response = f"💰 **PRICE CHECK: {range_info['item']}**\n\n"
        response += f"Expected Range: ₵{range_info['min']:,.2f} - ₵{range_info['max']:,.2f}"
        if range_info['unit']:
            response += f" {range_info['unit']}"
        response += f"\nConfidence: {range_info['confidence']}%"
        
        return conversation_agent.add_personality(response, user_name)

    # Show Prices
    elif text_lower in ['show_prices', 'list_prices', 'trained_items', 'prices']:
        return list_trained_items()

    # ==================== ORIGINAL TRANSACTION COMMANDS ====================
    
    # Record Sale
    elif text_lower.startswith('+sale'):
        parts = text.split()
        if len(parts) < 3:
            return "❌ Format: +sale [amount] [description]\nExample: +sale 500 Website design #web"
        try:
            amount = float(parts[1])
            description = ' '.join(parts[2:])
            return record_transaction('sale', amount, description, user_name)
        except ValueError:
            return "❌ Amount must be a number."

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
            return "❌ Amount must be a number."

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
            return "❌ Amount must be a number."

    # Check Balance
    elif text_lower in ['balance', 'profit', 'net']:
        balance_response = get_balance()
        return conversation_agent.add_personality(balance_response, user_name)

    # Today's Summary
    elif text_lower in ['today', 'today?', 'today.']:
        today_response = get_today_summary()
        return conversation_agent.add_personality(today_response, user_name)

    # Week Summary
    elif text_lower in ['week', 'weekly', 'this week']:
        week_response = get_period_summary('week')
        return conversation_agent.add_personality(week_response, user_name)

    # Month Summary
    elif text_lower in ['month', 'monthly', 'this month']:
        month_response = get_period_summary('month')
        return conversation_agent.add_personality(month_response, user_name)

    # Categories Report
    elif text_lower in ['categories', 'category', '/categories']:
        categories_response = get_categories_report()
        return conversation_agent.add_personality(categories_response, user_name)

    # List Transactions
    elif text_lower in ['list', 'transactions', '/list']:
        try:
            parts = text_lower.split()
            limit = int(parts[1]) if len(parts) > 1 else 10
            list_response = list_user_transactions(user_name, limit=min(limit, 20))
        except:
            list_response = list_user_transactions(user_name, limit=10)
        
        return conversation_agent.add_personality(list_response, user_name)

    # Smart Deletion
    elif text_lower.startswith('delete') or text_lower.startswith('/delete'):
        delete_part = text_lower.replace('delete', '', 1).replace('/', '', 1).strip()
        
        if not delete_part:
            list_response = list_user_transactions(user_name, limit=5)
            return conversation_agent.add_personality(list_response, user_name)
        
        elif delete_part == 'last':
            delete_response = delete_last_transaction(user_name)
            return conversation_agent.add_personality(delete_response, user_name)
        
        elif delete_part.startswith('id:'):
            transaction_id = delete_part[3:].strip().upper()
            delete_response = delete_transaction_by_id(transaction_id, user_name)
            return conversation_agent.add_personality(delete_response, user_name)
        
        elif delete_part == 'list':
            list_response = list_user_transactions(user_name, limit=10)
            return conversation_agent.add_personality(list_response, user_name)
        
        else:
            delete_help = """🗑️ **DELETION HELP**

**OPTIONS:**
• `/delete` - Show recent transactions
• `/delete last` - Delete most recent
• `/delete ID:XXX-XXX` - Delete by ID
• `/delete list` - List your transactions

**EXAMPLE:**
Record: `+expense 500 Test`
→ Shows: "Recorded... ID: EXP-ABC123"
Delete: `/delete ID:EXP-ABC123`"""
            
            return conversation_agent.add_personality(delete_help, user_name)

    # Help
    elif text_lower in ['help', '/start', '/help', 'commands', 'menu']:
        help_response = get_help_message()
        return conversation_agent.add_personality(help_response, user_name)

    # Unknown
    else:
        unknown_response = f"""🤔 Command not recognized.

**Try:**
• Record: `+sale 500 Project #client`
• Ask naturally: "I spent 100 on lunch"
• Train: `+train "birthday basic" 40 45 per package`
• Check: `balance`, `today`, `show_prices`
• Delete: `/delete` (shows options)
• Help: `help`

Type `help` for complete list!"""
        
        return conversation_agent.add_personality(unknown_response, user_name)

# Keep original process_command for backward compatibility
def process_command(user_input, user_name="User"):
    """Original command processor (for backward compatibility)."""
    return process_command_with_conversation(user_input, user_name)