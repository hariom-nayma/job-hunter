import os
import sys
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters
)
from src.config import TELEGRAM_BOT_TOKEN
from src.database import init_db
from src.handlers.start import start_command, menu_callback, show_help
from src.handlers.settings import (
    settings_menu,
    prompt_set_gmail,
    save_gmail,
    prompt_set_password,
    save_password,
    prompt_set_sender_name,
    save_sender_name,
    prompt_set_delay,
    save_delay,
    cancel_settings,
    test_smtp_callback,
    WAITING_EMAIL,
    WAITING_PASSWORD,
    WAITING_SENDER_NAME,
    WAITING_DELAY
)
from src.handlers.profiles import (
    profiles_menu,
    view_profile_handler,
    download_resume_handler,
    delete_profile_handler,
    start_add_profile,
    handle_prof_name,
    handle_prof_resume,
    handle_prof_subject,
    handle_prof_body,
    cancel_profile,
    start_edit_subject,
    save_edited_subject,
    start_edit_body,
    save_edited_body,
    start_edit_resume,
    save_edited_resume,
    NEW_PROF_NAME,
    NEW_PROF_RESUME,
    NEW_PROF_SUBJECT,
    NEW_PROF_BODY,
    EDIT_SUBJECT,
    EDIT_BODY,
    EDIT_RESUME
)
from src.handlers.send import (
    send_menu_start,
    profile_selected_for_send,
    handle_hr_input,
    confirm_send_callback,
    cancel_send,
    handle_quick_drop_text,
    handle_quick_drop_doc,
    quick_apply_callback,
    quick_dismiss_callback,
    WAITING_HR_INPUT,
    CONFIRM_SEND
)
from src.handlers.history import history_menu, export_history_csv_callback
from src.handlers.admin import (
    admin_panel_menu,
    toggle_mode_callback,
    list_allowed_users_menu,
    prompt_remove_user_menu,
    execute_remove_user_callback,
    prompt_add_user,
    save_add_user,
    prompt_set_delay,
    save_set_delay,
    prompt_broadcast,
    execute_broadcast,
    cancel_admin,
    ADMIN_ADD_USER,
    ADMIN_SET_DELAY,
    ADMIN_BROADCAST
)

import warnings
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("MailSenderBot")

async def post_init(application: Application):
    """Initializes the database and verifies bot credentials on startup."""
    logger.info("Initializing SQLite database...")
    await init_db()
    logger.info("Database initialized successfully.")
    
    # Ensure bot user is authenticated and cached
    bot_info = await application.bot.get_me()
    logger.info(f"Authenticated as @{bot_info.username} (ID: {bot_info.id})")
    print("\n=======================================================")
    print(f"  🤖 MailSenderBot is ONLINE!")
    print(f"  👉 Username: @{bot_info.username}")
    print(f"  👉 Status: Ready to receive commands")
    print("=======================================================\n")

def build_application():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set! Please set it in your .env file.")
        print("\n❌ ERROR: TELEGRAM_BOT_TOKEN is not set in .env!")
        print("Please edit .env and provide your bot token from @BotFather.\n")
        sys.exit(1)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # --- Conversation Handler: Settings ---
    settings_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_set_gmail, pattern="^set_gmail$"),
            CallbackQueryHandler(prompt_set_password, pattern="^set_app_pwd$"),
            CallbackQueryHandler(prompt_set_sender_name, pattern="^set_sender_name$"),
            CallbackQueryHandler(prompt_set_delay, pattern="^set_delay$"),
        ],
        states={
            WAITING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_gmail)],
            WAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_password)],
            WAITING_SENDER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_sender_name)],
            WAITING_DELAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_delay)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_settings),
            CallbackQueryHandler(cancel_settings, pattern="^cancel_settings$")
        ],
        per_user=True,
        per_chat=True
    )

    # --- Conversation Handler: Add Profile ---
    add_profile_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_profile, pattern="^add_profile$")
        ],
        states={
            NEW_PROF_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prof_name)],
            NEW_PROF_RESUME: [MessageHandler(filters.Document.ALL, handle_prof_resume)],
            NEW_PROF_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prof_subject)],
            NEW_PROF_BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prof_body)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_profile)
        ],
        per_user=True,
        per_chat=True
    )

    # --- Conversation Handler: Edit Profile Fields ---
    edit_profile_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_edit_subject, pattern=r"^edit_subj_\d+$"),
            CallbackQueryHandler(start_edit_body, pattern=r"^edit_body_\d+$"),
            CallbackQueryHandler(start_edit_resume, pattern=r"^edit_resume_\d+$"),
        ],
        states={
            EDIT_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_subject)],
            EDIT_BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_body)],
            EDIT_RESUME: [MessageHandler(filters.Document.ALL, save_edited_resume)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_profile)
        ],
        per_user=True,
        per_chat=True
    )

    # --- Conversation Handler: Send Campaign ---
    send_campaign_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(profile_selected_for_send, pattern=r"^select_prof_\d+$")
        ],
        states={
            WAITING_HR_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_hr_input),
                MessageHandler(filters.Document.ALL, handle_hr_input),
            ],
            CONFIRM_SEND: [
                CallbackQueryHandler(confirm_send_callback, pattern=r"^(confirm_send_all|confirm_send_new|cancel_send)$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_send),
            CallbackQueryHandler(confirm_send_callback, pattern="^cancel_send$")
        ],
        per_user=True,
        per_chat=True
    )

    # --- Conversation Handler: Admin Panel ---
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_add_user, pattern="^admin_prompt_add_user$"),
            CallbackQueryHandler(prompt_set_delay, pattern="^admin_prompt_delay$"),
            CallbackQueryHandler(prompt_broadcast, pattern="^admin_prompt_broadcast$"),
        ],
        states={
            ADMIN_ADD_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_add_user)],
            ADMIN_SET_DELAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_set_delay)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, execute_broadcast)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_admin)
        ],
        per_user=True,
        per_chat=True
    )

    # Register conversations
    app.add_handler(settings_conv)
    app.add_handler(add_profile_conv)
    app.add_handler(edit_profile_conv)
    app.add_handler(send_campaign_conv)
    app.add_handler(admin_conv)

    # Base commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CommandHandler("admin", admin_panel_menu))
    app.add_handler(CommandHandler("profiles", profiles_menu))
    app.add_handler(CommandHandler("settings", settings_menu))
    app.add_handler(CommandHandler("send", send_menu_start))
    app.add_handler(CommandHandler("history", history_menu))

    # Base menu callbacks
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^(main_menu|menu_help)$"))
    app.add_handler(CallbackQueryHandler(profiles_menu, pattern="^menu_profiles$"))
    app.add_handler(CallbackQueryHandler(settings_menu, pattern="^menu_settings$"))
    app.add_handler(CallbackQueryHandler(send_menu_start, pattern="^menu_send$"))
    app.add_handler(CallbackQueryHandler(history_menu, pattern="^menu_history$"))

    # Admin callbacks
    app.add_handler(CallbackQueryHandler(admin_panel_menu, pattern="^menu_admin$"))
    app.add_handler(CallbackQueryHandler(toggle_mode_callback, pattern="^admin_toggle_mode$"))
    app.add_handler(CallbackQueryHandler(list_allowed_users_menu, pattern="^admin_list_users$"))
    app.add_handler(CallbackQueryHandler(prompt_remove_user_menu, pattern="^admin_prompt_remove_user$"))
    app.add_handler(CallbackQueryHandler(execute_remove_user_callback, pattern=r"^admin_del_user_\d+$"))

    # Profile actions
    app.add_handler(CallbackQueryHandler(view_profile_handler, pattern=r"^view_prof_\d+$"))
    app.add_handler(CallbackQueryHandler(download_resume_handler, pattern=r"^get_resume_\d+$"))
    app.add_handler(CallbackQueryHandler(delete_profile_handler, pattern=r"^del_prof_\d+$"))

    # Settings actions
    app.add_handler(CallbackQueryHandler(test_smtp_callback, pattern="^test_smtp$"))

    # History actions
    app.add_handler(CallbackQueryHandler(export_history_csv_callback, pattern="^export_history_csv$"))

    # Quick Apply actions
    app.add_handler(CallbackQueryHandler(quick_apply_callback, pattern=r"^quick_apply_\d+$"))
    app.add_handler(CallbackQueryHandler(quick_dismiss_callback, pattern="^quick_dismiss$"))

    # Catch-all text & documents dropped outside conversation (Quick Email Drop)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quick_drop_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_quick_drop_doc))

    return app

def main():
    app = build_application()
    print("🤖 MailSenderBot is starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
