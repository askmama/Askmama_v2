# Quick Start Guide

## Fast Setup (5 minutes)

### 1. Install dependencies
```bash
pip install -r requirements.txt
pip install python-dotenv
```

### 2. Set up credentials

Create a `.env` file with:
```
TELEGRAM_BOT_TOKEN=your_bot_token
GEMINI_API_KEY=your_gemini_key
GOOGLE_SHEET_NAME=your_sheet_name
```

### 3. Add Google credentials

Place your `credentials.json` file in the project directory.

### 4. Run the bot
```bash
python run.py
```

## Getting Your Credentials

### Telegram Bot Token
1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot`
3. Follow instructions
4. Copy the token

### Gemini API Key
1. Visit https://aistudio.google.com/app/apikey
2. Create API key
3. Copy it

### Google Sheets
1. Visit https://console.cloud.google.com/
2. Create project → Enable Google Sheets API
3. Create Service Account → Download JSON key
4. Save as `credentials.json`
5. Create a Google Sheet
6. Share it with the service account email

Done! 🎉
