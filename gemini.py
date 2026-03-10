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
}

# Ordered list of models to try if the primary one is 404/unavailable in the user's GCP project
FALLBACK_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-pro"
]

# System prompt to guide Gemini's behavior and enforce JSON schema
SYSTEM_PROMPT = """You are a highly intelligent financial assistant Telegram bot. Your primary job is to understand user messages, figure out what they want to do, and extract any relevant data.
You MUST ALWAYS respond in valid JSON format matching the schema below.

You also have access to the user's "Long-Term Memory", which contains their established preferences, budgets, and habits. Use this context to make smarter decisions about categorization, names, and intent.

User's Context/Memory:
%s

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
    if not GEMINI_API_KEY:
        # Graceful fallback: API key missing
        return {"error": "api_failed"}
        
    try:
        # Prepare the prompt with memory context
        prompt = SYSTEM_PROMPT % (context if context else "No special preferences saved yet.")
        prompt += f"\n\nUser ({user_name}): {text}\nOutput:"

        response = None
        last_error = None
        
        # Try each model in the fallback list until one works
        for model_name in FALLBACK_MODELS:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config=generation_config,
                )
                response = model.generate_content(prompt)
                break # Success!
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                # If it's a 404/Not Found or 403, we try the next model.
                if "404" in error_str or "not found" in error_str or "permission" in error_str:
                    logger.warning(f"Model {model_name} failed ({e}), trying next...")
                    continue
                else:
                    # If it's a rate limit (429) or other API issue, usually all models will fail anyway
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
