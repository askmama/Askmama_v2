"""
AskMama Telegram Bot
Voice/audio or text → Gemini parsing → Google Sheets update
"""
import os
import json
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from audio_transcriber import transcribe_audio
from sheets_logger import update_inventory, append_new_item, find_item
from google import genai

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Callback data keys
CB_ADD_NEW = "add_new"
CB_CANCEL  = "cancel"


# ── GEMINI COMMAND PARSER ─────────────────────────────────

def _safe_parse(raw):
    """Strip markdown fences and parse JSON from Gemini output."""
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()
    match = re.search(r'\{.*?\}', text, re.DOTALL)
    if match:
        text = match.group()
    text = text.replace("'", '"')
    text = re.sub(r',\s*}', '}', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_command(transcript_text):
    """
    Use Gemini to extract {item, quantity, action} from a transcript.
    Returns parsed dict or None.
    """
    client = genai.Client()
    prompt = f"""You are an inventory tracking assistant for a small business.

Extract exactly three things from voice commands:
- item: name of the item (string)
- quantity: how many taken or added (integer)
- action: either exactly "taken" or exactly "added"

Rules:
- Respond with JSON and nothing else
- No markdown, no backticks, no explanation whatsoever
- If quantity unclear use 1
- If item unclear use "unknown"
- If action unclear use "taken"
- "used", "took", "grabbed", "removed", "ran out" = taken
- "added", "delivery", "restocked", "put back", "got" = added

Your entire response must be exactly this format with no other text:
{{"item": "name here", "quantity": 1, "action": "taken"}}

Voice command: {transcript_text}"""

    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=prompt
    )
    parsed = _safe_parse(response.text)
    if parsed:
        parsed.setdefault("item", "unknown")
        parsed.setdefault("quantity", 1)
        parsed.setdefault("action", "taken")
        try:
            parsed["quantity"] = int(parsed["quantity"])
        except (ValueError, TypeError):
            parsed["quantity"] = 1
        parsed["action"] = str(parsed["action"]).lower()
        if parsed["action"] not in ("taken", "added"):
            parsed["action"] = "taken"
    return parsed


# ── REPLY FORMATTER ───────────────────────────────────────

def format_summary(result):
    status_emoji = {"OK": "✅", "LOW STOCK": "⚠️", "MISSING": "🚨"}.get(result['status'], "📦")
    action_sign = "-" if result['action'] == "taken" else "+"
    return (
        f"{status_emoji} *{result['name']}*\n"
        f"Change: {action_sign}{result['quantity']}\n"
        f"New stock: {result['new_qty']}\n"
        f"Status: {result['status']}\n"
        f"Updated: {result['timestamp']}"
    )


# ── HANDLERS ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '👋 Welcome to AskMama Bot!\n\n'
        '🎙️ Send a voice message *or* type a message and I will:\n'
        '1. Parse the inventory command\n'
        '2. Update your Google Sheet\n\n'
        '📋 Commands:\n'
        '/start - Start the bot\n'
        '/help  - Show help\n\n'
        '💡 Examples:\n'
        '• Voice: "Used 2 bottles of developer 20vol"\n'
        '• Text: "Added 5 boxes of latex gloves"',
        parse_mode='Markdown'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Send a *voice message* or *text* describing an inventory action.\n\n'
        'Examples:\n'
        '• "Used two bottles of developer 20vol"\n'
        '• "Restocked 5 boxes of latex gloves"\n'
        '• "Grabbed one pack of foil sheets"\n\n'
        'I will update the Inventory sheet and reply with a summary.',
        parse_mode='Markdown'
    )


async def _process_command(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Parse an inventory command string and update the sheet."""
    parsed = parse_command(text)
    if not parsed or parsed.get('item') == 'unknown':
        await update.message.reply_text(
            "❓ Could not identify an item or action. Please try again."
        )
        return

    item_name = parsed['item']
    quantity  = parsed['quantity']
    action    = parsed['action']

    result = update_inventory(item_name, quantity, action, text)

    if result:
        await update.message.reply_text(format_summary(result), parse_mode='Markdown')
    else:
        context.user_data['pending'] = {
            'item': item_name,
            'quantity': quantity,
            'action': action,
            'raw': text,
        }
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"✅ Add '{item_name}' as new item",
                callback_data=CB_ADD_NEW
            ),
            InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL),
        ]])
        await update.message.reply_text(
            f"⚠️ *'{item_name}'* not found in inventory.\n"
            f"Action: {action} × {quantity}\n\n"
            "What would you like to do?",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive plain text, parse as inventory command, update sheet."""
    text = update.message.text.strip()
    logger.info(f"Text command: {text}")
    await update.message.reply_text(f'📝 Got: _{text}_', parse_mode='Markdown')
    try:
        await _process_command(update, context, text)
    except Exception as e:
        logger.error(f"Error handling text: {e}", exc_info=True)
        await update.message.reply_text(f'❌ Error: {str(e)}')


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive voice/audio, transcribe, parse, update sheet."""
    audio_path = 'temp_audio.ogg'
    try:
        if update.message.voice:
            audio_file = await update.message.voice.get_file()
        elif update.message.audio:
            audio_file = await update.message.audio.get_file()
        else:
            return

        await audio_file.download_to_drive(audio_path)
        await update.message.reply_text('🎤 Transcribing...')

        transcription = transcribe_audio(audio_path)
        logger.info(f"Transcription: {transcription}")

        await update.message.reply_text(f'📝 Heard: _{transcription}_', parse_mode='Markdown')
        await _process_command(update, context, transcription)

    except Exception as e:
        logger.error(f"Error handling audio: {e}", exc_info=True)
        await update.message.reply_text(f'❌ Error: {str(e)}')
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses for new-item confirmation."""
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get('pending')
    if not pending:
        await query.edit_message_text("⏱️ Session expired. Please send the voice message again.")
        return

    if query.data == CB_ADD_NEW:
        try:
            result = append_new_item(
                item_name=pending['item'],
                quantity=pending['quantity'],
                action=pending['action'],
                raw_command=pending['raw'],
            )
            await query.edit_message_text(
                f"➕ New item added!\n\n{format_summary(result)}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error appending new item: {e}", exc_info=True)
            await query.edit_message_text(f'❌ Failed to add item: {str(e)}')

    elif query.data == CB_CANCEL:
        await query.edit_message_text("🚫 Cancelled. No changes made.")

    context.user_data.pop('pending', None)


# ── MAIN ──────────────────────────────────────────────────

def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
