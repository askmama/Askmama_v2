# AskMama Bot - Architecture

## System Flow

```
User sends voice → Telegram Bot → Gemini Transcription → Gemini Parser → Google Sheets
                        ↓               ↓                      ↓               ↓
                   Downloads audio  Returns text       {item, qty, action}  Update Inventory
                   (temp_audio.ogg)                                         + Transaction Log
```

## Example Flow

```
1. User: 🎤 "Used two bottles of developer 20vol"

2. Telegram Bot:
   - Receives voice message
   - Downloads audio file (temp_audio.ogg)

3. Audio Transcriber (audio_transcriber.py):
   - Sends audio to Google Gemini API (gemini-2.5-flash)
   - Returns: "Used two bottles of developer 20vol"

4. Command Parser (bot.py → parse_command()):
   - Sends transcript to Gemini with structured prompt
   - Returns JSON: {"item": "developer 20vol", "quantity": 2, "action": "taken"}

5. Sheets Logger (sheets_logger.py → update_inventory()):
   - Searches "Inventory" tab for "developer 20vol" (partial match)
   - Item found → decrements stock: 8 → 6, status: OK
   - Appends row to "Transaction Log" tab

   Item NOT found → Bot sends inline keyboard to user:
   [✅ Add 'item' as new item]  [❌ Cancel]
   - ✅ → append_new_item() adds row to Inventory + Transaction Log
   - ❌ → no changes made

6. Bot replies with full summary:
   ✅ Developer 20vol
   Change: -2
   New stock: 6
   Status: OK
   Updated: 2026-03-26 14:30:00
```

## Components

### bot.py
- Telegram bot entry point
- Handles voice/audio messages
- Calls transcriber → parser → sheets logger
- Inline keyboard flow for unknown items
- Returns full item summary to user

### audio_transcriber.py
- Uploads audio to Gemini Files API
- Transcribes using `gemini-2.5-flash`
- Returns plain text transcription

### sheets_logger.py
- `find_item(name)` — partial-match search in Inventory tab (starts row 4)
- `update_inventory(...)` — updates qty, status, last_updated; appends log row
- `append_new_item(...)` — adds new item row + log row

### inventory_uploader.py
- One-time migration script
- Reads `stocksense_inventory.xlsx`
- Uploads "Inventory" and "Transaction Log" sheets to Google Sheets

## File Dependencies

```
bot.py
├── audio_transcriber.py
│   └── google-genai (package)
├── sheets_logger.py
│   ├── gspread (package)
│   └── google-auth (package)
└── google-genai (package)  ← also used for command parsing

inventory_uploader.py (run once)
├── openpyxl (package)
├── gspread (package)
└── google-auth (package)
```

## Google Sheet Structure

### Inventory tab
| A: Item ID | B: Item Name | C | D: Qty | E: Min Qty | F | G | H: Status | I: Last Updated |
|------------|-------------|---|--------|------------|---|---|-----------|-----------------|
| (rows 1–3 are headers) |
| INV-001 | Developer 20vol | | 6 | 2 | | | OK | 26 Mar 2026 |

Status values: `OK` / `LOW STOCK` / `MISSING`

### Transaction Log tab
| A: Datetime | B: Item ID | C: Item Name | D: Action | E: Qty | F: Raw Command | G: New Qty |
|-------------|------------|--------------|-----------|--------|----------------|------------|
| 26 Mar 2026 14:30 | INV-001 | Developer 20vol | TAKEN | 2 | Used two bottles... | 6 |

## Environment Variables

| Variable | Purpose | Where to get it |
|----------|---------|-----------------|
| TELEGRAM_BOT_TOKEN | Bot authentication | @BotFather on Telegram |
| GEMINI_API_KEY | Transcription + parsing | aistudio.google.com |
| GOOGLE_SHEET_NAME | Target spreadsheet name | Your Google Sheet |
| GOOGLE_CREDENTIALS_FILE | Service account key path | Google Cloud Console |

## Setup Order

1. `pip install -r requirements.txt`
2. `python inventory_uploader.py` — upload Excel data to Google Sheets (run once)
3. `python bot.py` — start the bot

## Error Handling

- Network/API failures: caught per-component, error message sent back to user
- Unknown item: inline keyboard confirmation before any write
- Bad transcription / unparseable command: bot replies asking user to try again
