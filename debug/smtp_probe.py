"""Check whether the saved Gmail password matches the expected one. Prints a short fingerprint only."""
import hashlib, os, re
pw = re.sub(r"[^A-Za-z0-9]", "", os.environ.get("SMTP_PASSWORD", ""))
print("secret fingerprint:", hashlib.sha256(pw.encode()).hexdigest()[:8], "len", len(pw))
