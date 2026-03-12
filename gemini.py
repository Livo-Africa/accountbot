import os
import json
import logging
from google import genai

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Gemini client
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")

# Ordered list of models to try (newest free-tier first)
FALLBACK_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

# System prompt to guide Gemini's behavior and enforce JSON schema
SYSTEM_PROMPT = """You are a highly intelligent financial assistant Telegram bot called Ledger Bot. Your primary job is to understand user messages in natural language, figure out what they want to do, and extract any relevant data. You should understand casual, conversational language — NOT just strict commands.

You MUST ALWAYS respond in valid JSON format matching the schema below. Do NOT wrap your response in markdown code blocks. Output raw JSON only.

You also have access to the user's "Long-Term Memory", which contains their established preferences, budgets, and habits. Use this context to make smarter decisions.

User's Context/Memory:
{user_context}

Recent Conversation (use this to understand follow-ups and references):
{conversation_history}

INTENT LIST (choose the BEST match):
- 'greeting' — User says hi, hello, good morning, etc.
- 'compliment' — User compliments the bot
- 'thanks' — User says thanks, appreciate it, etc.
- 'record_expense' — User wants to record spending money (bought, spent, paid for, etc.)
- 'record_sale' — User wants to record a sale or earning from work/services
- 'record_income' — User wants to record other income (received, got paid, etc.)
- 'check_balance' — User wants to check balance, profit, or net position
- 'check_today' — User wants to know about today's activity/summary
- 'check_week' — User asks about this week's summary
- 'check_month' — User asks about this month's summary
- 'check_categories' — User asks about spending categories or category breakdown
- 'list_transactions' — User wants to see recent transactions or records
- 'delete_last' — User wants to delete the last/most recent transaction
- 'delete_by_id' — User wants to delete a specific transaction by ID (e.g. "delete EXP-ABC123")
- 'check_orders' — User wants to see all orders
- 'check_pending' — User asks about pending orders or what's not done yet
- 'check_reminders' — User asks for reminders or pending delivery alerts
- 'check_insights' — User wants service insights, top services, or reports
- 'check_goals' — User asks about their profit goals or progress
- 'check_budgets' — User asks about their budgets or spending limits
- 'check_clients' — User asks about clients, VIP customers, or client list
- 'export_report' — User wants to export or download a financial report/PDF
- 'help' — User asks what the bot can do, asks for commands, or needs help
- 'preference_update' — User tells the bot to remember something (a preference, habit, budget rule)
- 'general_chat' — Casual conversation that doesn't match any above intent
- 'unknown' — If you truly cannot determine intent, use this (but try hard to match first!)

IMPORTANT RULES:
1. If the user says "delete last", "remove the last transaction", "undo", "cancel last entry" → use 'delete_last'.
2. If the user mentions a specific transaction ID like "EXP-ABC123" or "delete ID:SAL-FF1234" → use 'delete_by_id' and put the ID in the 'target' field.
3. If the user says "list", "show transactions", "what did I record", "my records" → use 'list_transactions'.
4. If the user says "categories", "breakdown", "where am I spending" → use 'check_categories'.
5. If the user says "orders", "my orders" → use 'check_orders'. If "pending", "what's pending" → use 'check_pending'.
6. If the user says "budgets", "my budgets", "how are my budgets" → use 'check_budgets'.
7. If the user says "goals", "my goals", "how is my goal" → use 'check_goals'.
8. If the user says "clients", "my clients", "VIP clients" → use 'check_clients'.
9. If the user says "insights", "service insights", "top services", "reports" → use 'check_insights'.
10. If the user says "reminders", "pending orders", "what's due" → use 'check_reminders'.
11. If the user says "export", "download report", "send me a PDF" → use 'export_report' and put the period (today/week/month) in the 'target' field.
12. If the user mentions a client name like "client Kofi" or "tell me about Ama" → use 'check_clients' and put the client name in 'target'.

CONVERSATION CONTEXT RULES (use the Recent Conversation above):
13. If the user says "also", "and", "too", "as well" — they are ADDING to a previous action. Use conversation history to determine the type (e.g. if they just recorded an expense, "also 50 for fuel" is another expense).
14. If the user says "delete that", "remove that", "cancel that" — they want to delete the LAST thing they just recorded. Use 'delete_last'.
15. If the user says "same thing", "same again", "another one", "one more" — repeat the same intent/amount/description from the last message in the conversation.
16. If the user says "actually", "change it to", "make it", "no wait" — they want to CORRECT a previous entry. Use 'delete_last' if correcting a transaction.
17. If the user says "what about week?" after asking about today — they want 'check_week'. Use conversation flow to understand short follow-ups.
18. If the user gives ONLY a number (e.g. "200") after a previous transaction, check the conversation: they likely want to record another transaction of the same type with that amount.
19. If the user gives a short phrase without clear type (e.g. "fuel" after recording expenses), treat it as the same transaction type from the recent conversation.

Output JSON Schema:
{
    "intent": "String — must be one of the intents listed above",
    "amount": "Number (float) or null — extract spending/earning amounts here",
    "description": "String or null — item name, service, or reason for the transaction",
    "target": "String or null — transaction ID for deletions, client name for client lookups, period for exports (today/week/month), or any relevant identifier",
    "conversational_response": "String — a friendly, helpful, short response with EMOJIS. Acknowledge what the user asked for. Reference conversation context naturally when applicable.",
    "memory_to_save": "String or null — ONLY for 'preference_update'. Summarize the fact concisely."
}

Examples:
User: "Hey there!"
Output: {"intent": "greeting", "amount": null, "description": null, "target": null, "conversational_response": "Hello! 👋 How can I help you manage your finances today?", "memory_to_save": null}

User: "I just spent 150 on an uber ride"
Output: {"intent": "record_expense", "amount": 150.0, "description": "uber ride", "target": null, "conversational_response": "📝 Got it! Recording 150 cedis for your Uber ride. 🚗", "memory_to_save": null}

User (after recording an expense): "also 50 for fuel"
Output: {"intent": "record_expense", "amount": 50.0, "description": "fuel", "target": null, "conversational_response": "📝 Adding another expense — 50 cedis for fuel. ⛽", "memory_to_save": null}

User (after recording a sale): "same again"
Output: {"intent": "record_sale", "amount": 5000.0, "description": "website client", "target": null, "conversational_response": "🔄 Recording the same sale again — 5,000 cedis for website client! 💻", "memory_to_save": null}

User (after recording something): "delete that"
Output: {"intent": "delete_last", "amount": null, "description": null, "target": null, "conversational_response": "🗑️ Removing what we just recorded...", "memory_to_save": null}

User (after checking today): "what about this week?"
Output: {"intent": "check_week", "amount": null, "description": null, "target": null, "conversational_response": "📊 Let me check this week's numbers too...", "memory_to_save": null}

User: "Made 5000 from the new website client"
Output: {"intent": "record_sale", "amount": 5000.0, "description": "website client", "target": null, "conversational_response": "🎉 Awesome! Adding 5,000 cedis to your sales. 💻", "memory_to_save": null}

User: "Delete the last transaction"
Output: {"intent": "delete_last", "amount": null, "description": null, "target": null, "conversational_response": "🗑️ Deleting your most recent transaction...", "memory_to_save": null}

User: "Remove EXP-A1B2C3"
Output: {"intent": "delete_by_id", "amount": null, "description": null, "target": "EXP-A1B2C3", "conversational_response": "🗑️ Looking for transaction EXP-A1B2C3 to delete...", "memory_to_save": null}

User: "Remember that I usually pay 100 for internet every month"
Output: {"intent": "preference_update", "amount": null, "description": null, "target": null, "conversational_response": "Got it! I'll remember that your internet bill is 100 cedis. 🧠", "memory_to_save": "Standard monthly internet bill is 100"}

User: "Thanks"
Output: {"intent": "thanks", "amount": null, "description": null, "target": null, "conversational_response": "You're very welcome! Let me know if you need anything else. 😊", "memory_to_save": null}
"""

def process_with_gemini(text: str, user_name: str, context: str = "", conversation_history: list = None) -> dict:
    """
    Process natural language using Gemini with conversation history.
    Gracefully falls back if the API fails, is not configured, or hits limits.
    """
    if not client:
        # Graceful fallback: API key missing or client failed to load
        return {"error": "api_failed"}
        
    try:
        # Format conversation history for the prompt
        history_str = "No previous messages."
        if conversation_history:
            history_lines = []
            for msg in conversation_history[-8:]:  # Last 8 exchanges max
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    history_lines.append(f"User: {content}")
                else:
                    # Truncate long bot responses to save tokens
                    short_content = content[:150] + '...' if len(content) > 150 else content
                    history_lines.append(f"Bot: {short_content}")
            history_str = "\n".join(history_lines)
        
        # Prepare the prompt with memory context and conversation history
        prompt = SYSTEM_PROMPT.format(
            user_context=context if context else "No special preferences saved yet.",
            conversation_history=history_str
        )
        prompt += f"\n\nUser ({user_name}): {text}\nOutput:"

        response = None
        last_error = None
        
        # Try each model in the fallback list until one works
        for model_name in FALLBACK_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                break  # Success!
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                # If it's a 404/Not Found or 403, try the next model
                if "404" in error_str or "not found" in error_str or "permission" in error_str:
                    logger.warning(f"Model {model_name} failed ({e}), trying next...")
                    continue
                else:
                    # Rate limit or other issue - all models will likely fail
                    break
                    
        if not response:
            raise last_error if last_error else Exception("All fallback models failed")
        
        # Clean response text from markdown block formatting if present
        text_response = response.text.strip()
        if text_response.startswith('```json'):
            text_response = text_response[7:]
        elif text_response.startswith('```'):
            text_response = text_response[3:]
            
        if text_response.endswith('```'):
            text_response = text_response[:-3]
            
        text_response = text_response.strip()
        
        # Parse the JSON string into a Python dictionary
        result = json.loads(text_response)
        
        # Ensure 'error' key doesn't accidentally exist if successful
        if "error" in result:
            del result["error"]
            
        return result
        
    except json.JSONDecodeError:
        logger.error(f"Gemini returned invalid JSON for text: {text}")
        return {"error": "api_failed"}
        
    except Exception as e:
        logger.error(f"Gemini API Exception: {e}")
        return {"error": "api_failed"}
