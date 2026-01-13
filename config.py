# config.py - Store your configuration here
import os
from dotenv import load_dotenv

load_dotenv()  # Loads variables from .env file

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')  # You'll add this later