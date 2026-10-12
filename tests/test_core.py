import os
import asyncio
import unittest
from pathlib import Path

# Adjust path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import parse_hr_contacts, render_template, render_progress_bar
from src.encryption import encrypt_secret, decrypt_secret
from src.database import (
    init_db,
    upsert_user,
    get_user,
    create_profile,
    get_user_profiles,
    get_profile,
    log_application,
    has_emailed_before,
    get_user_stats
)

import src.database as db_module

TEST_DB_PATH = Path("/tmp/test_bot_runner.db")
db_module.DB_PATH = TEST_DB_PATH

class TestMailSenderBot(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        await init_db()

    async def asyncTearDown(self):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def test_hr_parsing_formats(self):
        # 1. Plain comma separated
        text1 = "hr1@google.com, hr2@apple.com, hr3@meta.com"
        contacts1 = parse_hr_contacts(text1)
        self.assertEqual(len(contacts1), 3)
        self.assertEqual(contacts1[0]["email"], "hr1@google.com")

        # 2. Newline separated with duplicates
        text2 = "hr1@google.com\nhr2@apple.com\nhr1@google.com"
        contacts2 = parse_hr_contacts(text2)
        self.assertEqual(len(contacts2), 2)

        # 3. CSV format: email, company, hr_name
        text3 = "recruiter@netflix.com, Netflix, Jessica\ntalent@uber.com, Uber"
        contacts3 = parse_hr_contacts(text3)
        self.assertEqual(len(contacts3), 2)
        self.assertEqual(contacts3[0]["email"], "recruiter@netflix.com")
        self.assertEqual(contacts3[0]["company"], "Netflix")
        self.assertEqual(contacts3[0]["hr_name"], "Jessica")
        self.assertEqual(contacts3[1]["company"], "Uber")

        # 4. Quick dropped single email with company
        text4 = "hiring@openai.com, OpenAI"
        contacts4 = parse_hr_contacts(text4)
        self.assertEqual(len(contacts4), 1)
        self.assertEqual(contacts4[0]["email"], "hiring@openai.com")
        self.assertEqual(contacts4[0]["company"], "OpenAI")

    def test_template_rendering(self):
        contact = {"email": "alex@amazon.com", "company": "Amazon", "hr_name": "Alex"}
        template_sub = "Job Application for {company} - {my_name}"
        template_body = "Hi {name}, I'm applying to {company} at {email}."

        rendered_sub = render_template(template_sub, contact, sender_name="Gaurav")
        rendered_body = render_template(template_body, contact, sender_name="Gaurav")

        self.assertEqual(rendered_sub, "Job Application for Amazon - Gaurav")
        self.assertEqual(rendered_body, "Hi Alex, I'm applying to Amazon at alex@amazon.com.")

        # Default fallback test
        contact_empty = {"email": "blank@test.com", "company": "", "hr_name": ""}
        rendered_empty = render_template("Dear {name} at {company}", contact_empty, sender_name="Gaurav")
        self.assertEqual(rendered_empty, "Dear Hiring Manager at your company")

    def test_encryption(self):
        secret = "abcd efgh ijkl mnop"
        encrypted = encrypt_secret(secret)
        self.assertNotEqual(secret, encrypted)
        decrypted = decrypt_secret(encrypted)
        self.assertEqual(secret, decrypted)

    def test_progress_bar(self):
        bar0 = render_progress_bar(0, 10, length=10)
        bar5 = render_progress_bar(5, 10, length=10)
        bar10 = render_progress_bar(10, 10, length=10)
        self.assertIn("0%", bar0)
        self.assertIn("50%", bar5)
        self.assertIn("100%", bar10)

    async def test_database_operations(self):
        await init_db()
        test_uid = 99999999

        # User upsert
        await upsert_user(test_uid, gmail_address="test@gmail.com", sender_name="Test User", delay_seconds=5)
        u = await get_user(test_uid)
        self.assertIsNotNone(u)
        self.assertEqual(u["gmail_address"], "test@gmail.com")
        self.assertEqual(u["sender_name"], "Test User")

        # Profile creation
        prof_id = await create_profile(
            user_id=test_uid,
            name="Backend Engineer",
            resume_file_path="/tmp/test_resume.pdf",
            resume_file_name="test_resume.pdf",
            resume_file_id="tg_123",
            subject_template="Subject for {company}",
            body_template="Body for {company}"
        )
        profiles = await get_user_profiles(test_uid)
        self.assertGreaterEqual(len(profiles), 1)

        profile = await get_profile(prof_id, test_uid)
        self.assertEqual(profile["name"], "Backend Engineer")

        # Application logging
        await log_application(
            user_id=test_uid,
            profile_id=prof_id,
            recipient_email="hr@startup.io",
            company_name="Startup",
            hr_name="CEO",
            subject="Application",
            status="SENT"
        )

        has_sent = await has_emailed_before(test_uid, "hr@startup.io")
        self.assertTrue(has_sent)

        has_not_sent = await has_emailed_before(test_uid, "other@startup.io")
        self.assertFalse(has_not_sent)

        stats = await get_user_stats(test_uid)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["sent"], 1)

    async def test_multi_user_isolation(self):
        user_a = 11111111
        user_b = 22222222

        await upsert_user(user_a, gmail_address="usera@gmail.com")
        await upsert_user(user_b, gmail_address="userb@gmail.com")

        # Create profile for user_a
        p_a = await create_profile(
            user_id=user_a,
            name="Profile A",
            resume_file_path="/tmp/a.pdf",
            resume_file_name="a.pdf",
            resume_file_id="id_a",
            subject_template="Sub A",
            body_template="Body A"
        )

        profiles_a = await get_user_profiles(user_a)
        profiles_b = await get_user_profiles(user_b)

        self.assertEqual(len(profiles_a), 1)
        self.assertEqual(len(profiles_b), 0)

        # Profile A should not be retrievable by user_b
        p_wrong = await get_profile(p_a, user_b)
        self.assertIsNone(p_wrong)

    async def test_admin_and_authorization(self):
        from src.database import (
            is_user_authorized,
            add_allowed_user,
            remove_allowed_user,
            get_allowed_users,
            set_setting,
            get_setting
        )
        admin_id = 999
        normal_user = 123
        other_user = 456

        # In whitelist mode
        await set_setting("access_mode", "whitelist")

        # Admin is always authorized
        self.assertTrue(await is_user_authorized(admin_id, admin_id))

        # Normal user is not yet authorized
        self.assertFalse(await is_user_authorized(normal_user, admin_id))

        # Add normal user to allowed list
        await add_allowed_user(normal_user, notes="Test colleague")
        self.assertTrue(await is_user_authorized(normal_user, admin_id))

        allowed_list = await get_allowed_users()
        self.assertEqual(len(allowed_list), 1)
        self.assertEqual(allowed_list[0]["telegram_id"], normal_user)

        # Remove normal user
        await remove_allowed_user(normal_user)
        self.assertFalse(await is_user_authorized(normal_user, admin_id))

        # Switch to public mode
        await set_setting("access_mode", "public")
        self.assertTrue(await is_user_authorized(other_user, admin_id))

        # Setting delay
        await set_setting("default_delay_seconds", "12")
        val = await get_setting("default_delay_seconds")
        self.assertEqual(val, "12")

if __name__ == "__main__":
    unittest.main()
