"""
NOVEX AI v5.4 — Flask server (replacement)
==========================================
Compatible with the new session-aware novex.py.
Fixes:
  • nv.quiz_state / nv.ACTIVE_MODEL references (now via safe helpers)
  • session_id now passed to all streaming / brain calls → no cross-user leakage
  • deep_explain correctly forwards personas + memory
"""

from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context, session
from flask_cors import CORS
from waitress import serve
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler  # noqa: F401
import os
import json
import uuid
import datetime
import secrets
import asyncio
import time
import random
import base64
import re
import requests
from io import BytesIO
from collections import defaultdict
from dotenv import load_dotenv

# Convex Client
try:
    from convex import ConvexClient
except ImportError:
    ConvexClient = None

load_dotenv()

import novex as nv
from novex import novex
from auth_extra import auth_extra_bp

# ============ CONVEX CLIENT ============
CONVEX_URL = os.getenv("CONVEX_URL")
if not CONVEX_URL:
    print("WARNING: CONVEX_URL is not set. Convex features will fail.")

convex_client = ConvexClient(CONVEX_URL) if (CONVEX_URL and ConvexClient) else None


def cq(path, args):
    """Convex Query Wrapper"""
    if not convex_client:
        raise ValueError("CONVEX_URL is not configured in environment variables")
    return convex_client.query(path, args)


def cm(path, args):
    """Convex Mutation Wrapper"""
    if not convex_client:
        raise ValueError("CONVEX_URL is not configured in environment variables")
    return convex_client.mutation(path, args)


# ============ novex.py COMPAT SHIMS ============
def _active_model() -> str:
    """Works with both old (ACTIVE_MODEL) and new (_ACTIVE_MODEL) novex."""
    return getattr(nv, "ACTIVE_MODEL", None) or getattr(nv, "_ACTIVE_MODEL", "groq:openai/gpt-oss-20b")


def _set_active_model(model_id: str) -> None:
    nv.set_model(model_id)  # new novex updates _ACTIVE_MODEL
    # mirror onto ACTIVE_MODEL if the attribute exists / is expected by callers
    if hasattr(nv, "ACTIVE_MODEL"):
        try:
            nv.ACTIVE_MODEL = model_id
        except Exception:
            pass


def _quiz_active(session_id: str) -> bool:
    """Works with both old (quiz_state dict) and new (_quiz_state per-session)."""
    if hasattr(nv, "_quiz_state"):
        st = nv._quiz_state.get(session_id) or {}
        return bool(st.get("active"))
    if hasattr(nv, "quiz_state"):
        return bool(nv.quiz_state.get("active"))
    return False


# ============ 2FA (optional) ============
try:
    import pyotp
    import qrcode
    TOTP_AVAILABLE = True
except ImportError:
    TOTP_AVAILABLE = False

# ============ APP ============
app = Flask(__name__, static_folder=".")
app.register_blueprint(auth_extra_bp)
CORS(app, supports_credentials=True)

app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.permanent_session_lifetime = datetime.timedelta(days=36500)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

# ============ EMAIL ============
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@novex.local")
FROM_NAME = os.getenv("FROM_NAME", "NOVEX AI")
APP_URL = os.getenv("APP_URL", "http://localhost:10000")


def send_email(to, subject, body):
    if not BREVO_API_KEY:
        print("\n" + "=" * 60, flush=True)
        print(f"[EMAIL FALLBACK] -> {to}", flush=True)
        print(f"Subject: {subject}", flush=True)
        print("-" * 60, flush=True)
        print(body, flush=True)
        print("=" * 60 + "\n", flush=True)
        return True
    try:
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "sender": {"email": FROM_EMAIL, "name": FROM_NAME},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code in (200, 201, 202):
            print(f"[EMAIL] Sent to {to} via Brevo", flush=True)
            return True
        print(f"[EMAIL ERROR] Brevo {resp.status_code}: {resp.text}", flush=True)
        return False
    except Exception as e:
        print(f"[EMAIL ERROR] {e}", flush=True)
        return False


# ============ RATE LIMIT ============
rate_buckets = defaultdict(list)


def check_rate_limit(key, max_attempts=5, window_sec=300):
    now = time.time()
    bucket = rate_buckets[key]
    bucket[:] = [t for t in bucket if now - t < window_sec]
    if len(bucket) >= max_attempts:
        return False
    bucket.append(now)
    return True


def get_client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()


# ============ LOCAL DIRS ============
UPLOADS_DIR = "uploads"
VOICE_DIR = "voice"
for d in [UPLOADS_DIR, VOICE_DIR]:
    os.makedirs(d, exist_ok=True)

AVAILABLE_MODELS = [
    {"id": "groq:openai/gpt-oss-120b", "name": "Novex Pro", "provider": "Groq", "desc": "Best for coding"},
    {"id": "groq:openai/gpt-oss-20b", "name": "Novex Balanced", "provider": "Groq", "desc": "Speed + quality"},
    {"id": "groq:llama-3.3-70b-versatile", "name": "Novex Turbo", "provider": "Groq", "desc": "Balanced fast"},
]

VOICES = {
    "hi-male": "hi-IN-MadhurNeural", "hi-female": "hi-IN-SwaraNeural",
    "en-in-male": "en-IN-PrabhatNeural", "en-in-female": "en-IN-NeerjaNeural",
    "en-us-male": "en-US-GuyNeural", "en-us-female": "en-US-JennyNeural",
    "en-gb-female": "en-GB-SoniaNeural", "ur-male": "ur-PK-AsadNeural",
    "bn-female": "bn-IN-TanishaaNeural", "ta-male": "ta-IN-ValluvarNeural",
    "te-male": "te-IN-MohanNeural", "mr-male": "mr-IN-ManoharNeural",
    "gu-female": "gu-IN-DhwaniNeural", "kn-male": "kn-IN-GaganNeural",
    "ml-male": "ml-IN-MidhunNeural", "pa-female": "pa-IN-GurpreetNeural",
    "ar-male": "ar-SA-HamedNeural", "zh-female": "zh-CN-XiaoxiaoNeural",
    "ja-female": "ja-JP-NanamiNeural", "ko-female": "ko-KR-SunHiNeural",
    "fr-female": "fr-FR-DeniseNeural", "de-male": "de-DE-ConradNeural",
    "es-female": "es-ES-ElviraNeural", "ru-female": "ru-RU-SvetlanaNeural",
    "pt-br-female": "pt-BR-FranciscaNeural", "it-female": "it-IT-ElsaNeural",
}


# ============ HELPERS ============
def current_user():
    return session.get("user")


def current_user_id():
    return session.get("user_id")


def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"error": "Not logged in", "need_login": True}), 401
        return f(*args, **kwargs)
    return wrapper


def is_valid_email(email):
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email or ""))


def password_strength(pw):
    if not pw:
        return 0, "empty", ["Password required"]
    score = 0
    issues = []
    if len(pw) >= 8:
        score += 1
    else:
        issues.append("Min 8 characters")
    if len(pw) >= 12:
        score += 1
    if re.search(r"[A-Z]", pw) and re.search(r"[a-z]", pw):
        score += 1
    else:
        issues.append("Mix upper+lowercase")
    if re.search(r"\d", pw):
        score += 1
    else:
        issues.append("Include a number")
    if re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=]", pw):
        score += 1
    else:
        issues.append("Include a symbol")
    labels = ["very weak", "weak", "fair", "good", "strong"]
    return min(score, 4), labels[min(score, 4)], issues


def gen_code():
    return f"{random.randint(0, 999999):06d}"


# ============ CONVEX HELPERS ============
def user_by_username(username):
    return cq("users:getByUsername", {"username": (username or "").lower()})


def user_by_email(email):
    return cq("users:getByEmail", {"email": (email or "").lower()})


def user_by_id(uid):
    return cq("users:getById", {"id": uid})


def record_login(user_id, success=True):
    cm("auth:recordLogin", {
        "user_id": user_id,
        "ip": get_client_ip(),
        "ua": (request.headers.get("User-Agent") or "")[:200],
        "success": success,
    })


# ============ AUTH ============
@app.route("/auth/check-username", methods=["POST"])
def auth_check_username():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    if not username:
        return jsonify({"available": False, "error": "Empty"})
    if len(username) < 3:
        return jsonify({"available": False, "error": "Min 3 chars"})
    if len(username) > 20:
        return jsonify({"available": False, "error": "Max 20 chars"})
    if not username.replace("_", "").isalnum():
        return jsonify({"available": False, "error": "Only letters/numbers/_"})
    if user_by_username(username):
        return jsonify({"available": False, "error": "Already taken"})
    return jsonify({"available": True})


@app.route("/auth/check-email", methods=["POST"])
def auth_check_email():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not is_valid_email(email):
        return jsonify({"available": False, "error": "Invalid email"})
    if user_by_email(email):
        return jsonify({"available": False, "error": "Already registered"})
    return jsonify({"available": True})


@app.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or username.title()).strip()[:40]

    if not check_rate_limit(f"reg:{get_client_ip()}", max_attempts=5, window_sec=600):
        return jsonify({"error": "Too many attempts. Wait 10 minutes."}), 429

    if not username or not email or not password:
        return jsonify({"error": "Username, email aur password zaroori"}), 400
    if len(username) < 3 or len(username) > 20:
        return jsonify({"error": "Username 3-20 characters"}), 400
    if not username.replace("_", "").isalnum():
        return jsonify({"error": "Username: sirf letters, numbers, _"}), 400
    if not is_valid_email(email):
        return jsonify({"error": "Valid email daalein"}), 400
    score, label, issues = password_strength(password)
    if score < 2:
        return jsonify({"error": "Password weak: " + ", ".join(issues)}), 400
    if user_by_username(username):
        return jsonify({"error": "Username pehle se hai"}), 400
    if user_by_email(email):
        return jsonify({"error": "Email pehle se registered hai"}), 400

    code = gen_code()
    cm("auth:createPending", {
        "username": username, "email": email,
        "password_hash": generate_password_hash(password),
        "display_name": display_name, "code": code,
    })
    subject = "NOVEX AI — Verify your email"
    body = (
        f"Hi {display_name},\n\nWelcome to NOVEX AI!\n\n"
        f"Your email verification code is:\n\n    {code}\n\n"
        f"This code expires in 15 minutes.\n\n— NOVEX AI"
    )
    send_email(email, subject, body)
    masked = email[:2] + "***@" + email.split("@")[1] if "@" in email else email
    return jsonify({"ok": True, "message": "Verification code sent",
                    "username": username, "email_masked": masked})


# ---- Backward-compat aliases ----
@app.route("/register", methods=["POST"])
def register_compat():
    return auth_register()


@app.route("/auth/login", methods=["POST"])
def login_compat():
    return login()


@app.route("/auth/logout", methods=["POST"])
def logout_compat():
    return logout()


@app.route("/auth/me", methods=["GET"])
def me_compat():
    return me()


@app.route("/auth/forgot-password", methods=["POST"])
def forgot_compat():
    return auth_forgot()


@app.route("/auth/reset-password", methods=["POST"])
def reset_compat():
    return auth_reset()


# ============ VERIFY ============
@app.route("/auth/verify", methods=["POST"])
def auth_verify():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    code = (data.get("code") or "").strip()
    if not username or not code:
        return jsonify({"error": "Username aur code chahiye"}), 400
    entry = cq("auth:getPending", {"username": username})
    if not entry:
        return jsonify({"error": "Verification session nahi mila. Dobara register karein."}), 400
    try:
        if datetime.datetime.fromisoformat(entry["expires"]) < datetime.datetime.now():
            cm("auth:deletePending", {"username": username})
            return jsonify({"error": "Code expire ho gaya."}), 400
    except Exception:
        pass
    if entry["code"] != code:
        return jsonify({"error": "Galat code."}), 400
    uid = cm("users:create", {
        "username": username,
        "email": entry["email"],
        "password_hash": entry["password_hash"],
        "display_name": entry["display_name"],
        "email_verified": True,
        "auth_provider": "local",
    })
    cm("auth:deletePending", {"username": username})
    session.permanent = True
    session["user"] = username
    session["user_id"] = uid
    record_login(uid, True)
    return jsonify({"ok": True, "username": username, "display_name": entry["display_name"]})


@app.route("/auth/resend-verify", methods=["POST"])
def auth_resend_verify():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    entry = cq("auth:getPending", {"username": username})
    if not entry:
        return jsonify({"error": "Session expired."}), 400
    if not check_rate_limit(f"resend:{get_client_ip()}:{username}",
                            max_attempts=3, window_sec=300):
        return jsonify({"error": "Too many resend requests."}), 429
    code = gen_code()
    cm("auth:updatePendingCode", {"username": username, "code": code})
    body = f"Your new code:\n\n    {code}\n\nValid 15 minutes.\n\n— NOVEX AI"
    send_email(entry["email"], "NOVEX AI — New code", body)
    return jsonify({"ok": True})


# ============ LOGIN ============
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    identifier = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    totp_code = (data.get("totp") or "").strip()

    if not check_rate_limit(f"login:{get_client_ip()}", max_attempts=8, window_sec=300):
        return jsonify({"error": "Too many login attempts. Wait 5 minutes."}), 429

    user = user_by_username(identifier) or user_by_email(identifier)
    if not user:
        return jsonify({"error": "Galat credentials"}), 401
    if not user.get("password_hash"):
        return jsonify({"error": "Use Google/Magic Link login"}), 401
    if not check_password_hash(user["password_hash"], password):
        record_login(user["_id"], False)
        return jsonify({"error": "Galat credentials"}), 401
    if not user.get("email_verified", False):
        return jsonify({"error": "Email verify nahi hua",
                        "need_verify": True, "username": user["username"]}), 403

    if user.get("totp_enabled") and user.get("totp_secret"):
        if not totp_code:
            return jsonify({"error": "2FA code required",
                            "need_2fa": True, "username": user["username"]}), 202
        if not TOTP_AVAILABLE:
            return jsonify({"error": "2FA unavailable"}), 500
        totp = pyotp.TOTP(user["totp_secret"])
        if not totp.verify(totp_code, valid_window=1):
            record_login(user["_id"], False)
            return jsonify({"error": "Galat 2FA code"}), 401

    session.permanent = True
    session["user"] = user["username"]
    session["user_id"] = user["_id"]
    cm("users:updateLastLogin", {"id": user["_id"]})
    record_login(user["_id"], True)
    return jsonify({"ok": True, "username": user["username"],
                    "display_name": user.get("display_name", user["username"].title())})


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    session.pop("user_id", None)
    session.pop("guest_id", None)
    return jsonify({"ok": True})


@app.route("/me", methods=["GET"])
def me():
    if "user" not in session:
        return jsonify({"logged_in": False})
    user = user_by_username(session["user"])
    if not user:
        session.clear()
        return jsonify({"logged_in": False})
    return jsonify({
        "logged_in": True,
        "username": user["username"],
        "display_name": user.get("display_name", user["username"].title()),
        "email": user.get("email", ""),
        "email_verified": user.get("email_verified", False),
        "totp_enabled": user.get("totp_enabled", False),
        "has_password": bool(user.get("password_hash")),
        "auth_provider": user.get("auth_provider", "local"),
        "is_guest": user.get("auth_provider") == "guest",
    })


# ============ PASSWORD RESET ============
@app.route("/auth/forgot", methods=["POST"])
def auth_forgot():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not check_rate_limit(f"forgot:{get_client_ip()}", max_attempts=3, window_sec=600):
        return jsonify({"error": "Too many requests."}), 429
    user = user_by_email(email)
    if not user:
        return jsonify({"ok": True, "message": "If email exists, code sent."})
    code = gen_code()
    token = secrets.token_urlsafe(24)
    cm("auth:createReset", {"token": token, "username": user["username"],
                            "email": email, "code": code})
    body = f"Hi,\n\nPassword reset code:\n\n    {code}\n\nValid 15 minutes.\n\n— NOVEX AI"
    send_email(email, "NOVEX AI — Password Reset", body)
    return jsonify({"ok": True, "message": "If email exists, code sent."})


@app.route("/auth/reset", methods=["POST"])
def auth_reset():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    new_password = data.get("new_password") or ""
    if not check_rate_limit(f"reset:{get_client_ip()}", max_attempts=6, window_sec=600):
        return jsonify({"error": "Too many attempts."}), 429
    if not email or not code or not new_password:
        return jsonify({"error": "Sab fields zaroori"}), 400
    score, label, issues = password_strength(new_password)
    if score < 2:
        return jsonify({"error": "Password weak: " + ", ".join(issues)}), 400
    entry = cq("auth:findReset", {"email": email, "code": code})
    if not entry:
        return jsonify({"error": "Galat ya expired code"}), 400
    user = user_by_username(entry["username"])
    if not user:
        return jsonify({"error": "User not found"}), 404
    cm("users:updatePassword", {"id": user["_id"],
                                "password_hash": generate_password_hash(new_password)})
    cm("auth:deleteReset", {"token": entry["token"]})
    return jsonify({"ok": True})


# ============ 2FA ============
@app.route("/auth/2fa/setup", methods=["POST"])
@require_login
def auth_2fa_setup():
    if not TOTP_AVAILABLE:
        return jsonify({"error": "2FA not available"}), 500
    user = user_by_username(current_user())
    secret = pyotp.random_base32()
    label = user.get("email") or user["username"]
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=label, issuer_name="NOVEX AI")
    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    qr_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    session["pending_totp_secret"] = secret
    return jsonify({"ok": True, "secret": secret, "qr": qr_url})


@app.route("/auth/2fa/enable", methods=["POST"])
@require_login
def auth_2fa_enable():
    if not TOTP_AVAILABLE:
        return jsonify({"error": "2FA unavailable"}), 500
    data = request.get_json() or {}
    code = (data.get("code") or "").strip()
    secret = session.get("pending_totp_secret")
    if not secret:
        return jsonify({"error": "Setup start karein"}), 400
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        return jsonify({"error": "Galat code"}), 400
    user = user_by_username(current_user())
    cm("users:set2FA", {"id": user["_id"], "secret": secret, "enabled": True})
    session.pop("pending_totp_secret", None)
    return jsonify({"ok": True})


@app.route("/auth/2fa/disable", methods=["POST"])
@require_login
def auth_2fa_disable():
    data = request.get_json() or {}
    password = data.get("password") or ""
    user = user_by_username(current_user())
    if not user.get("password_hash"):
        return jsonify({"error": "No password set"}), 400
    if not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Galat password"}), 401
    cm("users:set2FA", {"id": user["_id"], "secret": None, "enabled": False})
    return jsonify({"ok": True})


# ============ SESSIONS ============
@app.route("/auth/sessions", methods=["GET"])
@require_login
def auth_sessions():
    user = user_by_username(current_user())
    hist = cq("auth:getHistory", {"user_id": user["_id"]}) or []
    return jsonify({"sessions": hist})


@app.route("/auth/sessions/clear", methods=["POST"])
@require_login
def auth_sessions_clear():
    user = user_by_username(current_user())
    cm("auth:clearHistory", {"user_id": user["_id"]})
    return jsonify({"ok": True})


@app.route("/auth/password/change", methods=["POST"])
@require_login
def auth_password_change():
    data = request.get_json() or {}
    old = data.get("old_password") or ""
    new = data.get("new_password") or ""
    user = user_by_username(current_user())
    if user.get("password_hash"):
        if not check_password_hash(user["password_hash"], old):
            return jsonify({"error": "Galat purana password"}), 401
    score, label, issues = password_strength(new)
    if score < 2:
        return jsonify({"error": "Password weak: " + ", ".join(issues)}), 400
    cm("users:updatePassword", {"id": user["_id"],
                                "password_hash": generate_password_hash(new)})
    return jsonify({"ok": True})


@app.route("/auth/account/delete", methods=["POST"])
@require_login
def auth_account_delete():
    user = user_by_username(current_user())
    if not user:
        return jsonify({"error": "Not found"}), 404
    cm("users:deleteUser", {"id": user["_id"]})
    session.clear()
    return jsonify({"ok": True})


# ============ USERS SEARCH ============
@app.route("/users/search", methods=["GET"])
@require_login
def users_search():
    q = (request.args.get("q") or "").strip().lower()
    if len(q) < 2:
        return jsonify({"users": []})
    me = user_by_username(current_user())
    result = cq("users:search", {"q": q, "me_id": me["_id"] if me else None}) or []
    return jsonify({"users": result})


# ============ SETTINGS ============
@app.route("/settings", methods=["GET"])
@require_login
def get_settings():
    user = user_by_username(current_user())
    s = cq("misc:getSettings", {"user_id": user["_id"]})
    if not s:
        return jsonify({"custom_instructions": "",
                        "quiet_hours": {"enabled": False, "start": "22:00",
                                        "end": "07:00", "tz_offset": 5.5}})
    return jsonify({
        "custom_instructions": s.get("custom_instructions", ""),
        "quiet_hours": s.get("quiet_hours", {"enabled": False, "start": "22:00",
                                             "end": "07:00", "tz_offset": 5.5}),
    })


@app.route("/settings", methods=["POST"])
@require_login
def update_settings():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    patch = {"user_id": user["_id"]}
    if "custom_instructions" in data:
        patch["custom_instructions"] = str(data["custom_instructions"])[:4000]
    if "quiet_hours" in data and isinstance(data["quiet_hours"], dict):
        qh = data["quiet_hours"]
        patch["quiet_hours"] = {
            "enabled": bool(qh.get("enabled", False)),
            "start": str(qh.get("start", "22:00"))[:5],
            "end": str(qh.get("end", "07:00"))[:5],
            "tz_offset": float(qh.get("tz_offset", 5.5)),
        }
    cm("misc:updateSettings", patch)
    return jsonify({"ok": True, "settings": patch})


# ============ PERSONAS ============
@app.route("/personas", methods=["GET"])
@require_login
def list_personas():
    user = user_by_username(current_user())
    items = cq("misc:listPersonas", {"user_id": user["_id"]}) or []
    out = {}
    for p in items:
        out[p["slug"]] = {"name": p["name"], "prompt": p["prompt"],
                          "icon": p["icon"], "created": p["created"]}
    return jsonify({"personas": out})


@app.route("/personas", methods=["POST"])
@require_login
def save_persona():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    prompt = (data.get("prompt") or "").strip()
    icon = (data.get("icon") or "🤖").strip()[:4]
    if not name or not prompt:
        return jsonify({"error": "Name aur prompt chahiye"}), 400
    slug = "".join(c for c in name.lower().replace(" ", "_")
                   if c.isalnum() or c == "_") or "persona"
    cm("misc:savePersona", {"user_id": user["_id"], "slug": slug,
                            "name": name, "prompt": prompt, "icon": icon})
    return jsonify({"ok": True, "slug": slug})


@app.route("/personas/<slug>", methods=["DELETE"])
@require_login
def delete_persona(slug):
    user = user_by_username(current_user())
    cm("misc:deletePersona", {"user_id": user["_id"], "slug": slug})
    return jsonify({"ok": True})


# ============ PROJECTS ============
@app.route("/projects", methods=["GET"])
@require_login
def list_projects():
    user = user_by_username(current_user())
    items = cq("misc:listProjects", {"user_id": user["_id"]}) or []
    return jsonify({"projects": [{"id": p["_id"], "name": p["name"],
                                  "color": p["color"], "created": p["created"]}
                                 for p in items]})


@app.route("/projects", methods=["POST"])
@require_login
def create_project():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    color = (data.get("color") or "#06b6d4").strip()[:9]
    if not name:
        return jsonify({"error": "Name chahiye"}), 400
    pid = cm("misc:createProject", {"user_id": user["_id"],
                                    "name": name, "color": color})
    return jsonify({"ok": True, "id": pid})


@app.route("/projects/<pid>", methods=["DELETE"])
@require_login
def delete_project(pid):
    cm("misc:deleteProject", {"project_id": pid})
    return jsonify({"ok": True})


# ============ MEMORY ============
@app.route("/memory", methods=["GET"])
@require_login
def list_memory():
    user = user_by_username(current_user())
    items = cq("misc:listMemory", {"user_id": user["_id"]}) or []
    return jsonify({"memory": [{"id": m["_id"], "fact": m["fact"],
                                "source": m["source"], "created": m["created"]}
                               for m in items]})


@app.route("/memory", methods=["POST"])
@require_login
def create_memory():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    fact = (data.get("fact") or "").strip()
    if not fact:
        return jsonify({"error": "Fact chahiye"}), 400
    if len(fact) > 500:
        return jsonify({"error": "Max 500"}), 400
    result = cm("misc:addMemory", {"user_id": user["_id"],
                                   "fact": fact, "source": "manual"})
    return jsonify({"ok": True, "id": result.get("id"),
                    "duplicate": result.get("duplicate", False)})


@app.route("/memory/<mid>", methods=["DELETE"])
@require_login
def delete_memory(mid):
    cm("misc:deleteMemory", {"id": mid})
    return jsonify({"ok": True})


@app.route("/memory/all", methods=["DELETE"])
@require_login
def clear_memory():
    user = user_by_username(current_user())
    cm("misc:clearMemory", {"user_id": user["_id"]})
    return jsonify({"ok": True})


@app.route("/memory/auto-extract", methods=["POST"])
@require_login
def auto_extract_memory():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Text chahiye"}), 400
    facts = nv.extract_facts(text)
    added = []
    for f in facts:
        result = cm("misc:addMemory", {"user_id": user["_id"],
                                       "fact": f, "source": "auto"})
        if not result.get("duplicate"):
            added.append(f)
    return jsonify({"ok": True, "added": added, "count": len(added)})


# ============ FLASHCARDS ============
@app.route("/flashcards", methods=["GET"])
@require_login
def list_flashcards():
    user = user_by_username(current_user())
    items = cq("misc:listFlashcards", {"user_id": user["_id"]}) or []
    return jsonify({"decks": [{"id": d["_id"], "title": d["title"],
                               "cards": d["cards"], "created": d["created"],
                               "reviewed": d["reviewed"]} for d in items]})


@app.route("/flashcards/generate", methods=["POST"])
@require_login
def generate_flashcards_endpoint():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    source = (data.get("source") or "").strip()
    count = int(data.get("count") or 10)
    topic = (data.get("topic") or "").strip()
    chat_id = data.get("chat_id")
    if chat_id and not source:
        c = cq("chats:getById", {"id": chat_id, "viewer_id": user["_id"]})
        if c:
            source = "\n\n".join(m.get("content", "")
                                 for m in c.get("messages", [])[-10:])
    if not source and not topic:
        return jsonify({"error": "Topic ya chat_id chahiye"}), 400
    cards = nv.generate_flashcards(source or f"Topic: {topic}", count)
    if "error" in cards:
        return jsonify(cards), 500
    deck_id = cm("misc:createFlashcardDeck", {
        "user_id": user["_id"],
        "title": (topic or cards.get("title", "Flashcards"))[:60],
        "cards": cards["cards"],
    })
    return jsonify({"ok": True, "deck": {"id": deck_id,
                                         "title": topic or "Flashcards",
                                         "cards": cards["cards"]}})


@app.route("/flashcards/<deck_id>", methods=["DELETE"])
@require_login
def delete_flashcards(deck_id):
    cm("misc:deleteFlashcardDeck", {"id": deck_id})
    return jsonify({"ok": True})


# ============ DOCS ============
@app.route("/docs", methods=["GET"])
@require_login
def list_docs():
    user = user_by_username(current_user())
    items = cq("misc:listDocs", {"user_id": user["_id"]}) or []
    return jsonify({"docs": items})


@app.route("/docs/<doc_id>", methods=["GET"])
@require_login
def get_doc(doc_id):
    d = cq("misc:getDoc", {"id": doc_id})
    if not d:
        return jsonify({"error": "Not found"}), 404
    return jsonify(d)


@app.route("/docs/<doc_id>", methods=["DELETE"])
@require_login
def delete_doc(doc_id):
    cm("misc:deleteDoc", {"id": doc_id})
    return jsonify({"ok": True})


@app.route("/docs/generate", methods=["POST"])
@require_login
def generate_doc():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    topic = (data.get("topic") or "").strip()
    style = (data.get("style") or "essay").strip().lower()
    length = (data.get("length") or "medium").strip().lower()
    language = (data.get("language") or "hindi").strip().lower()
    if not topic:
        return jsonify({"error": "Topic chahiye"}), 400
    if style not in ["essay", "blog", "report", "story", "notes"]:
        style = "essay"
    if length not in ["short", "medium", "long"]:
        length = "medium"
    result = nv.generate_document(topic, style, length, language)
    if "error" in result:
        return jsonify(result), 500
    doc_id = cm("misc:createDoc", {
        "user_id": user["_id"],
        "title": result.get("title", topic)[:80],
        "topic": topic, "style": style, "length": length, "language": language,
        "outline": result.get("outline", []),
        "content": result.get("content", ""),
    })
    return jsonify({"ok": True, "doc": {"id": doc_id,
                                        "title": result.get("title", topic),
                                        "content": result.get("content", "")}})


# ============ STATS ============
@app.route("/stats", methods=["GET"])
@require_login
def stats():
    user = user_by_username(current_user())
    s = cq("misc:getStats", {"user_id": user["_id"]})
    if not s:
        return jsonify({"total_in": 0, "total_out": 0, "calls": 0, "models": {}})
    models = {}
    for m in s.get("model_stats", []):
        models[m["model"]] = {"in": m["in"], "out": m["out"], "calls": m["calls"]}
    return jsonify({"total_in": s["total_in"], "total_out": s["total_out"],
                    "calls": s["calls"], "models": models})


def record_usage(user_id, model, tokens_in, tokens_out):
    try:
        cm("misc:recordUsage", {"user_id": user_id, "model": model,
                                "tokens_in": tokens_in, "tokens_out": tokens_out})
    except Exception as e:
        print(f"[record_usage] {e}", flush=True)


# ============ REMINDERS ============
@app.route("/reminders", methods=["GET"])
@require_login
def list_reminders():
    user = user_by_username(current_user())
    items = cq("misc:listReminders", {"user_id": user["_id"]}) or []
    return jsonify({"reminders": [{"id": r["_id"], "text": r["text"],
                                   "when": r["when_iso"], "fired": r["fired"]}
                                  for r in items]})


@app.route("/reminders", methods=["POST"])
@require_login
def create_reminder():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    when_iso = (data.get("when") or "").strip()
    if not text or not when_iso:
        return jsonify({"error": "text aur when zaroori"}), 400
    try:
        datetime.datetime.fromisoformat(when_iso)
    except Exception:
        return jsonify({"error": "when ISO format mein"}), 400
    rid = cm("misc:createReminder", {"user_id": user["_id"],
                                     "text": text, "when_iso": when_iso})
    return jsonify({"ok": True, "id": rid})


@app.route("/reminders/<rid>", methods=["DELETE"])
@require_login
def delete_reminder(rid):
    cm("misc:deleteReminder", {"id": rid})
    return jsonify({"ok": True})


@app.route("/reminders/pending", methods=["GET"])
@require_login
def pending_reminders():
    return jsonify({"pending": []})


# ============ MODELS ============
@app.route("/models", methods=["GET"])
@require_login
def models():
    return jsonify({"available": AVAILABLE_MODELS, "active": _active_model()})


@app.route("/set-model", methods=["POST"])
@require_login
def set_model_endpoint():
    data = request.get_json() or {}
    model_id = data.get("model")
    if not model_id:
        return jsonify({"error": "No model"}), 400
    _set_active_model(model_id)
    return jsonify({"ok": True, "active": _active_model()})


# ============ UPLOAD ============
@app.route("/upload", methods=["POST"])
@require_login
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    uid = uuid.uuid4().hex[:8]
    safe_name = f"{uid}_{f.filename}"
    path = os.path.join(UPLOADS_DIR, safe_name)
    f.save(path)
    return jsonify({"ok": True, "filename": f.filename, "path": path,
                    "size": os.path.getsize(path)})


# ============ QUIZ ============
@app.route("/quiz/start", methods=["POST"])
@require_login
def quiz_start():
    data = request.get_json() or {}
    topic = (data.get("topic") or "General Knowledge").strip()
    difficulty = (data.get("difficulty") or "medium").strip().lower()
    count = int(data.get("count") or 5)
    if count not in [5, 10, 15, 20, 30]:
        count = 5
    if difficulty not in ["easy", "medium", "hard"]:
        difficulty = "medium"
    result = nv.generate_quiz_json(topic, difficulty, count)
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


# ============ SEARCH ============
@app.route("/search", methods=["POST"])
@require_login
def web_search_endpoint():
    data = request.get_json() or {}
    q = (data.get("q") or "").strip()
    if not q:
        return jsonify({"error": "Query chahiye"}), 400
    results = nv.web_search_structured(q, max_results=6)
    return jsonify({"ok": True, "query": q, "results": results})


# ============ SHARE ============
@app.route("/share", methods=["POST"])
@require_login
def create_share():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    cid = data.get("chat_id")
    if not cid:
        return jsonify({"error": "chat_id chahiye"}), 400
    c = cq("chats:getById", {"id": cid, "viewer_id": user["_id"]})
    if not c:
        return jsonify({"error": "Chat nahi mili"}), 404
    token = uuid.uuid4().hex[:12]
    cm("misc:createSharedLink", {"token": token, "chat_id": cid,
                                 "owner_id": user["_id"],
                                 "title": c.get("title", "Shared chat")})
    return jsonify({"ok": True, "token": token, "url": f"/s/{token}"})


@app.route("/s/<token>")
def view_shared(token):
    entry = cq("misc:getSharedLink", {"token": token})
    if not entry:
        return "Chat not found", 404
    chat = cq("chats:getById", {"id": entry["chat_id"]})
    if not chat:
        return "Chat deleted", 404
    return _render_shared_html(chat)


def _render_shared_html(chat):
    import html as _html

    def esc(x):
        return _html.escape(str(x or ""))

    msgs = ""
    for m in chat.get("messages", []):
        role = m.get("role", "user")
        role_label = "You" if role == "user" else "NOVEX"
        cls = "user" if role == "user" else "bot"
        msgs += (f'<div class="msg {cls}"><div class="role">{role_label}</div>'
                 f'<div class="content">{esc(m.get("content", ""))}</div></div>')
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(chat.get("title","Shared"))}</title>
<style>body{{background:#0d0d0d;color:#ececec;font-family:system-ui;margin:0;padding:20px}}.wrap{{max-width:780px;margin:0 auto}}.head{{border-bottom:1px solid #ffffff20;padding-bottom:16px;margin-bottom:24px;display:flex;justify-content:space-between}}.head h1{{font-size:20px;margin:0}}.head a{{color:#10a37f;text-decoration:none;font-weight:700}}.msg{{margin-bottom:20px;padding:14px 18px;border-radius:12px;background:#1a1a1a}}.msg.user{{background:#262626;margin-left:auto;max-width:80%}}.msg.bot{{background:#000;border:1px solid #ffffff10}}.role{{font-size:11px;text-transform:uppercase;color:#8e8e8e;margin-bottom:6px;font-weight:600}}.content{{white-space:pre-wrap;line-height:1.7}}.footer{{margin-top:40px;padding-top:20px;border-top:1px solid #ffffff20;text-align:center;color:#8e8e8e;font-size:13px}}.footer a{{color:#10a37f}}</style></head><body><div class="wrap"><div class="head"><h1>{esc(chat.get("title","Shared"))}</h1><a href="/">NOVEX AI →</a></div>{msgs}<div class="footer">Read-only · <a href="/">Try NOVEX AI</a></div></div></body></html>'''


# ============ MULTI-USER ============
@app.route("/chats/<cid>/collaborators", methods=["GET"])
@require_login
def list_collaborators(cid):
    items = cq("chats:listCollaborators", {"chat_id": cid}) or []
    return jsonify({"owner": current_user(),
                    "collaborators": [u["username"] for u in items]})


@app.route("/chats/<cid>/collaborators", methods=["POST"])
@require_login
def add_chat_collaborator(cid):
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    if not username:
        return jsonify({"error": "Username chahiye"}), 400
    result = cm("chats:addCollaborator", {"chat_id": cid, "username": username})
    if result and result.get("error"):
        return jsonify({"error": result["error"]}), 400
    return jsonify({"ok": True})


@app.route("/chats/<cid>/collaborators/<username>", methods=["DELETE"])
@require_login
def remove_chat_collaborator(cid, username):
    cm("chats:removeCollaborator", {"chat_id": cid, "username": username.lower()})
    return jsonify({"ok": True})


@app.route("/shared-with-me", methods=["GET"])
@require_login
def shared_with_me():
    user = user_by_username(current_user())
    items = cq("chats:getSharedWithUser", {"user_id": user["_id"]}) or []
    return jsonify(items)


# ============ STATIC ============
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/index.html")
def index_html():
    return send_from_directory(".", "index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(".", "manifest.json")


@app.route("/sw.js")
def sw():
    return send_from_directory(".", "sw.js")


@app.route("/image/<path:filename>")
def image(filename):
    return send_from_directory(".", filename)


@app.route("/voice/<path:filename>")
def voice_file(filename):
    return send_from_directory(VOICE_DIR, filename)


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


@app.route("/health", methods=["GET"])
def health():
    try:
        cq("users:getByUsername", {"username": "__health_check__"})
        convex_ok = True
    except Exception:
        convex_ok = False
    return jsonify({
        "ok": True, "service": "novex-ai", "version": "5.4",
        "totp": TOTP_AVAILABLE,
        "brevo": bool(BREVO_API_KEY),
        "convex": convex_ok,
        "google": bool(os.getenv("GOOGLE_CLIENT_ID")),
        "session_days": 36500,
        "deep_explain": True,
        "session_isolation": True,
    })


# ============ TTS ============
@app.route("/tts", methods=["POST"])
@require_login
def tts():
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    voice_key = data.get("voice", "hi-male")
    if not text:
        return jsonify({"error": "Koi text nahi"}), 400
    if len(text) > 2000:
        text = text[:2000]
    voice = VOICES.get(voice_key, VOICES["hi-male"])
    filename = f"novex_{uuid.uuid4().hex[:12]}.mp3"
    out_path = os.path.join(VOICE_DIR, filename)
    try:
        import edge_tts

        async def _gen():
            c = edge_tts.Communicate(text, voice)
            await c.save(out_path)

        asyncio.run(_gen())
        if not os.path.exists(out_path) or os.path.getsize(out_path) < 500:
            return jsonify({"error": "TTS failed"}), 500
        return jsonify({"ok": True, "url": f"/voice/{filename}", "voice": voice})
    except Exception as e:
        return jsonify({"error": f"TTS error: {e}"}), 500


@app.route("/voices", methods=["GET"])
@require_login
def list_voices():
    return jsonify({"voices": list(VOICES.keys()), "default": "hi-male"})


# ============ TRANSLATION ============
LANGUAGES = [
    {"code": "hi", "name": "हिन्दी", "en": "Hindi"},
    {"code": "en", "name": "English", "en": "English"},
    {"code": "bn", "name": "বাংলা", "en": "Bengali"},
    {"code": "te", "name": "తెలుగు", "en": "Telugu"},
    {"code": "mr", "name": "मराठी", "en": "Marathi"},
    {"code": "ta", "name": "தமிழ்", "en": "Tamil"},
    {"code": "ur", "name": "اردو", "en": "Urdu"},
    {"code": "gu", "name": "ગુજરાતી", "en": "Gujarati"},
    {"code": "kn", "name": "ಕನ್ನಡ", "en": "Kannada"},
    {"code": "ml", "name": "മലയാളം", "en": "Malayalam"},
    {"code": "pa", "name": "ਪੰਜਾਬੀ", "en": "Punjabi"},
    {"code": "es", "name": "Español", "en": "Spanish"},
    {"code": "fr", "name": "Français", "en": "French"},
    {"code": "de", "name": "Deutsch", "en": "German"},
    {"code": "ar", "name": "العربية", "en": "Arabic"},
    {"code": "zh-CN", "name": "中文(简)", "en": "Chinese"},
    {"code": "ja", "name": "日本語", "en": "Japanese"},
    {"code": "ko", "name": "한국어", "en": "Korean"},
]


@app.route("/languages", methods=["GET"])
def languages():
    return jsonify({"languages": LANGUAGES})


@app.route("/translate", methods=["POST"])
@require_login
def translate():
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    target = (data.get("target") or "hi").strip()
    source = (data.get("source") or "auto").strip()
    if not text:
        return jsonify({"error": "Koi text nahi"}), 400
    return jsonify(nv.translate_text(text, target, source))


# ============ CHAT STREAM (fixed) ============
@app.route("/chat-stream", methods=["POST"])
@require_login
def chat_stream():
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    chat_id = data.get("chat_id")
    attachments = data.get("attachments", [])
    project_id = data.get("project_id")
    owner = data.get("owner")
    deep_explain = data.get("deep_explain", False)

    if not message and not attachments:
        return jsonify({"error": "Empty"}), 400

    user = user_by_username(current_user())
    if not user:
        return jsonify({"error": "User not found"}), 401

    sid = user["username"]  # session_id for novex per-user state

    chat_owner_id = user["_id"]
    if owner and owner != user["username"]:
        owner_user = user_by_username(owner)
        if not owner_user:
            return jsonify({"error": "Owner not found"}), 404
        if not chat_id:
            return jsonify({"error": "Shared chat needs id"}), 400
        chat_owner_id = owner_user["_id"]

    if not chat_id:
        title_src = message or (attachments[0] if attachments else "New chat")
        if deep_explain:
            title_src = "💡 " + title_src
        chat_id = cm("chats:create", {
            "user_id": chat_owner_id,
            "title": title_src[:45] + ("…" if len(title_src) > 45 else ""),
            "project_id": project_id,
        })

    final_message = message
    if attachments:
        final_message = ((message or "Analyze")
                         + "\n\n[Attached: " + ", ".join(attachments) + "]")

    sender = user["username"] if chat_owner_id != user["_id"] else None
    cm("chats:appendMessage", {
        "chat_id": chat_id, "role": "user",
        "content": ("💡 Deep Explain: " if deep_explain else "") + final_message,
        "attachments": attachments if attachments else None,
        "sender": sender,
    })

    user_settings = cq("misc:getSettings", {"user_id": user["_id"]}) or {}
    persona_items = cq("misc:listPersonas", {"user_id": user["_id"]}) or []
    user_personas = {p["slug"]: {"name": p["name"], "prompt": p["prompt"],
                                 "icon": p["icon"]} for p in persona_items}
    memory_items = cq("misc:listMemory", {"user_id": user["_id"]}) or []
    user_memory = [{"fact": m["fact"]} for m in memory_items]

    def _on_usage(_uid, model, ti, to):
        record_usage(user["_id"], model, ti, to)

    def generate():
        yield f"data: {json.dumps({'chat_id': chat_id})}\n\n".encode("utf-8")
        full = ""
        try:
            # -------- DEEP EXPLAIN MODE --------
            if deep_explain:
                for chunk in nv.ask_groq_stream(
                    final_message,
                    system_prompt=nv.DEEP_EXPLAIN_SYSTEM,
                    custom_instructions=user_settings.get("custom_instructions", ""),
                    user_personas=user_personas,
                    user=sid,
                    on_usage=_on_usage,
                    memory=user_memory,
                    session_id=sid,
                ):
                    full += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n".encode("utf-8")
                cm("chats:appendMessage", {"chat_id": chat_id,
                                           "role": "assistant", "content": full})
                yield f"data: {json.dumps({'done': True, 'full': full})}\n\n".encode("utf-8")
                return

            # -------- REMINDER SHORTCUT --------
            reminder_result = nv.parse_reminder(message)
            if reminder_result:
                when_dt = datetime.datetime.fromisoformat(reminder_result["when"])
                cm("misc:createReminder", {
                    "user_id": user["_id"],
                    "text": reminder_result["text"],
                    "when_iso": reminder_result["when"],
                })
                qh = user_settings.get("quiet_hours", {})
                extra = ""
                if qh.get("enabled"):
                    extra = (f"\n\n_🌙 Quiet hours "
                             f"({qh.get('start')}–{qh.get('end')})._")
                full = (f"✓ **Reminder set**\n\n"
                        f"- **Kaam:** {reminder_result['text']}\n"
                        f"- **Kab:** {when_dt.strftime('%A, %d %B %Y, %I:%M %p')}"
                        f"{extra}")
                for i in range(0, len(full), 4):
                    yield f"data: {json.dumps({'chunk': full[i:i+4]})}\n\n".encode("utf-8")
                cm("chats:appendMessage", {"chat_id": chat_id,
                                           "role": "assistant", "content": full})
                yield f"data: {json.dumps({'done': True, 'full': full})}\n\n".encode("utf-8")
                return

            # -------- ROUTE: simple / search / streaming --------
            p = message.lower().strip()
            is_quiz = (p == "/quiz" or p == "quiz" or p.startswith("/quiz ")
                       or p.startswith("quiz ") or p.endswith(" quiz"))
            simple_prefixes = ("time", "weather", "news", "search", "wiki",
                               "calc", "note", "notes", "image", "translate",
                               "pdf ", "save code", "calculate ")
            simple_words = ["mausam", "samay", "khabar", "baj", "waqt",
                            "dhundo", "hello", "hi", "hey", "namaste",
                            "bye", "thanks"]
            is_simple = p.startswith(simple_prefixes) or any(w in p for w in simple_words)
            quiz_running = _quiz_active(sid)

            if p.startswith(("search ", "google ", "dhundo ")):
                q = re.sub(r"^(search|google|dhundo)\s+", "", message,
                           flags=re.IGNORECASE).strip()
                results = nv.web_search_structured(q, max_results=5)
                full = nv.format_search_results_with_citations(q, results)
                for i in range(0, len(full), 4):
                    yield f"data: {json.dumps({'chunk': full[i:i+4]})}\n\n".encode("utf-8")

            elif is_simple or is_quiz or quiz_running or _active_model().startswith("ollama:"):
                full = novex(final_message, user=sid,
                             settings=user_settings,
                             personas=user_personas,
                             memory=user_memory,
                             session_id=sid)
                for i in range(0, len(full), 4):
                    yield f"data: {json.dumps({'chunk': full[i:i+4]})}\n\n".encode("utf-8")

            else:
                for chunk in nv.ask_groq_stream(
                    final_message,
                    custom_instructions=user_settings.get("custom_instructions", ""),
                    user_personas=user_personas,
                    user=sid,
                    on_usage=_on_usage,
                    memory=user_memory,
                    session_id=sid,
                ):
                    full += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n".encode("utf-8")

        except Exception as e:
            import traceback
            traceback.print_exc()
            full = f"Error: {e}"
            yield f"data: {json.dumps({'chunk': full})}\n\n".encode("utf-8")

        cm("chats:appendMessage", {"chat_id": chat_id,
                                   "role": "assistant", "content": full})
        yield f"data: {json.dumps({'done': True, 'full': full})}\n\n".encode("utf-8")

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform",
                 "X-Accel-Buffering": "no"},
    )


# ============ CHATS ============
@app.route("/chats", methods=["GET"])
@require_login
def list_chats():
    user = user_by_username(current_user())
    project_filter = request.args.get("project")
    pid = project_filter if project_filter else None
    items = cq("chats:listByUser", {"user_id": user["_id"], "project_id": pid}) or []
    return jsonify(items)


@app.route("/chats/<cid>", methods=["GET"])
@require_login
def get_chat(cid):
    user = user_by_username(current_user())
    c = cq("chats:getById", {"id": cid, "viewer_id": user["_id"]})
    if not c:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "id": c["_id"], "title": c["title"],
        "messages": c["messages"], "updated": c["updated"],
        "project_id": c.get("project_id"),
    })


@app.route("/chats/<cid>", methods=["DELETE"])
@require_login
def delete_chat(cid):
    cm("chats:remove", {"id": cid})
    return jsonify({"ok": True})


@app.route("/chats/<cid>", methods=["PUT"])
@require_login
def update_chat(cid):
    data = request.get_json() or {}
    patch = {"chat_id": cid}
    if "title" in data:
        patch["title"] = data["title"]
    if "project_id" in data:
        patch["project_id"] = data["project_id"]
    cm("chats:update", patch)
    return jsonify({"ok": True})


# ============ INIT auth_extra ============
from auth_extra import init as _auth_extra_init  # noqa: E402

_auth_extra_init(cq, cm, send_email, APP_URL, password_strength)


if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 10000))
    HOST = os.getenv("HOST", "0.0.0.0")
    print("=" * 60)
    print("  NOVEX AI v5.4 — Deep Explain + Brevo + 29 Themes")
    print(f"  URL: http://{HOST}:{PORT}")
    print(f"  Convex: {os.getenv('CONVEX_URL', 'NOT SET')}")
    print(f"  Brevo: {'configured' if BREVO_API_KEY else 'NOT configured (console fallback)'}")
    print(f"  From: {FROM_EMAIL}")
    print(f"  2FA: {'enabled' if TOTP_AVAILABLE else 'disabled'}")
    print(f"  Google OAuth: {'configured' if os.getenv('GOOGLE_CLIENT_ID') else 'NOT configured'}")
    print(f"  Session: 36500000 days")
    print(f"  Deep Explain: enabled")
    print(f"  Session isolation: ENABLED (per-user chat history)")
    print("=" * 60)
    serve(app, host=HOST, port=PORT, threads=16, send_bytes=1, channel_timeout=300)