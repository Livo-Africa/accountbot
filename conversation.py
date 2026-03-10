# conversation.py - Conversational Intelligence Module
import re
import random
from datetime import datetime
import time
from gemini import process_with_gemini

class ConversationalAgent:
    """Makes the bot conversational and intelligent with optional AI"""
    
    def __init__(self):
        self.greetings = {
            'morning': ['Good morning! ☀️', 'Morning! Ready to tackle the day?', 'Hello! How are you today?'],
            'afternoon': ['Good afternoon! 🌤️', 'Afternoon! How\'s your day going?', 'Hi there!'],
            'evening': ['Good evening! 🌙', 'Evening! How was your day?', 'Hello!'],
            'general': ['Hello! 👋', 'Hi there!', 'Hey!']
        }
        
        self.responses = {
            'thanks': [
                "You're welcome! 😊", 
                "Happy to help! 👍", 
                "Anytime! Let me know if you need anything else."
            ],
            'compliment': [
                "Thanks! I'm here to make finance management easier. 💪",
                "Appreciate it! You're doing great with your tracking. 📊",
                "Thank you! Let's keep those finances organized."
            ],
            'encouragement': [
                "Great job staying on top of your finances! 🎯",
                "You're doing amazing with your tracking! 📈",
                "Keep up the good work! Every transaction counts. 💰"
            ],
            'apology': [
                "Sorry about that! Let me help you get it right.",
                "My mistake! Let's try that again.",
                "Oops! I didn't understand that. Could you rephrase?"
            ]
        }
        
        # User conversation memory (simple in-memory store)
        self.user_memory = {}
        
    def detect_intent(self, message: str) -> str:
        """Detect the user's intent from their message (Fallback Logic)."""
        message_lower = message.lower().strip()
        
        # Greetings
        greeting_words = ['hi', 'hello', 'hey', 'hola', 'yo', 'greetings', 'good morning', 'good afternoon', 'good evening']
        if any(word in message_lower for word in greeting_words):
            return 'greeting'
        
        # Thanks
        if any(word in message_lower for word in ['thanks', 'thank you', 'ty', 'appreciate']):
            return 'thanks'
        
        # Compliments
        if any(word in message_lower for word in ['good job', 'well done', 'nice work', 'great', 'awesome', 'good bot']):
            return 'compliment'
        
        # Questions
        if '?' in message:
            if 'how much' in message_lower:
                return 'question_amount'
            elif 'what' in message_lower or 'which' in message_lower:
                return 'question_what'
            elif 'when' in message_lower:
                return 'question_when'
            elif 'how' in message_lower:
                return 'question_how'
            elif 'why' in message_lower:
                return 'question_why'
            return 'question_general'
        
        # Transaction intent
        transaction_indicators = {
            'spent': 'expense',
            'paid': 'expense',
            'bought': 'expense',
            'purchased': 'expense',
            'made': 'sale',
            'earned': 'sale',
            'received': 'income',
            'got paid': 'income',
            'sold': 'sale',
            'income': 'income'
        }
        
        for indicator, trans_type in transaction_indicators.items():
            if indicator in message_lower:
                return f'intent_record_{trans_type}'
        
        # Help intent
        if any(word in message_lower for word in ['help', 'what can you do', 'commands', 'menu']):
            return 'intent_help'
        
        # Report intent
        if 'balance' in message_lower or 'how am i doing' in message_lower:
            return 'intent_balance'
        if 'today' in message_lower or "today's" in message_lower:
            return 'intent_today'
        if 'week' in message_lower:
            return 'intent_week'
        if 'month' in message_lower:
            return 'intent_month'
        
        return 'unknown'
    
    def generate_greeting(self, user_name: str = "User") -> str:
        """Generate appropriate greeting based on time of day."""
        hour = datetime.now().hour
        
        if 5 <= hour < 12:
            greeting = random.choice(self.greetings['morning'])
        elif 12 <= hour < 17:
            greeting = random.choice(self.greetings['afternoon'])
        elif 17 <= hour < 22:
            greeting = random.choice(self.greetings['evening'])
        else:
            greeting = random.choice(self.greetings['general'])
        
        return f"{greeting} I'm your financial assistant!"
    
    def generate_response(self, intent: str, user_name: str = "User") -> str:
        """Generate conversational response based on intent."""
        
        if intent == 'greeting':
            return self.generate_greeting(user_name)
        
        elif intent == 'thanks':
            return random.choice(self.responses['thanks'])
        
        elif intent == 'compliment':
            return random.choice(self.responses['compliment'])
        
        elif intent.startswith('intent_record_'):
            trans_type = intent.replace('intent_record_', '')
            return f"Sure! I can help you record a {trans_type}. Just tell me the amount and what it's for. 💰"
        
        elif intent == 'intent_help':
            return "I can help you record transactions, check balances, and analyze your finances! Type 'help' for a full list of commands. 📖"
        
        elif intent == 'intent_balance':
            return "Let me check your balance for you... ⏳"
        
        elif intent == 'intent_today':
            return "Checking today's transactions... 📊"
        
        elif intent.startswith('question_'):
            return "That's a good question! Let me check the information for you. 🤔"
        
        elif intent == 'unknown':
            return ""  # Empty string means let the main engine handle it
        
        return ""
    
    def extract_transaction_details(self, message: str):
        """Extract transaction details from natural language (Fallback Logic)."""
        patterns = [
            # "spent 100 on lunch"
            (r'(?:spent|paid|bought|purchased)\s+(\d+(?:\.\d{1,2})?)\s+(?:on|for)\s+(.+)', 'expense'),
            # "made 500 from client"
            (r'(?:made|earned|received|got)\s+(\d+(?:\.\d{1,2})?)\s+(?:from|for)\s+(.+)', 'sale'),
            # "100 for lunch"
            (r'(\d+(?:\.\d{1,2})?)\s+(?:for|on)\s+(.+)', 'unknown'),
            # "lunch 100"
            (r'(.+?)\s+(\d+(?:\.\d{1,2})?)$', 'unknown'),
        ]
        
        message_lower = message.lower()
        
        for pattern, trans_type in patterns:
            match = re.search(pattern, message_lower)
            if match:
                if trans_type == 'unknown':
                    # Need to determine type from context
                    if len(match.groups()) == 2:
                        # Pattern "100 for lunch" or "lunch 100"
                        try:
                            # Try to figure out which is amount
                            amount = None
                            description = None
                            
                            # Check if first group is number
                            try:
                                amount = float(match.group(1))
                                description = match.group(2)
                            except ValueError:
                                # First group is not a number, try second
                                try:
                                    amount = float(match.group(2))
                                    description = match.group(1)
                                except ValueError:
                                    continue
                            
                            # Guess type based on keywords
                            if any(word in message_lower for word in ['spent', 'paid', 'bought', 'purchased']):
                                guessed_type = 'expense'
                            elif any(word in message_lower for word in ['made', 'earned', 'received', 'sold']):
                                guessed_type = 'sale'
                            else:
                                # Default to expense for now
                                guessed_type = 'expense'
                            
                            return {
                                'type': guessed_type,
                                'amount': amount,
                                'description': description,
                                'confidence': 0.7
                            }
                        except:
                            continue
                else:
                    # Clear pattern match
                    amount = match.group(1)
                    description = match.group(2)
                    return {
                        'type': trans_type,
                        'amount': amount,
                        'description': description,
                        'confidence': 0.85
                    }
        
        return None
    
    def enhance_transaction_response(self, original_response: str, trans_type: str) -> str:
        """Make transaction responses more conversational."""
        enhancements = {
            'sale': [
                "🎉 Great! Recorded your sale: {}",
                "💰 Sale recorded successfully: {}",
                "📈 Excellent! Added to sales: {}"
            ],
            'expense': [
                "📝 Got it! Expense recorded: {}",
                "💸 Expense saved: {}",
                "📋 Recorded your expense: {}"
            ],
            'income': [
                "🎯 Income recorded! {}",
                "💪 Nice! Income added: {}",
                "📊 Income saved: {}"
            ],
            'success': [
                "✅ Done! {}",
                "👍 All set! {}",
                "✨ Perfect! {}"
            ],
            'error': [
                "🤔 Hmm, I need a bit more info: {}",
                "Let me help you get that right: {}",
                "I think there's a small issue: {}"
            ]
        }
        
        # Determine which enhancement to use
        if '✅' in original_response or 'Recorded' in original_response:
            if trans_type in enhancements:
                template = random.choice(enhancements[trans_type])
                return template.format(original_response.replace('✅ ', '').replace('❌ ', ''))
            else:
                template = random.choice(enhancements['success'])
                return template.format(original_response.replace('✅ ', '').replace('❌ ', ''))
        elif '❌' in original_response:
            template = random.choice(enhancements['error'])
            return template.format(original_response.replace('❌ ', ''))
        
        return original_response
    
    def add_personality(self, response: str, user_name: str = "User") -> str:
        """Add personality elements to a response."""
        
        # Don't modify if already has personality
        if any(emoji in response for emoji in ['🎉', '💰', '📝', '💸', '🎯', '💪', '📊', '✅', '👍', '✨', '🤔']):
            return response
        
        # Add user's name if not present (only for conversational responses)
        if user_name != "User" and user_name not in response:
            # Only add name to conversational responses (not lists or reports)
            if len(response) < 100 and not any(word in response.lower() for word in ['list', 'report', 'summary', 'transactions:']):
                response = f"{user_name}, {response}"
        
        return response
    
    def update_user_memory(self, user_id: str, key: str, value: str):
        """Update user memory for context."""
        if user_id not in self.user_memory:
            self.user_memory[user_id] = {}
        
        self.user_memory[user_id][key] = {
            'value': value,
            'timestamp': time.time()
        }
    
    def get_user_memory(self, user_id: str, key: str):
        """Get user memory for context."""
        if user_id in self.user_memory and key in self.user_memory[user_id]:
            # Check if memory is recent (within 1 hour)
            if time.time() - self.user_memory[user_id][key]['timestamp'] < 3600:
                return self.user_memory[user_id][key]['value']
        
        return None


class SmartProcessor:
    """Delegates to Gemini AI first; gracefully falls back to Regex if API fails."""
    
    def __init__(self):
        # We need the old parser for fallback command routing
        self.command_patterns = {
            'balance': [
                r'how.*much.*(?:money|balance|profit)',
                r'what.*my.*balance',
                r'check.*balance',
                r'current.*(?:money|funds)'
            ],
            'today': [
                r"today.*(?:transactions|summary|sales|expenses)",
                r"how.*today.*(?:going|doing)",
                r"what.*happened.*today"
            ],
            'week': [
                r'week.*(?:summary|report|sales|expenses)',
                r'this.*week',
                r'weekly.*report'
            ],
            'month': [
                r'month.*(?:summary|report|sales|expenses)',
                r'this.*month',
                r'monthly.*report'
            ],
            'categories': [
                r'categor(?:y|ies)',
                r'where.*spent',
                r'what.*spent.*on',
                r'breakdown'
            ],
            'list': [
                r'my.*(?:transactions|records)',
                r'list.*(?:transactions|records)',
                r'what.*(?:recorded|entered)',
                r'recent.*transactions'
            ],
            'help': [
                r'what.*can.*you.*do',
                r'how.*use.*you',
                r'commands',
                r'help.*me',
                r'what.*options'
            ]
        }
        
    def process_message(self, message: str, user_name: str, saved_memory: str = "") -> dict:
        """
        Attempts to process the message via Gemini.
        Returns a dict. If API fails, dict contains {"error": "api_failed"}.
        """
        # Try Gemini API first
        gemini_result = process_with_gemini(message, user_name, saved_memory)
        return gemini_result
    
    def fallback_parse_to_command(self, message: str):
        """Parse natural language to a command (Fallback)."""
        message_lower = message.lower().strip()
        
        # Check for transaction patterns first
        if any(word in message_lower for word in ['spent', 'paid', 'bought', 'purchased', 'expense']):
            return None
        
        if any(word in message_lower for word in ['made', 'earned', 'received', 'sale', 'income']):
            return None
        
        # Check for command patterns
        for command, patterns in self.command_patterns.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    return command
        
        return None

# Global instances
conversation_agent = ConversationalAgent()
nlp_processor = SmartProcessor()