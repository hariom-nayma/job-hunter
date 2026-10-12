import html
import asyncio
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
from src.config import ADMIN_USER_ID
from src.database import (
    get_setting,
    set_setting,
    get_allowed_users,
    add_allowed_user,
    remove_allowed_user,
    get_global_stats,
    get_all_registered_users
)

# Conversation states for admin
ADMIN_ADD_USER = 50
ADMIN_SET_DELAY = 51
ADMIN_BROADCAST = 52

def is_admin(user_id: int) -> bool:
    return bool(ADMIN_USER_ID and user_id == ADMIN_USER_ID)

async def admin_panel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        if update.callback_query:
            await update.callback_query.answer("⛔ Admin access only.", show_alert=True)
        elif update.message:
            await update.message.reply_text("⛔ Admin access only.")
        return ConversationHandler.END

    access_mode = await get_setting("access_mode", "whitelist")
    delay = await get_setting("default_delay_seconds", "7")
    allowed_users = await get_allowed_users()
    stats = await get_global_stats()

    mode_display = "🔒 <b>Whitelist (Private)</b>" if access_mode == "whitelist" else "🌐 <b>Public (Open)</b>"
    toggle_text = "Switch to Public 🌐" if access_mode == "whitelist" else "Switch to Whitelist 🔒"

    text = (
        "👑 <b>ADMIN CONTROL PANEL</b>\n"
        "────────────────────────\n"
        f"• <b>Access Policy:</b> {mode_display}\n"
        f"• <b>Default Delay:</b> <code>{delay}s</code>\n"
        f"• <b>Whitelisted Users:</b> <code>{len(allowed_users)}</code>\n\n"
        "📊 <b>Platform-Wide Analytics:</b>\n"
        f"• Registered Users: <b>{stats['total_users']}</b>\n"
        f"• Active Job Profiles: <b>{stats['total_profiles']}</b>\n"
        f"• Emails Dispatched: <b>{stats['sent_applications']}</b>\n"
        f"• Dispatches Failed: <b>{stats['failed_applications']}</b>\n"
    )

    keyboard = [
        [
            InlineKeyboardButton(f"🔄 {toggle_text}", callback_data="admin_toggle_mode")
        ],
        [
            InlineKeyboardButton(f"👥 Manage Allowed Users ({len(allowed_users)})", callback_data="admin_list_users"),
            InlineKeyboardButton("⏱️ Change Delay", callback_data="admin_prompt_delay")
        ],
        [
            InlineKeyboardButton("📢 Broadcast Announcement", callback_data="admin_prompt_broadcast")
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
    return ConversationHandler.END

async def toggle_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not is_admin(user.id):
        return

    current = await get_setting("access_mode", "whitelist")
    new_mode = "public" if current == "whitelist" else "whitelist"
    await set_setting("access_mode", new_mode)

    await admin_panel_menu(update, context)

async def list_allowed_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not is_admin(user.id):
        return

    allowed = await get_allowed_users()
    text = (
        "👥 <b>WHITELISTED TELEGRAM USERS</b>\n"
        "────────────────────────\n"
    )

    if not allowed:
        text += "<blockquote><i>No users added yet. Only you (the Admin) currently have access.</i></blockquote>\n"
    else:
        for idx, u in enumerate(allowed, 1):
            notes_str = f" ({html.escape(u['notes'])})" if u.get("notes") else ""
            date_str = u["added_at"][:10] if u.get("added_at") else ""
            text += f"{idx}. <code>{u['telegram_id']}</code>{notes_str} — <i>{date_str}</i>\n"

    keyboard = [
        [InlineKeyboardButton("➕ Add User ID", callback_data="admin_prompt_add_user")]
    ]

    if allowed:
        keyboard.append([InlineKeyboardButton("➖ Remove a User", callback_data="admin_prompt_remove_user")])

    keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="menu_admin")])

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def prompt_remove_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not is_admin(user.id):
        return

    allowed = await get_allowed_users()
    keyboard = []
    for u in allowed:
        name = f"ID: {u['telegram_id']}" + (f" ({u['notes']})" if u.get('notes') else '')
        keyboard.append([
            InlineKeyboardButton(f"❌ Remove {name}", callback_data=f"admin_del_user_{u['telegram_id']}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_list_users")])

    await query.message.edit_text("Select a user to revoke access:", reply_markup=InlineKeyboardMarkup(keyboard))

async def execute_remove_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    if not is_admin(user.id):
        return

    target_id = int(query.data.split("_")[-1])
    await remove_allowed_user(target_id)
    await query.message.reply_text(f"✅ User <code>{target_id}</code> removed from whitelist.", parse_mode=ParseMode.HTML)
    await list_allowed_users_menu(update, context)

# --- Add User Conversation ---

async def prompt_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    await query.message.edit_text(
        "➕ <b>Enter Telegram User ID to Whitelist:</b>\n"
        "────────────────────────\n"
        "Format: <code>123456789</code> or <code>123456789 Name/Note</code>\n\n"
        "<i>Send /cancel to return.</i>",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_ADD_USER

async def save_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    raw_id = parts[0]
    notes = parts[1] if len(parts) > 1 else ""

    if not raw_id.isdigit():
        await update.message.reply_text("⚠️ Invalid ID. Telegram IDs are numeric. Try again or /cancel:")
        return ADMIN_ADD_USER

    target_id = int(raw_id)
    await add_allowed_user(target_id, notes=notes)

    note_str = f" (Note: {html.escape(notes)})" if notes else ""
    await update.message.reply_text(
        f"✅ User <code>{target_id}</code> has been granted access!{note_str}",
        parse_mode=ParseMode.HTML
    )
    await admin_panel_menu(update, context)
    return ConversationHandler.END

# --- Set Delay Conversation ---

async def prompt_set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    await query.message.edit_text(
        "⏱️ <b>Enter default email delay in seconds (1 - 60):</b>\n"
        "────────────────────────\n"
        "This sets the default safe delivery interval between emails across the bot.\n\n"
        "<i>Send /cancel to return.</i>",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_SET_DELAY

async def save_set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1 or int(text) > 60:
        await update.message.reply_text("⚠️ Please enter a number between 1 and 60 seconds (or /cancel):")
        return ADMIN_SET_DELAY

    delay_val = text
    await set_setting("default_delay_seconds", delay_val)

    await update.message.reply_text(f"✅ Default email delay updated to <code>{delay_val} seconds</code>!", parse_mode=ParseMode.HTML)
    await admin_panel_menu(update, context)
    return ConversationHandler.END

# --- Broadcast Conversation ---

async def prompt_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    all_users = await get_all_registered_users()
    await query.message.edit_text(
        "📢 <b>Broadcast Announcement</b>\n"
        "────────────────────────\n"
        f"This announcement will be delivered to all <b>{len(all_users)}</b> registered users.\n\n"
        "Send your message text now (or /cancel to abort):",
        parse_mode=ParseMode.HTML
    )
    return ADMIN_BROADCAST

async def execute_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text
    all_users = await get_all_registered_users()
    status_msg = await update.message.reply_text(f"🚀 Broadcasting to {len(all_users)} users...")

    sent_count = 0
    broadcast_body = (
        "📢 <b>Announcement from Administrator</b>\n"
        "────────────────────────\n"
        f"{html.escape(msg_text)}"
    )

    for uid in all_users:
        try:
            await context.bot.send_message(chat_id=uid, text=broadcast_body, parse_mode=ParseMode.HTML)
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await status_msg.edit_text(f"✅ Broadcast complete! Delivered to <b>{sent_count}/{len(all_users)}</b> users.", parse_mode=ParseMode.HTML)
    await admin_panel_menu(update, context)
    return ConversationHandler.END

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    await admin_panel_menu(update, context)
    return ConversationHandler.END
