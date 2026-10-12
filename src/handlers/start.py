import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from src.database import get_user, upsert_user, is_user_authorized
from src.config import ADMIN_USER_ID

def get_main_menu_keyboard(is_admin: bool = False):
    keyboard = [
        [
            InlineKeyboardButton("📁 Job Profiles", callback_data="menu_profiles"),
            InlineKeyboardButton("🚀 Send Applications", callback_data="menu_send")
        ],
        [
            InlineKeyboardButton("⚙️ Gmail Settings", callback_data="menu_settings"),
            InlineKeyboardButton("📊 History & Stats", callback_data="menu_history")
        ]
    ]

    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin")])

    keyboard.append([InlineKeyboardButton("❓ Help & Setup Guide", callback_data="menu_help")])
    return InlineKeyboardMarkup(keyboard)

async def check_access(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False

    authorized = await is_user_authorized(user.id, ADMIN_USER_ID)
    if not authorized:
        msg = (
            "⛔ <b>Access Restricted</b>\n"
            "────────────────────────\n"
            "This bot is currently operating in <b>Private Whitelist Mode</b>.\n\n"
            f"Your Telegram ID: <code>{user.id}</code>\n\n"
            "<blockquote>Please send your ID to the administrator to request access.</blockquote>"
        )
        if update.callback_query:
            await update.callback_query.answer("Access Restricted", show_alert=True)
            await update.callback_query.message.reply_text(msg, parse_mode=ParseMode.HTML)
        elif update.message:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return False
    return True

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return
    
    user = update.effective_user
    is_admin = bool(ADMIN_USER_ID and user.id == ADMIN_USER_ID)

    db_user = await get_user(user.id)
    if not db_user:
        await upsert_user(user.id, sender_name=user.full_name)

    safe_name = html.escape(user.first_name)
    welcome_text = (
        "💼 <b>M A I L  S E N D E R  B O T</b>\n"
        "────────────────────────\n"
        f"👋 Welcome, <b>{safe_name}</b>!\n\n"
        "<blockquote>Automate personalized job applications to recruiters directly from Telegram with tailored resumes & safe email delivery.</blockquote>\n\n"
        "<b>Core Capabilities:</b>\n"
        "• 📁 <b>Job Profiles</b> — Store multiple resumes & cover letter templates\n"
        "• ⚡ <b>Quick Apply</b> — Drop any HR email in chat to apply with 1-tap\n"
        "• 🚀 <b>Bulk Dispatch</b> — Paste recruiter lists or upload CSV sheets\n"
        "• 🛡️ <b>Anti-Spam Shield</b> — Humanized delays & duplicate warnings\n"
        "• 📊 <b>Tracking</b> — Real-time delivery tracking & CSV export\n\n"
        "👇 <i>Choose an action below to get started:</i>"
    )

    markup = get_main_menu_keyboard(is_admin=is_admin)
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=markup, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.message.edit_text(welcome_text, reply_markup=markup, parse_mode=ParseMode.HTML)

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "main_menu":
        await start_command(update, context)
    elif query.data == "menu_help":
        await show_help(update, context)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "💡 <b>Setup & User Guide</b>\n"
        "────────────────────────\n\n"
        "1️⃣ <b>Step 1: Configure Gmail SMTP</b>\n"
        "<blockquote>• Go to Google Account ➔ <b>Security</b> ➔ <b>2-Step Verification</b>\n"
        "• Scroll to the bottom and select <b>App passwords</b>\n"
        "• Create a new password named <i>MailSenderBot</i>\n"
        "• Copy the 16 characters and enter them in <b>⚙️ Gmail Settings</b></blockquote>\n\n"
        "2️⃣ <b>Step 2: Create a Job Profile</b>\n"
        "<blockquote>• Open <b>📁 Job Profiles</b> ➔ <b>➕ Add New Profile</b>\n"
        "• Upload your resume document (PDF or DOCX)\n"
        "• Write your subject and cover letter template</blockquote>\n\n"
        "3️⃣ <b>Supported Dynamic Placeholders:</b>\n"
        "• <code>{company}</code> — Recruiter's company (e.g. Google, Apple)\n"
        "• <code>{name}</code> — Recruiter's name (or 'Hiring Manager')\n"
        "• <code>{my_name}</code> — Your sender name\n"
        "• <code>{email}</code> — Recruiter's email address\n\n"
        "4️⃣ <b>Step 3: Sending Applications</b>\n"
        "• <b>Quick Drop:</b> Simply paste an email in chat (e.g. <code>recruiter@google.com</code>)!\n"
        "• <b>Bulk:</b> Click <b>🚀 Send Applications</b> to send to an entire list."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Configure Gmail Now", callback_data="menu_settings")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
    ])
    if update.callback_query:
        await update.callback_query.message.edit_text(help_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_text(help_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
