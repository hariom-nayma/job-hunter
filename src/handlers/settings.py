import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CommandHandler
)
from src.database import get_user, upsert_user, get_setting
from src.encryption import encrypt_secret, decrypt_secret
from src.mailer import verify_smtp_credentials, send_email
from src.utils import is_valid_email
from src.handlers.start import check_access

# Conversation States
WAITING_EMAIL = 1
WAITING_PASSWORD = 2
WAITING_SENDER_NAME = 3
WAITING_DELAY = 4

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return ConversationHandler.END

    user = update.effective_user
    db_user = await get_user(user.id)

    default_delay = int(await get_setting("default_delay_seconds", "7"))
    gmail = db_user.get("gmail_address") if db_user else None
    has_pwd = bool(db_user.get("app_password_enc")) if db_user else False
    sender_name = (db_user.get("sender_name") or user.full_name) if db_user else user.full_name
    delay = db_user.get("delay_seconds", default_delay) if db_user else default_delay

    gmail_display = f"<code>{html.escape(gmail)}</code>" if gmail else "<i>Not set</i>"
    pwd_display = "✅ <code>Configured & Encrypted</code>" if has_pwd else "❌ <i>Not set</i>"
    name_display = f"<b>{html.escape(sender_name)}</b>" if sender_name else "<i>Not set</i>"
    delay_display = f"<code>{delay} seconds</code>"

    text = (
        "⚙️ <b>GMAIL & SMTP SETTINGS</b>\n"
        "────────────────────────\n"
        f"📧 <b>Gmail Address:</b> {gmail_display}\n"
        f"🔑 <b>App Password:</b> {pwd_display}\n"
        f"👤 <b>Sender Name:</b> {name_display}\n"
        f"⏱️ <b>Delivery Delay:</b> {delay_display}\n\n"
        "<blockquote>💡 <b>Note:</b> You need a 16-character Google App Password (not your normal Gmail login password) to allow sending via SMTP.</blockquote>"
    )

    keyboard = [
        [
            InlineKeyboardButton("📧 Set Gmail Address", callback_data="set_gmail"),
            InlineKeyboardButton("🔑 Set App Password", callback_data="set_app_pwd")
        ],
        [
            InlineKeyboardButton("👤 Set Sender Name", callback_data="set_sender_name"),
            InlineKeyboardButton("⏱️ Change Delay", callback_data="set_delay")
        ],
        [
            InlineKeyboardButton("🧪 Send Test Email", callback_data="test_smtp")
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")
        ]
    ]

    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)

async def prompt_set_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "📧 <b>Enter your Gmail Address:</b>\n"
        "────────────────────────\n"
        "Example: <code>myname@gmail.com</code>\n\n"
        "<i>Send /cancel to return to settings.</i>",
        parse_mode=ParseMode.HTML
    )
    return WAITING_EMAIL

async def save_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip().lower()
    if not is_valid_email(email) or not email.endswith("@gmail.com"):
        await update.message.reply_text(
            "⚠️ <b>Invalid Gmail address.</b>\n"
            "Please provide a valid address ending in <code>@gmail.com</code> (or send /cancel):",
            parse_mode=ParseMode.HTML
        )
        return WAITING_EMAIL

    user = update.effective_user
    await upsert_user(user.id, gmail_address=email)
    await update.message.reply_text(f"✅ Gmail address saved as <code>{html.escape(email)}</code>!", parse_mode=ParseMode.HTML)
    await settings_menu(update, context)
    return ConversationHandler.END

async def prompt_set_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "🔑 <b>Enter your 16-character Google App Password:</b>\n"
        "────────────────────────\n"
        "1. Open your Google Account ➔ <b>Security</b>\n"
        "2. Ensure <b>2-Step Verification</b> is ON\n"
        "3. Search & open <b>App passwords</b>\n"
        "4. Create a password named <code>MailSenderBot</code>\n"
        "5. Paste the 16 characters here (spaces are removed automatically)\n\n"
        "<blockquote>🔒 Your password will be encrypted in the database using Fernet cipher.</blockquote>\n\n"
        "<i>Send /cancel to return.</i>",
        parse_mode=ParseMode.HTML
    )
    return WAITING_PASSWORD

async def save_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_pwd = update.message.text.strip()
    clean_pwd = raw_pwd.replace(" ", "")

    if len(clean_pwd) != 16:
        await update.message.reply_text(
            "⚠️ <b>Invalid Length!</b>\n"
            "Google App Passwords are exactly 16 characters long. Please check and try again (or /cancel):",
            parse_mode=ParseMode.HTML
        )
        return WAITING_PASSWORD

    user = update.effective_user
    db_user = await get_user(user.id)
    gmail = db_user.get("gmail_address") if db_user else None

    if gmail:
        status_msg = await update.message.reply_text("🔄 Verifying credentials with Google SMTP servers...")
        success, err = await verify_smtp_credentials(gmail, clean_pwd)
        if not success:
            await status_msg.edit_text(
                "❌ <b>Authentication Failed!</b>\n"
                "────────────────────────\n"
                f"<blockquote>{html.escape(err or '')}</blockquote>\n\n"
                "Please verify your Gmail address and 16-character App Password, then send it again (or /cancel).",
                parse_mode=ParseMode.HTML
            )
            return WAITING_PASSWORD
        await status_msg.edit_text("✅ <b>Authentication Successful!</b>", parse_mode=ParseMode.HTML)

    encrypted_pwd = encrypt_secret(clean_pwd)
    await upsert_user(user.id, app_password_enc=encrypted_pwd)

    try:
        await update.message.delete()
    except Exception:
        pass

    await update.message.reply_text("🔒 <b>App Password encrypted & stored securely!</b>", parse_mode=ParseMode.HTML)
    await settings_menu(update, context)
    return ConversationHandler.END

async def prompt_set_sender_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "👤 <b>Enter your Sender Display Name:</b>\n"
        "────────────────────────\n"
        "This is the name HR will see in their inbox 'From' field.\n\n"
        "Example: <code>Gaurav Sharma</code>\n\n"
        "<i>Send /cancel to return.</i>",
        parse_mode=ParseMode.HTML
    )
    return WAITING_SENDER_NAME

async def save_sender_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    user = update.effective_user
    await upsert_user(user.id, sender_name=name)
    await update.message.reply_text(f"✅ Sender name updated to <b>{html.escape(name)}</b>!", parse_mode=ParseMode.HTML)
    await settings_menu(update, context)
    return ConversationHandler.END

async def prompt_set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "⏱️ <b>Enter delay between emails (in seconds):</b>\n"
        "────────────────────────\n"
        "Recommended: <b>5 to 15 seconds</b>\n"
        "<blockquote>A steady delay protects your Gmail account reputation and keeps deliverability healthy.</blockquote>\n\n"
        "<i>Send /cancel to return.</i>",
        parse_mode=ParseMode.HTML
    )
    return WAITING_DELAY

async def save_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1 or int(text) > 120:
        await update.message.reply_text("⚠️ Please enter a number between 1 and 120 seconds (or /cancel):")
        return WAITING_DELAY

    delay = int(text)
    user = update.effective_user
    await upsert_user(user.id, delay_seconds=delay)
    await update.message.reply_text(f"✅ Delay updated to <code>{delay} seconds</code>!", parse_mode=ParseMode.HTML)
    await settings_menu(update, context)
    return ConversationHandler.END

async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    await settings_menu(update, context)
    return ConversationHandler.END

async def test_smtp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    db_user = await get_user(user.id)

    if not db_user or not db_user.get("gmail_address") or not db_user.get("app_password_enc"):
        await query.message.reply_text(
            "⚠️ Please configure both your <b>Gmail Address</b> and <b>App Password</b> before testing.",
            parse_mode=ParseMode.HTML
        )
        return

    gmail = db_user["gmail_address"]
    app_pwd = decrypt_secret(db_user["app_password_enc"])
    sender_name = db_user.get("sender_name") or user.full_name

    status_msg = await query.message.reply_text(f"🔄 Sending test email to <code>{html.escape(gmail)}</code>...", parse_mode=ParseMode.HTML)

    success, err = await send_email(
        from_address=gmail,
        app_password=app_pwd,
        sender_name=sender_name,
        to_address=gmail,
        subject="🚀 Test Email from MailSenderBot",
        body=(
            f"Hello {sender_name},\n\n"
            "This is a confirmation that your Gmail SMTP configuration in MailSenderBot is working properly!\n\n"
            "You are ready to create job profiles and apply to HRs.\n\n"
            "Best regards,\nMailSenderBot"
        )
    )

    if success:
        await status_msg.edit_text(
            f"🎉 <b>Success!</b> Test email delivered to <code>{html.escape(gmail)}</code>.\n"
            "Check your inbox to confirm.",
            parse_mode=ParseMode.HTML
        )
    else:
        await status_msg.edit_text(
            f"❌ <b>Failed to send test email:</b>\n\n<code>{html.escape(err or '')}</code>",
            parse_mode=ParseMode.HTML
        )
