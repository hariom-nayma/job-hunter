import os
import html
import asyncio
import random
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
from src.database import (
    get_user,
    get_user_profiles,
    get_profile,
    log_application,
    has_emailed_before,
    get_setting
)
from src.encryption import decrypt_secret
from src.mailer import send_email
from src.utils import EMAIL_REGEX, parse_hr_contacts, render_template, render_progress_bar
from src.handlers.start import check_access, get_main_menu_keyboard

# Conversation States
WAITING_HR_INPUT = 30
CONFIRM_SEND = 31

async def send_menu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return ConversationHandler.END

    user = update.effective_user
    db_user = await get_user(user.id)

    # Check Gmail setup
    if not db_user or not db_user.get("gmail_address") or not db_user.get("app_password_enc"):
        text = (
            "⚠️ <b>Gmail Not Configured!</b>\n"
            "────────────────────────\n"
            "You must connect your Gmail address and 16-character App Password before sending job applications."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Go to Gmail Settings", callback_data="menu_settings")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
        ])
        if update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        elif update.message:
            await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    profiles = await get_user_profiles(user.id)
    if not profiles:
        text = (
            "⚠️ <b>No Job Profiles Found!</b>\n"
            "────────────────────────\n"
            "Create at least one Job Profile (with resume & email template) before sending applications."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Job Profile", callback_data="add_profile")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
        ])
        if update.callback_query:
            await update.callback_query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        elif update.message:
            await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    keyboard = []
    for p in profiles:
        keyboard.append([
            InlineKeyboardButton(f"🎯 {p['name']} ({p['resume_file_name']})", callback_data=f"select_prof_{p['id']}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])

    text = (
        "🚀 <b>SEND JOB APPLICATIONS</b> (Step 1/2)\n"
        "────────────────────────\n"
        "Select which Job Profile & Resume to use for this campaign:"
    )
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def profile_selected_for_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    profile_id = int(query.data.split("_")[-1])

    profile = await get_profile(profile_id, user.id)
    if not profile:
        await query.message.edit_text("⚠️ Profile not found.")
        return ConversationHandler.END

    context.user_data["send_campaign"] = {
        "profile_id": profile_id,
        "profile_name": profile["name"],
        "resume_name": profile["resume_file_name"]
    }

    instructions = (
        f"🎯 <b>Selected Profile:</b> <code>{html.escape(profile['name'])}</code>\n"
        f"📄 <b>Resume Attachment:</b> <code>{html.escape(profile['resume_file_name'])}</code>\n"
        "────────────────────────\n"
        "📬 <b>Step 2/2: Provide HR Recipient List</b>\n\n"
        "You can send recipients in any of these ways:\n\n"
        "1️⃣ <b>Paste raw emails:</b>\n"
        "<code>hr@stripe.com, recruiter@google.com, talent@netflix.com</code>\n"
        "<i>(or one email per line)</i>\n\n"
        "2️⃣ <b>Paste structured CSV lines:</b>\n"
        "<code>hr@apple.com, Apple, Sarah</code>\n"
        "<code>jobs@microsoft.com, Microsoft, Hiring Team</code>\n\n"
        "3️⃣ <b>Upload a <code>.csv</code> or <code>.txt</code> file</b> directly in chat!\n\n"
        "<i>Send /cancel to abort.</i>"
    )

    await query.message.edit_text(instructions, parse_mode=ParseMode.HTML)
    return WAITING_HR_INPUT

async def handle_hr_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = ""

    if update.message.document:
        doc = update.message.document
        if not (doc.file_name.endswith(".csv") or doc.file_name.endswith(".txt")):
            await update.message.reply_text("⚠️ Please send a <code>.csv</code> or <code>.txt</code> file containing email addresses:", parse_mode=ParseMode.HTML)
            return WAITING_HR_INPUT
        file_obj = await context.bot.get_file(doc.file_id)
        file_bytes = await file_obj.download_as_bytearray()
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = file_bytes.decode("latin-1")
    elif update.message.text:
        raw_text = update.message.text
    else:
        await update.message.reply_text("⚠️ Please send text or upload a CSV/TXT file:")
        return WAITING_HR_INPUT

    contacts = parse_hr_contacts(raw_text)
    if not contacts:
        await update.message.reply_text(
            "⚠️ No valid email addresses found in your input. Please check the format and try again (or /cancel):"
        )
        return WAITING_HR_INPUT

    user = update.effective_user
    camp = context.user_data.get("send_campaign", {})
    camp["all_contacts"] = contacts

    new_contacts = []
    already_emailed = []
    for c in contacts:
        if await has_emailed_before(user.id, c["email"]):
            already_emailed.append(c)
        else:
            new_contacts.append(c)

    camp["new_contacts"] = new_contacts
    camp["already_emailed"] = already_emailed

    profile = await get_profile(camp["profile_id"], user.id)
    db_user = await get_user(user.id)
    sender_name = db_user.get("sender_name") or user.full_name
    default_delay = int(await get_setting("default_delay_seconds", "7"))
    delay = db_user.get("delay_seconds", default_delay) or default_delay

    sample_contact = contacts[0]
    sample_sub = render_template(profile["subject_template"], sample_contact, sender_name)
    sample_body = render_template(profile["body_template"], sample_contact, sender_name)

    est_minutes = round((len(contacts) * delay) / 60, 1)

    warn_block = ""
    if already_emailed:
        warn_block = f"⚠️ <b>Notice:</b> <code>{len(already_emailed)}</code> of these contacts were previously emailed!\n"

    preview_text = (
        "📋 <b>CAMPAIGN REVIEW & CONFIRMATION</b>\n"
        "────────────────────────\n"
        f"🎯 <b>Profile:</b> <code>{html.escape(camp['profile_name'])}</code>\n"
        f"📄 <b>Resume:</b> <code>{html.escape(camp['resume_name'])}</code>\n"
        f"👥 <b>Total Recipients:</b> <code>{len(contacts)}</code>\n"
        f"🆕 <b>New Contacts:</b> <code>{len(new_contacts)}</code>\n"
        f"{warn_block}"
        f"⏱️ <b>Estimated Duration:</b> <code>~{est_minutes} min</code> ({delay}s delay)\n\n"
        "🔎 <b>Sample Email (Recipient #1):</b>\n"
        f"• <b>To:</b> <code>{html.escape(sample_contact['email'])}</code>\n"
        f"• <b>Subject:</b> <code>{html.escape(sample_sub)}</code>\n"
        "• <b>Body Snippet:</b>\n"
        f"<blockquote>{html.escape(sample_body[:250])}...</blockquote>\n\n"
        "Ready to begin dispatching?"
    )

    keyboard = [
        [InlineKeyboardButton(f"🚀 Send to All ({len(contacts)})", callback_data="confirm_send_all")]
    ]
    if already_emailed and new_contacts:
        keyboard.append([
            InlineKeyboardButton(f"⏭️ Send to New Only ({len(new_contacts)})", callback_data="confirm_send_new")
        ])
    keyboard.append([InlineKeyboardButton("❌ Cancel Campaign", callback_data="cancel_send")])

    await update.message.reply_text(preview_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRM_SEND

async def confirm_send_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data
    user = update.effective_user

    if choice == "cancel_send":
        context.user_data.pop("send_campaign", None)
        await query.message.edit_text("❌ Campaign cancelled.")
        return ConversationHandler.END

    camp = context.user_data.get("send_campaign")
    if not camp:
        await query.message.edit_text("⚠️ Campaign session expired.")
        return ConversationHandler.END

    if choice == "confirm_send_new":
        recipients = camp.get("new_contacts", [])
    else:
        recipients = camp.get("all_contacts", [])

    if not recipients:
        await query.message.edit_text("⚠️ No recipients to send.")
        return ConversationHandler.END

    profile = await get_profile(camp["profile_id"], user.id)
    db_user = await get_user(user.id)
    gmail = db_user["gmail_address"]
    app_pwd = decrypt_secret(db_user["app_password_enc"])
    sender_name = db_user.get("sender_name") or user.full_name
    default_delay = int(await get_setting("default_delay_seconds", "7"))
    delay = db_user.get("delay_seconds", default_delay) or default_delay

    context.user_data.pop("send_campaign", None)

    asyncio.create_task(
        _execute_campaign_task(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            user_id=user.id,
            gmail=gmail,
            app_pwd=app_pwd,
            sender_name=sender_name,
            delay=delay,
            profile=profile,
            recipients=recipients
        )
    )

    await query.message.edit_text(
        f"🚀 <b>Campaign Started!</b>\n"
        f"Dispatching applications to <b>{len(recipients)}</b> HR contacts with rate-limiting safety.\n"
        "Live progress will update below.",
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END

async def _execute_campaign_task(bot, chat_id, user_id, gmail, app_pwd, sender_name, delay, profile, recipients):
    total = len(recipients)
    sent_count = 0
    fail_count = 0
    failed_details = []

    progress_msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            "📨 <b>Starting Delivery...</b>\n"
            "────────────────────────\n"
            f"<code>{render_progress_bar(0, total)}</code>\n"
            f"• <b>Sent:</b> 0/{total}\n"
            f"• <b>Failed:</b> 0"
        ),
        parse_mode=ParseMode.HTML
    )

    last_update_time = asyncio.get_event_loop().time()

    for idx, contact in enumerate(recipients, start=1):
        to_email = contact["email"]
        company = contact.get("company", "")
        hr_name = contact.get("hr_name", "")

        rendered_sub = render_template(profile["subject_template"], contact, sender_name)
        rendered_body = render_template(profile["body_template"], contact, sender_name)

        success, err = await send_email(
            from_address=gmail,
            app_password=app_pwd,
            sender_name=sender_name,
            to_address=to_email,
            subject=rendered_sub,
            body=rendered_body,
            resume_path=profile["resume_file_path"],
            resume_display_name=profile["resume_file_name"]
        )

        if success:
            sent_count += 1
            await log_application(
                user_id=user_id,
                profile_id=profile["id"],
                recipient_email=to_email,
                company_name=company,
                hr_name=hr_name,
                subject=rendered_sub,
                status="SENT"
            )
        else:
            fail_count += 1
            failed_details.append(f"<code>{html.escape(to_email)}</code>: {html.escape(err or '')}")
            await log_application(
                user_id=user_id,
                profile_id=profile["id"],
                recipient_email=to_email,
                company_name=company,
                hr_name=hr_name,
                subject=rendered_sub,
                status="FAILED",
                error_message=err
            )

        now = asyncio.get_event_loop().time()
        if (now - last_update_time > 3.0) or (idx == total):
            last_update_time = now
            try:
                progress_text = (
                    f"📨 <b>Applying via Profile:</b> <code>{html.escape(profile['name'])}</code>\n"
                    "────────────────────────\n"
                    f"<code>{render_progress_bar(idx, total)}</code>\n"
                    f"• <b>Processed:</b> <code>{idx}/{total}</code>\n"
                    f"• ✅ <b>Sent:</b> <code>{sent_count}</code>\n"
                    f"• ❌ <b>Failed:</b> <code>{fail_count}</code>\n"
                    f"• <b>Current:</b> <code>{html.escape(to_email)}</code>"
                )
                await progress_msg.edit_text(progress_text, parse_mode=ParseMode.HTML)
            except Exception:
                pass

        if idx < total:
            jitter = random.uniform(0.5, 2.0)
            await asyncio.sleep(max(1, delay + jitter))

    summary = (
        "🎉 <b>CAMPAIGN COMPLETE!</b>\n"
        "────────────────────────\n"
        f"🎯 <b>Profile:</b> <code>{html.escape(profile['name'])}</code>\n"
        "📊 <b>Summary:</b>\n"
        f"• Total Processed: <b>{total}</b>\n"
        f"• ✅ Successfully Sent: <b>{sent_count}</b>\n"
        f"• ❌ Failed: <b>{fail_count}</b>\n"
    )

    if failed_details:
        summary += "\n⚠️ <b>Failed Recipients:</b>\n" + "\n".join(failed_details[:10])
        if len(failed_details) > 10:
            summary += f"\n<i>...and {len(failed_details) - 10} more.</i>"

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 View Application History", callback_data="menu_history")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
    ])

    await bot.send_message(chat_id=chat_id, text=summary, reply_markup=markup, parse_mode=ParseMode.HTML)

async def cancel_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("send_campaign", None)
    await update.message.reply_text("Campaign cancelled.")
    return ConversationHandler.END

# --- Quick Drop Email Handlers ---

async def handle_quick_drop_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    if not EMAIL_REGEX.search(text):
        return

    if not await check_access(update):
        return

    user = update.effective_user
    contacts = parse_hr_contacts(text)
    if not contacts:
        return

    db_user = await get_user(user.id)
    if not db_user or not db_user.get("gmail_address") or not db_user.get("app_password_enc"):
        await update.message.reply_text(
            "📬 <b>Email detected!</b> But your Gmail settings aren't configured yet.\n\n"
            "Please configure your Gmail & App Password first to enable 1-tap applications.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Setup Gmail Now", callback_data="menu_settings")]
            ]),
            parse_mode=ParseMode.HTML
        )
        return

    profiles = await get_user_profiles(user.id)
    if not profiles:
        await update.message.reply_text(
            "📬 <b>Email detected!</b> But you haven't created any Job Profiles yet.\n\n"
            "Create a profile with your resume and cover letter to apply with one tap.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Create Job Profile", callback_data="add_profile")]
            ]),
            parse_mode=ParseMode.HTML
        )
        return

    dup_count = 0
    for c in contacts:
        if await has_emailed_before(user.id, c["email"]):
            dup_count += 1

    context.user_data["quick_contacts"] = contacts

    if len(contacts) == 1:
        c = contacts[0]
        meta = []
        if c.get("company"):
            meta.append(f"Company: <b>{html.escape(c['company'])}</b>")
        if c.get("hr_name"):
            meta.append(f"HR: <b>{html.escape(c['hr_name'])}</b>")
        meta_str = f" ({', '.join(meta)})" if meta else ""

        warn = "<blockquote>⚠️ <b>Notice:</b> You already applied to this email before!</blockquote>\n\n" if dup_count > 0 else ""
        msg_text = (
            "📬 <b>HR Contact Detected</b>\n"
            "────────────────────────\n"
            f"• <b>Email:</b> <code>{html.escape(c['email'])}</code>{meta_str}\n\n"
            f"{warn}"
            "⚡ <b>Select a profile below to send your application instantly:</b>"
        )
    else:
        warn = f"<blockquote>⚠️ <b>Notice:</b> {dup_count} contact(s) were previously emailed.</blockquote>\n\n" if dup_count > 0 else ""
        list_str = "\n".join(f"• <code>{html.escape(c['email'])}</code>" + (f" ({html.escape(c['company'])})" if c.get('company') else "") for c in contacts[:5])
        if len(contacts) > 5:
            list_str += f"\n<i>...and {len(contacts) - 5} more.</i>"

        msg_text = (
            f"📬 <b>Found {len(contacts)} HR Contacts</b>\n"
            "────────────────────────\n"
            f"{list_str}\n\n"
            f"{warn}"
            f"⚡ <b>Select a profile to send to all {len(contacts)} contacts:</b>"
        )

    keyboard = []
    for p in profiles:
        keyboard.append([
            InlineKeyboardButton(f"🚀 Send with {p['name']}", callback_data=f"quick_apply_{p['id']}")
        ])
    keyboard.append([
        InlineKeyboardButton("❌ Dismiss", callback_data="quick_dismiss")
    ])

    await update.message.reply_text(
        msg_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

async def handle_quick_drop_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        return
    doc = update.message.document
    if not (doc.file_name.endswith(".csv") or doc.file_name.endswith(".txt")):
        return

    if not await check_access(update):
        return

    user = update.effective_user
    file_obj = await context.bot.get_file(doc.file_id)
    file_bytes = await file_obj.download_as_bytearray()
    try:
        raw_text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw_text = file_bytes.decode("latin-1")

    contacts = parse_hr_contacts(raw_text)
    if not contacts:
        return

    db_user = await get_user(user.id)
    if not db_user or not db_user.get("gmail_address") or not db_user.get("app_password_enc"):
        await update.message.reply_text(
            f"📁 Found <b>{len(contacts)}</b> contacts in <code>{html.escape(doc.file_name)}</code>, but Gmail isn't configured yet.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Setup Gmail", callback_data="menu_settings")]]),
            parse_mode=ParseMode.HTML
        )
        return

    profiles = await get_user_profiles(user.id)
    if not profiles:
        await update.message.reply_text(
            f"📁 Found <b>{len(contacts)}</b> contacts in <code>{html.escape(doc.file_name)}</code>, but you have no job profiles.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Create Profile", callback_data="add_profile")]]),
            parse_mode=ParseMode.HTML
        )
        return

    context.user_data["quick_contacts"] = contacts
    keyboard = []
    for p in profiles:
        keyboard.append([
            InlineKeyboardButton(f"🚀 Send with {p['name']}", callback_data=f"quick_apply_{p['id']}")
        ])
    keyboard.append([InlineKeyboardButton("❌ Dismiss", callback_data="quick_dismiss")])

    await update.message.reply_text(
        f"📁 <b>File Uploaded:</b> <code>{html.escape(doc.file_name)}</code>\n"
        "────────────────────────\n"
        f"👥 <b>Found {len(contacts)} recipient(s)</b>\n\n"
        "⚡ <b>Select a profile below to send your application:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

async def quick_apply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    profile_id = int(query.data.split("_")[-1])

    contacts = context.user_data.get("quick_contacts")
    if not contacts:
        await query.message.edit_text("⚠️ Contacts session expired. Please drop the email again.")
        return

    profile = await get_profile(profile_id, user.id)
    if not profile:
        await query.message.edit_text("⚠️ Profile not found.")
        return

    db_user = await get_user(user.id)
    gmail = db_user["gmail_address"]
    app_pwd = decrypt_secret(db_user["app_password_enc"])
    sender_name = db_user.get("sender_name") or user.full_name
    default_delay = int(await get_setting("default_delay_seconds", "7"))
    delay = db_user.get("delay_seconds", default_delay) or default_delay

    context.user_data.pop("quick_contacts", None)

    asyncio.create_task(
        _execute_campaign_task(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            user_id=user.id,
            gmail=gmail,
            app_pwd=app_pwd,
            sender_name=sender_name,
            delay=delay,
            profile=profile,
            recipients=contacts
        )
    )

    await query.message.edit_text(
        f"🚀 <b>Quick Apply Started!</b>\n"
        f"Sending to <b>{len(contacts)}</b> contact(s) using profile <b>{html.escape(profile['name'])}</b> (<code>{html.escape(profile['resume_file_name'])}</code>).\n"
        "Live progress will update below.",
        parse_mode=ParseMode.HTML
    )

async def quick_dismiss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Dismissed")
    context.user_data.pop("quick_contacts", None)
    await query.message.delete()
