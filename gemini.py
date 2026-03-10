import os
import json
import logging
import google.generativeai as genai

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Gemini
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Configuration for the model
    generation_config = {
        "temperature": 0.2, # Low temperature for more deterministic JSON output
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
        "response_mime_type": "application/json",
    }
    
    # We use 1.5 flash for speed and free tier limits
    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config,
        )
    except Exception as e:
        logger.error(f"Failed to initialize Gemini model: {e}")
        model = None
else:
    model = None

# System prompt to guide Gemini's behavior and enforce JSON schema
SYSTEM_PROMPT = """You are a highly intelligent financial assistant Telegram bot. Your primary job is to understand user messages, figure out what they want to do, and extract any relevant data.
You MUST ALWAYS respond in valid JSON format matching the schema below.

You also have access to the user's "Long-Term Memory", which contains their established preferences, budgets, and habits. Use this context to make smarter decisions about categorization, names, and intent.

User's Context/Memory:
{memory_context}

Output JSON Schema:
{
    "intent": "String (one of: 'greeting', 'compliment', 'thanks', 'record_expense', 'record_sale', 'record_income', 'check_balance', 'check_today', 'check_week', 'check_month', 'help', 'preference_update', 'general_chat', 'unknown')",
    "amount": "Number (float) or null if not applicable. If the user mentions spending/earning, extract the total amount here.",
    "description": "String or null. The name of the item bought/sold, the service provided, or the reason for the income/expense. Keep it brief (e.g., 'lunch', '3 coffees', 'website design').",
    "conversational_response": "String. A friendly, helpful, short response to the user. EMOJIS INCLUDED. If recording a transaction, say something acknowledging it (e.g., 'Got it! I\\'ll record 50 cedis for lunch. 🍔'). If general chat, respond naturally. If preference update, acknowledge the learning.",
    "memory_to_save": "String or null. ONLY use this if intent is 'preference_update'. Summarize the new rule/fact to remember concisely (e.g., 'User spends 50 cedis on lunch daily', 'Favorite restaurant is KFC')."
}

Examples:
User: "Hey there!"
Output: {"intent": "greeting", "amount": null, "description": null, "conversational_response": "Hello! 👋 How can I help you manage your finances today?", "memory_to_save": null}

User: "I just spent 150 on an uber ride"
Output: {"intent": "record_expense", "amount": 150.0, "description": "uber ride", "conversational_response": "📝 Got it! I've recorded 150 cedis for your Uber ride. 🚗", "memory_to_save": null}

User: "Made 5000 from the new website client"
Output: {"intent": "record_sale", "amount": 5000.0, "description": "website client", "conversational_response": "🎉 Awesome! I've added 5,000 cedis to your sales. Keep it up! 💻", "memory_to_save": null}

User: "Remember that I usually pay 100 for internet every month"
Output: {"intent": "preference_update", "amount": null, "description": null, "conversational_response": "Got it! I will remember that your standard internet bill is 100 cedis. 🧠", "memory_to_save": "Standard monthly internet bill is 100"}

User: "How much did I make today?"
Output: {"intent": "check_today", "amount": null, "description": null, "conversational_response": "Let me pull up today's numbers for you... 📊", "memory_to_save": null}

User: "Thanks"
Output: {"intent": "thanks", "amount": null, "description": null, "conversational_response": "You're very welcome! Let me know if you need anything else. 😊", "memory_to_save": null}
"""

def process_with_gemini(text: str, user_name: str, context: str = "") -> dict:
    """
    Process natural language using Gemini. 
    Gracefully falls back if the API fails, is not configured, or hits limits.
    """
    if not model:
        # Graceful fallback: API key missing or model failed to load
        return {"error": "api_failed"}
        
    try:
        # Prepare the prompt with memory context
        prompt = SYSTEM_PROMPT.format(memory_context=context if context else "No special preferences saved yet.")
        prompt += f"\n\nUser ({user_name}): {text}\nOutput:"

        # Call Gemini (Generative AI)
        response = model.generate_content(prompt)
        
        # Parse the JSON string into a Python dictionary
        result = json.loads(response.text)
        
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
