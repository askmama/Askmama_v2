#!/usr/bin/env python3
"""
Run the Telegram bot with environment variables loaded from .env file
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import and run the bot
from bot import main

if __name__ == '__main__':
    main()
