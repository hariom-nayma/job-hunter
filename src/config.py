import os
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
RESUMES_DIR = DATA_DIR / "resumes"
DB_PATH = DATA_DIR / "bot.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
RESUMES_DIR.mkdir(parents=True, exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Encryption Key for sensitive App Passwords
_raw_key = os.getenv("ENCRYPTION_KEY", "").strip()
if not _raw_key:
    # Auto-generate and cache key in file if not provided
    key_file = DATA_DIR / ".secret_key"
    if key_file.exists():
        _raw_key = key_file.read_text().strip()
    else:
        _raw_key = Fernet.generate_key().decode()
        key_file.write_text(_raw_key)

ENCRYPTION_KEY = _raw_key

admin_env = os.getenv("ADMIN_USER_ID", "").strip()
ADMIN_USER_ID = int(admin_env) if admin_env.isdigit() else None

