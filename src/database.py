import aiosqlite
from typing import Optional, List, Dict, Any
from src.config import DB_PATH

async def init_db():
    """Initializes the database schema."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                gmail_address TEXT,
                app_password_enc TEXT,
                sender_name TEXT,
                delay_seconds INTEGER DEFAULT 7,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                resume_file_path TEXT NOT NULL,
                resume_file_name TEXT NOT NULL,
                resume_file_id TEXT,
                subject_template TEXT NOT NULL,
                body_template TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                profile_id INTEGER,
                recipient_email TEXT NOT NULL,
                company_name TEXT,
                hr_name TEXT,
                subject TEXT,
                status TEXT NOT NULL, -- 'SENT' or 'FAILED'
                error_message TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS allowed_users (
                telegram_id INTEGER PRIMARY KEY,
                notes TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Initialize defaults if not present
        await db.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('access_mode', 'whitelist')")
        await db.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('default_delay_seconds', '7')")

        await db.commit()

async def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def upsert_user(
    telegram_id: int,
    gmail_address: Optional[str] = None,
    app_password_enc: Optional[str] = None,
    sender_name: Optional[str] = None,
    delay_seconds: Optional[int] = None
):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            existing = await cursor.fetchone()

        if existing:
            gmail = gmail_address if gmail_address is not None else existing["gmail_address"]
            pwd = app_password_enc if app_password_enc is not None else existing["app_password_enc"]
            name = sender_name if sender_name is not None else existing["sender_name"]
            delay = delay_seconds if delay_seconds is not None else existing["delay_seconds"]
            await db.execute("""
                UPDATE users
                SET gmail_address = ?, app_password_enc = ?, sender_name = ?, delay_seconds = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
            """, (gmail, pwd, name, delay, telegram_id))
        else:
            default_delay = int(await get_setting("default_delay_seconds", "7"))
            await db.execute("""
                INSERT INTO users (telegram_id, gmail_address, app_password_enc, sender_name, delay_seconds)
                VALUES (?, ?, ?, ?, ?)
            """, (telegram_id, gmail_address or "", app_password_enc or "", sender_name or "", delay_seconds or default_delay))
        await db.commit()

async def create_profile(
    user_id: int,
    name: str,
    resume_file_path: str,
    resume_file_name: str,
    resume_file_id: str,
    subject_template: str,
    body_template: str
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO profiles (user_id, name, resume_file_path, resume_file_name, resume_file_id, subject_template, body_template)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, name, resume_file_path, resume_file_name, resume_file_id, subject_template, body_template))
        await db.commit()
        return cursor.lastrowid

async def get_user_profiles(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM profiles WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_profile(profile_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM profiles WHERE id = ? AND user_id = ?", (profile_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_profile(
    profile_id: int,
    user_id: int,
    name: Optional[str] = None,
    resume_file_path: Optional[str] = None,
    resume_file_name: Optional[str] = None,
    resume_file_id: Optional[str] = None,
    subject_template: Optional[str] = None,
    body_template: Optional[str] = None
):
    profile = await get_profile(profile_id, user_id)
    if not profile:
        return
    n = name if name is not None else profile["name"]
    rfp = resume_file_path if resume_file_path is not None else profile["resume_file_path"]
    rfn = resume_file_name if resume_file_name is not None else profile["resume_file_name"]
    rfi = resume_file_id if resume_file_id is not None else profile["resume_file_id"]
    sub = subject_template if subject_template is not None else profile["subject_template"]
    bod = body_template if body_template is not None else profile["body_template"]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE profiles
            SET name = ?, resume_file_path = ?, resume_file_name = ?, resume_file_id = ?, subject_template = ?, body_template = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        """, (n, rfp, rfn, rfi, sub, bod, profile_id, user_id))
        await db.commit()

async def delete_profile(profile_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM profiles WHERE id = ? AND user_id = ?", (profile_id, user_id))
        await db.commit()

async def log_application(
    user_id: int,
    profile_id: Optional[int],
    recipient_email: str,
    company_name: Optional[str],
    hr_name: Optional[str],
    subject: str,
    status: str,
    error_message: Optional[str] = None
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO applications (user_id, profile_id, recipient_email, company_name, hr_name, subject, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, profile_id, recipient_email, company_name, hr_name, subject, status, error_message))
        await db.commit()

async def get_user_stats(user_id: int) -> Dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'SENT' THEN 1 ELSE 0 END) as sent,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
            FROM applications
            WHERE user_id = ?
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
            return {
                "total": row[0] or 0,
                "sent": row[1] or 0,
                "failed": row[2] or 0
            }

async def get_user_applications(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT a.*, p.name as profile_name
            FROM applications a
            LEFT JOIN profiles p ON a.profile_id = p.id
            WHERE a.user_id = ?
            ORDER BY a.sent_at DESC
            LIMIT ?
        """, (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def has_emailed_before(user_id: int, recipient_email: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT 1 FROM applications
            WHERE user_id = ? AND LOWER(recipient_email) = LOWER(?) AND status = 'SENT'
            LIMIT 1
        """, (user_id, recipient_email.strip())) as cursor:
            return (await cursor.fetchone()) is not None

# --- Admin & System Settings ---

async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM system_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO system_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()

async def is_user_authorized(telegram_id: int, admin_id: Optional[int]) -> bool:
    """Checks if a user is authorized to interact with the bot."""
    # Admin is always authorized
    if admin_id and telegram_id == admin_id:
        return True

    # Check access mode
    access_mode = await get_setting("access_mode", "whitelist" if admin_id else "public")
    if access_mode == "public":
        return True

    # If whitelist, check allowed_users table
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM allowed_users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            return (await cursor.fetchone()) is not None

async def add_allowed_user(telegram_id: int, notes: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO allowed_users (telegram_id, notes)
            VALUES (?, ?)
        """, (telegram_id, notes))
        await db.commit()

async def remove_allowed_user(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM allowed_users WHERE telegram_id = ?", (telegram_id,))
        await db.commit()

async def get_allowed_users() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM allowed_users ORDER BY added_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_global_stats() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1:
            total_users = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM profiles") as c2:
            total_profiles = (await c2.fetchone())[0]
        async with db.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'SENT' THEN 1 ELSE 0 END) as sent,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
            FROM applications
        """) as c3:
            row = await c3.fetchone()
            total_apps = row[0] or 0
            sent_apps = row[1] or 0
            failed_apps = row[2] or 0

        return {
            "total_users": total_users,
            "total_profiles": total_profiles,
            "total_applications": total_apps,
            "sent_applications": sent_apps,
            "failed_applications": failed_apps
        }

async def get_all_registered_users() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT telegram_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

