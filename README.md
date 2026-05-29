# AskMama MVP - Telegram Audio Transcription Bot

A Telegram bot that receives audio messages, transcribes them using OpenAI Whisper, and logs the transcriptions to Google Sheets.

## Features

- 🎙️ Receives voice messages and audio files
- 📝 Transcribes audio using Google Gemini API
- 📊 Logs transcriptions to Google Sheets with timestamps
- 🔄 Parses transcription to extract items and quantities

## Setup Instructions

### 1. Prerequisites

- Python 3.8 or higher
- Telegram account
- Google Gemini API account
- Google Cloud account

### 2. Create a Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow the instructions to name your bot
4. Copy the bot token provided

### 3. Get Google Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the API key

### 4. Set Up Google Sheets

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Google Sheets API and Google Drive API
4. Create a service account:
   - Go to IAM & Admin > Service Accounts
   - Click "Create Service Account"
   - Grant it "Editor" role
   - Create a JSON key and download it
5. Rename the downloaded file to `credentials.json` and place it in the project directory
6. Create a new Google Sheet for logging
7. Share the Google Sheet with the service account email (found in credentials.json)

### 5. Install Dependencies

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 6. Configure Environment Variables

```bash
# Copy the example .env file
cp .env.example .env

# Edit .env file with your credentials
# Add your:
# - TELEGRAM_BOT_TOKEN
# - GEMINI_API_KEY
# - GOOGLE_SHEET_NAME
```

### 7. Load Environment Variables

```bash
# Install python-dotenv if not already installed
pip install python-dotenv

# Or manually export variables:
export TELEGRAM_BOT_TOKEN=your_token_here
export GEMINI_API_KEY=your_key_here
export GOOGLE_SHEET_NAME=your_sheet_name_here
```

### 8. Run the Bot

```bash
python bot.py
```

## Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to begin
3. Send a voice message or audio file
4. The bot will:
   - Transcribe the audio
   - Parse the transcription (e.g., "I wanna take 1 erhu string" → "Erhu string -1")
   - Log it to Google Sheets with a timestamp

## Example

**Audio message:** "I wanna take 1 erhu string"

**Google Sheet entry:**
```
| Timestamp           | Entry          |
|---------------------|----------------|
| 2026-03-10 14:30:00 | Erhu string -1 |
```

## File Structure

```
AskMama_MVP/
├── bot.py                  # Main bot logic
├── audio_transcriber.py    # Audio transcription module
├── sheets_logger.py        # Google Sheets integration
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── .env                   # Your actual credentials (not in git)
├── credentials.json       # Google service account key (not in git)
└── README.md             # This file
```

## Security Notes

- Never commit `.env` or `credentials.json` to version control
- Keep your API keys and tokens secure
- Regularly rotate your credentials
- Use environment variables for sensitive data

## Troubleshooting

### Bot doesn't respond
- Check if the bot is running
- Verify TELEGRAM_BOT_TOKEN is correct
- Check internet connection

### Transcription fails
- Verify GEMINI_API_KEY is valid
- Check if you have API quota available
- Ensure audio file format is supported (most formats work with Gemini)

### Google Sheets logging fails
- Verify credentials.json is in the correct location
- Check if the sheet is shared with the service account email
- Ensure GOOGLE_SHEET_NAME matches exactly

## Customization

### Modify parsing logic

Edit the `parse_transcription()` function in `bot.py` to customize how transcriptions are parsed and formatted.

### Change transcription language

Edit `audio_transcriber.py` and change the `language` parameter in the transcription call.

### Add more columns to Google Sheets

Modify the `log_to_sheet()` function in `sheets_logger.py` to add additional data fields.

## License

MIT License
