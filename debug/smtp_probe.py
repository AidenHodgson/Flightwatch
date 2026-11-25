"""Find out exactly where Gmail stops talking. Never prints the password."""
import os, re, smtplib, socket, ssl
host = "smtp.gmail.com"
user = os.environ.get("SMTP_USER", "").strip()
pw = re.sub(r"[^A-Za-z0-9]", "", os.environ.get("SMTP_PASSWORD", ""))
print("user:", user, "pw len:", len(pw), "pw all lowercase letters:", pw.isalpha() and pw.islower())
print("runner ip:", socket.gethostbyname(socket.gethostname()))
for mech in ("PLAIN", "LOGIN"):
    for port in (587, 465):
        try:
            if port == 465:
                s = smtplib.SMTP_SSL(host, 465, timeout=20, context=ssl.create_default_context())
            else:
                s = smtplib.SMTP(host, 587, timeout=20)
            code, msg = s.ehlo(); print(f"[{mech} {port}] ehlo {code}")
            if port == 587:
                print(f"[{mech} {port}] starttls", s.starttls()[0]); s.ehlo()
            print(f"[{mech} {port}] auth offered:", s.esmtp_features.get("auth"))
            s.user, s.password = user, pw
            auth = s.auth_plain if mech == "PLAIN" else s.auth_login
            try:
                print(f"[{mech} {port}] AUTH result:", s.auth(mech, auth, initial_response_ok=(mech == "PLAIN")))
                print(f"[{mech} {port}] LOGIN OK")
            except smtplib.SMTPAuthenticationError as e:
                print(f"[{mech} {port}] AUTH rejected:", e.smtp_code, e.smtp_error.decode(errors="replace")[:300])
            except Exception as e:
                print(f"[{mech} {port}] AUTH error:", repr(e))
            try: s.quit()
            except Exception: pass
        except Exception as e:
            print(f"[{mech} {port}] connect error:", repr(e))
