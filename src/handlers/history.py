import io
import csv
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from src.database import get_user_stats, get_user_applications
from src.handlers.start import check_access

async def history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    user = update.effective_user
    stats = await get_user_stats(user.id)
    recent_apps = await get_user_applications(user.id, limit=8)

    text = (
        "📊 <b>APPLICATION HISTORY & STATS</b>\n"
        "────────────────────────\n"
        f"• <b>Total Applications:</b> <code>{stats['total']}</code>\n"
        f"• ✅ <b>Successfully Sent:</b> <code>{stats['sent']}</code>\n"
        f"• ❌ <b>Failed:</b> <code>{stats['failed']}</code>\n\n"
    )

    if not recent_apps:
        text += "<blockquote><i>No applications recorded yet. Start applying using 'Send Applications' or by dropping an email in chat!</i></blockquote>"
    else:
        text += "<b>Recent Dispatches:</b>\n"
        for a in recent_apps:
            icon = "✅" if a["status"] == "SENT" else "❌"
            company_str = f" ({html.escape(a['company_name'])})" if a.get("company_name") else ""
            prof_str = f" [<b>{html.escape(a['profile_name'] or '')}</b>]" if a.get("profile_name") else ""
            date_str = a["sent_at"][:16] if a.get("sent_at") else ""
            text += f"{icon} <code>{html.escape(a['recipient_email'])}</code>{company_str}{prof_str}\n<i>{date_str}</i>\n"

    keyboard = []
    if stats["total"] > 0:
        keyboard.append([InlineKeyboardButton("📥 Export Full History (CSV)", callback_data="export_history_csv")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])

    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)

async def export_history_csv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    all_apps = await get_user_applications(user.id, limit=2000)
    if not all_apps:
        await query.message.reply_text("No applications to export.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Recipient Email", "Company", "HR Name", "Profile", "Subject", "Status", "Error Message", "Date (UTC)"])

    for a in all_apps:
        writer.writerow([
            a.get("recipient_email", ""),
            a.get("company_name", ""),
            a.get("hr_name", ""),
            a.get("profile_name", ""),
            a.get("subject", ""),
            a.get("status", ""),
            a.get("error_message", ""),
            a.get("sent_at", "")
        ])

    csv_bytes = io.BytesIO(output.getvalue().encode("utf-8"))
    csv_bytes.name = f"job_applications_{user.id}.csv"

    await query.message.reply_document(
        document=csv_bytes,
        filename="job_applications_export.csv",
        caption="📄 <b>Here is your complete job applications export.</b>",
        parse_mode=ParseMode.HTML
    )
