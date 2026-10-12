import re
import csv
import io
from typing import List, Dict, Any

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

def is_valid_email(email: str) -> bool:
    return bool(EMAIL_REGEX.fullmatch(email.strip()))

def parse_hr_contacts(raw_input: str) -> List[Dict[str, str]]:
    """
    Parses HR contacts from raw text, comma-separated lists, or CSV format.
    Handles:
    - Pure emails: "hr1@comp.com, hr2@comp.com" or newline-separated
    - CSV format: "email, company, hr_name" or "email, company"
    """
    results = []
    seen = set()

    # Try parsing line-by-line
    lines = [line.strip() for line in raw_input.strip().splitlines() if line.strip()]

    for line in lines:
        # Check if line contains comma / tab / semicolon separation
        delimiter = None
        for d in [",", "\t", ";"]:
            if d in line:
                delimiter = d
                break

        if delimiter:
            try:
                reader = csv.reader(io.StringIO(line), delimiter=delimiter)
                row = next(reader)
                row = [col.strip() for col in row]
                
                # Check how many columns match an email
                email_cols = [idx for idx, col in enumerate(row) if EMAIL_REGEX.search(col)]
                
                if len(email_cols) > 1:
                    # Multiple emails on one line separated by comma/semicolon
                    for idx in email_cols:
                        match = EMAIL_REGEX.search(row[idx])
                        email = match.group(0).lower() if match else ""
                        if email and email not in seen:
                            seen.add(email)
                            results.append({
                                "email": email,
                                "company": "",
                                "hr_name": ""
                            })
                    continue
                elif len(email_cols) == 1:
                    # Structured CSV record: email + company + hr_name
                    email_idx = email_cols[0]
                    match = EMAIL_REGEX.search(row[email_idx])
                    email = match.group(0).lower() if match else ""
                    if email and email not in seen:
                        seen.add(email)
                        other_cols = [col for idx, col in enumerate(row) if idx != email_idx and col]
                        company = other_cols[0] if len(other_cols) >= 1 else ""
                        hr_name = other_cols[1] if len(other_cols) >= 2 else ""
                        results.append({
                            "email": email,
                            "company": company,
                            "hr_name": hr_name
                        })
                    continue
            except Exception:
                pass

        # If not structured CSV, extract all emails found in the line
        found_emails = EMAIL_REGEX.findall(line)
        for e in found_emails:
            clean_e = e.lower()
            if clean_e not in seen:
                seen.add(clean_e)
                results.append({
                    "email": clean_e,
                    "company": "",
                    "hr_name": ""
                })

    return results

def render_template(template: str, contact: Dict[str, str], sender_name: str = "") -> str:
    """Replaces placeholders like {company}, {name}, {hr_name}, {my_name}, {email} in template."""
    company_val = contact.get("company", "").strip() or "your company"
    name_val = contact.get("hr_name", "").strip() or "Hiring Manager"
    email_val = contact.get("email", "").strip()

    text = template
    # Case-insensitive replacement of standard tags
    replacements = {
        "{company}": company_val,
        "{Company}": company_val,
        "{COMPANY}": company_val.upper(),
        "{name}": name_val,
        "{Name}": name_val,
        "{hr_name}": name_val,
        "{Hr_Name}": name_val,
        "{HR_NAME}": name_val,
        "{my_name}": sender_name or "",
        "{My_Name}": sender_name or "",
        "{email}": email_val
    }

    for tag, val in replacements.items():
        text = text.replace(tag, val)
    return text

def render_progress_bar(completed: int, total: int, length: int = 10) -> str:
    """Renders a visual progress bar e.g. [██████░░░░] 60%"""
    if total <= 0:
        return "[░░░░░░░░░░] 0%"
    fraction = min(1.0, completed / total)
    filled = int(fraction * length)
    bar = "█" * filled + "░" * (length - filled)
    percent = int(fraction * 100)
    return f"[{bar}] {percent}%"
