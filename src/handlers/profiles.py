import os
import html
from pathlib import Path
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
    get_user_profiles,
    get_profile,
    create_profile,
    update_profile,
    delete_profile
)
from src.config import RESUMES_DIR
from src.handlers.start import check_access

# Conversation states for creating profile
NEW_PROF_NAME = 10
NEW_PROF_RESUME = 11
NEW_PROF_SUBJECT = 12
NEW_PROF_BODY = 13

# States for editing
EDIT_SUBJECT = 20
EDIT_BODY = 21
EDIT_RESUME = 22

async def profiles_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return

    user = update.effective_user
    profiles = await get_user_profiles(user.id)

    text = (
        "📁 <b>JOB PROFILES MANAGEMENT</b>\n"
        "────────────────────────\n"
        "Job profiles let you organize multiple tailored resumes & custom cover letters for different job categories.\n\n"
    )

    keyboard = []
    if not profiles:
        text += "<blockquote><i>You don't have any job profiles yet. Tap below to create your first one!</i></blockquote>"
    else:
        text += f"You have <b>{len(profiles)}</b> active profile(s):\n"
        for p in profiles:
            p_name = html.escape(p['name'])
            r_name = html.escape(p['resume_file_name'])
            text += f"• <b>{p_name}</b> (<code>{r_name}</code>)\n"
            keyboard.append([
                InlineKeyboardButton(f"📂 {p['name']}", callback_data=f"view_prof_{p['id']}")
            ])

    keyboard.append([InlineKeyboardButton("➕ Add New Profile", callback_data="add_profile")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])

    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)

async def view_profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    profile_id = int(query.data.split("_")[-1])

    profile = await get_profile(profile_id, user.id)
    if not profile:
        await query.message.edit_text("⚠️ Profile not found.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Profiles", callback_data="menu_profiles")]
        ]))
        return

    safe_name = html.escape(profile['name'])
    safe_resume = html.escape(profile['resume_file_name'])
    safe_subject = html.escape(profile['subject_template'])
    body_snippet = html.escape(profile['body_template'][:300]) + ('...' if len(profile['body_template']) > 300 else '')

    text = (
        f"📂 <b>Profile: {safe_name}</b>\n"
        "────────────────────────\n"
        f"📄 <b>Attached Resume:</b> <code>{safe_resume}</code>\n"
        f"✉️ <b>Subject Template:</b>\n<code>{safe_subject}</code>\n\n"
        f"📝 <b>Email Body Preview:</b>\n"
        f"<blockquote>{body_snippet}</blockquote>"
    )

    keyboard = [
        [
            InlineKeyboardButton("📄 Download/View Resume", callback_data=f"get_resume_{profile_id}"),
            InlineKeyboardButton("📎 Replace Resume", callback_data=f"edit_resume_{profile_id}")
        ],
        [
            InlineKeyboardButton("✏️ Edit Subject", callback_data=f"edit_subj_{profile_id}"),
            InlineKeyboardButton("✏️ Edit Body", callback_data=f"edit_body_{profile_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Delete Profile", callback_data=f"del_prof_{profile_id}"),
            InlineKeyboardButton("🔙 Back to Profiles", callback_data="menu_profiles")
        ]
    ]

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def download_resume_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    profile_id = int(query.data.split("_")[-1])

    profile = await get_profile(profile_id, user.id)
    if not profile or not os.path.exists(profile["resume_file_path"]):
        await query.message.reply_text("⚠️ Resume file not found on server.")
        return

    with open(profile["resume_file_path"], "rb") as doc:
        await query.message.reply_document(
            document=doc,
            filename=profile["resume_file_name"],
            caption=f"📄 Resume for <b>{html.escape(profile['name'])}</b>",
            parse_mode=ParseMode.HTML
        )

async def delete_profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    profile_id = int(query.data.split("_")[-1])

    profile = await get_profile(profile_id, user.id)
    if profile:
        try:
            if os.path.exists(profile["resume_file_path"]):
                os.remove(profile["resume_file_path"])
        except Exception:
            pass
        await delete_profile(profile_id, user.id)

    await query.message.reply_text("🗑️ Profile deleted successfully.")
    await profiles_menu(update, context)

# --- Add Profile Conversation Flow ---

async def start_add_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_profile"] = {}

    await query.message.edit_text(
        "➕ <b>Create New Job Profile</b> (Step 1/4)\n"
        "────────────────────────\n"
        "Enter a name for this category/profile.\n\n"
        "Examples:\n"
        "• <code>Full Stack Engineer</code>\n"
        "• <code>Python Backend Specialist</code>\n"
        "• <code>Frontend React Developer</code>\n\n"
        "<i>Send /cancel anytime to abort.</i>",
        parse_mode=ParseMode.HTML
    )
    return NEW_PROF_NAME

async def handle_prof_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 60:
        await update.message.reply_text("⚠️ Please enter a name between 2 and 60 characters:")
        return NEW_PROF_NAME

    context.user_data["new_profile"]["name"] = name
    await update.message.reply_text(
        f"✅ Profile name: <b>{html.escape(name)}</b>\n"
        "────────────────────────\n"
        "📎 <b>Step 2/4: Upload your Resume</b>\n"
        "Send your resume as a <b>Document</b> (PDF or DOCX preferred).\n\n"
        "<i>Send /cancel to abort.</i>",
        parse_mode=ParseMode.HTML
    )
    return NEW_PROF_RESUME

async def handle_prof_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        await update.message.reply_text("⚠️ Please send your resume file as a Document (PDF/DOCX):")
        return NEW_PROF_RESUME

    user = update.effective_user
    user_resumes_dir = RESUMES_DIR / str(user.id)
    user_resumes_dir.mkdir(parents=True, exist_ok=True)

    clean_filename = "".join(c for c in doc.file_name if c.isalnum() or c in "._- ")
    dest_path = user_resumes_dir / f"{context.user_data['new_profile']['name'].replace(' ', '_')}_{clean_filename}"

    file_obj = await context.bot.get_file(doc.file_id)
    await file_obj.download_to_drive(dest_path)

    context.user_data["new_profile"]["resume_path"] = str(dest_path)
    context.user_data["new_profile"]["resume_name"] = clean_filename
    context.user_data["new_profile"]["resume_file_id"] = doc.file_id

    await update.message.reply_text(
        f"✅ Received resume: <code>{html.escape(clean_filename)}</code>\n"
        "────────────────────────\n"
        "✉️ <b>Step 3/4: Email Subject Line</b>\n"
        "Enter the subject line for emails sent with this profile.\n\n"
        "<b>Available tags:</b>\n"
        "• <code>{company}</code> — Recruiter's company\n"
        "• <code>{name}</code> — Recruiter's name\n"
        "• <code>{my_name}</code> — Your name\n\n"
        "Example:\n<code>Application for Software Engineer Role - {my_name}</code>\n\n"
        "<i>Send /cancel to abort.</i>",
        parse_mode=ParseMode.HTML
    )
    return NEW_PROF_SUBJECT

async def handle_prof_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = update.message.text.strip()
    if len(subject) < 3:
        await update.message.reply_text("⚠️ Subject line is too short. Please enter a valid subject:")
        return NEW_PROF_SUBJECT

    context.user_data["new_profile"]["subject"] = subject

    sample_body = (
        "Dear {name},\n\n"
        "I am writing to express my strong interest in software engineering opportunities at {company}. "
        "With hands-on experience in building scalable applications, I would love to contribute to your engineering team.\n\n"
        "Please find my resume attached for your review. I look forward to connecting with you!\n\n"
        "Best regards,\n{my_name}"
    )

    instructions = (
        f"✅ Subject saved: <code>{html.escape(subject)}</code>\n"
        "────────────────────────\n"
        "📝 <b>Step 4/4: Email Body (Cover Letter)</b>\n"
        "Enter your email body template. You can use placeholders:\n"
        "• <code>{company}</code> — Replaced with HR's company\n"
        "• <code>{name}</code> — Replaced with HR name (or 'Hiring Manager')\n"
        "• <code>{my_name}</code> — Your sender name\n\n"
        "<b>Sample template you can copy & adapt:</b>\n"
        f"<blockquote>{html.escape(sample_body)}</blockquote>\n\n"
        "<i>Send your text now or /cancel to abort.</i>"
    )

    await update.message.reply_text(instructions, parse_mode=ParseMode.HTML)
    return NEW_PROF_BODY

async def handle_prof_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
    body = update.message.text.strip()
    if len(body) < 10:
        await update.message.reply_text("⚠️ Email body is too short. Please provide a full cover letter:")
        return NEW_PROF_BODY

    p_data = context.user_data.get("new_profile", {})
    user = update.effective_user

    await create_profile(
        user_id=user.id,
        name=p_data["name"],
        resume_file_path=p_data["resume_path"],
        resume_file_name=p_data["resume_name"],
        resume_file_id=p_data["resume_file_id"],
        subject_template=p_data["subject"],
        body_template=body
    )

    context.user_data.pop("new_profile", None)

    await update.message.reply_text(
        f"🎉 <b>Profile '{html.escape(p_data['name'])}' created successfully!</b>\n"
        "You can now select this profile whenever you apply to HRs.",
        parse_mode=ParseMode.HTML
    )

    await profiles_menu(update, context)
    return ConversationHandler.END

async def cancel_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_profile", None)
    context.user_data.pop("edit_prof_id", None)
    await update.message.reply_text("Action cancelled.")
    await profiles_menu(update, context)
    return ConversationHandler.END

# --- Edit Profile Handlers ---

async def start_edit_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prof_id = int(query.data.split("_")[-1])
    context.user_data["edit_prof_id"] = prof_id

    await query.message.reply_text(
        "✏️ <b>Enter new email subject line:</b>\n"
        "────────────────────────\n"
        "Tags: <code>{company}</code>, <code>{name}</code>, <code>{my_name}</code>\n\n"
        "<i>Send /cancel to return.</i>",
        parse_mode=ParseMode.HTML
    )
    return EDIT_SUBJECT

async def save_edited_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_sub = update.message.text.strip()
    prof_id = context.user_data.get("edit_prof_id")
    user = update.effective_user

    if prof_id:
        await update_profile(profile_id=prof_id, user_id=user.id, subject_template=new_sub)
        await update.message.reply_text("✅ Subject updated successfully!")

    context.user_data.pop("edit_prof_id", None)
    await profiles_menu(update, context)
    return ConversationHandler.END

async def start_edit_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prof_id = int(query.data.split("_")[-1])
    context.user_data["edit_prof_id"] = prof_id

    await query.message.reply_text(
        "✏️ <b>Enter new email body / cover letter:</b>\n"
        "────────────────────────\n"
        "Tags: <code>{company}</code>, <code>{name}</code>, <code>{my_name}</code>\n\n"
        "<i>Send /cancel to return.</i>",
        parse_mode=ParseMode.HTML
    )
    return EDIT_BODY

async def save_edited_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_body = update.message.text.strip()
    prof_id = context.user_data.get("edit_prof_id")
    user = update.effective_user

    if prof_id:
        await update_profile(profile_id=prof_id, user_id=user.id, body_template=new_body)
        await update.message.reply_text("✅ Email body updated successfully!")

    context.user_data.pop("edit_prof_id", None)
    await profiles_menu(update, context)
    return ConversationHandler.END

async def start_edit_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prof_id = int(query.data.split("_")[-1])
    context.user_data["edit_prof_id"] = prof_id

    await query.message.reply_text(
        "📎 <b>Send the new resume document (PDF/DOCX):</b>\n\n"
        "<i>Send /cancel to return.</i>",
        parse_mode=ParseMode.HTML
    )
    return EDIT_RESUME

async def save_edited_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        await update.message.reply_text("⚠️ Please send your resume file as a Document:")
        return EDIT_RESUME

    user = update.effective_user
    prof_id = context.user_data.get("edit_prof_id")
    profile = await get_profile(prof_id, user.id)

    if profile:
        user_resumes_dir = RESUMES_DIR / str(user.id)
        user_resumes_dir.mkdir(parents=True, exist_ok=True)
        clean_filename = "".join(c for c in doc.file_name if c.isalnum() or c in "._- ")
        dest_path = user_resumes_dir / f"{profile['name'].replace(' ', '_')}_{clean_filename}"

        file_obj = await context.bot.get_file(doc.file_id)
        await file_obj.download_to_drive(dest_path)

        if profile["resume_file_path"] != str(dest_path) and os.path.exists(profile["resume_file_path"]):
            try:
                os.remove(profile["resume_file_path"])
            except Exception:
                pass

        await update_profile(
            profile_id=prof_id,
            user_id=user.id,
            resume_file_path=str(dest_path),
            resume_file_name=clean_filename,
            resume_file_id=doc.file_id
        )
        await update.message.reply_text(f"✅ Resume updated to <code>{html.escape(clean_filename)}</code>!", parse_mode=ParseMode.HTML)

    context.user_data.pop("edit_prof_id", None)
    await profiles_menu(update, context)
    return ConversationHandler.END
