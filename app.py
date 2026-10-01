"""
NOVEX AI v7.0 — Flask Server
Complete: Chat, Auth, 2FA, Quiz v2, Batch 1+2, Lingua, Voice, Rooms, Peer Doubts,
Real-time Search (Serper + DDGS), 32 Themes
"""
from flask import (Flask, request, jsonify, send_from_directory, Response,
                   stream_with_context, session)
from flask_cors import CORS
from waitress import serve
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os, json, uuid, datetime, secrets, asyncio, time, random
import base64, re, requests
from io import BytesIO
from collections import defaultdict
from dotenv import load_dotenv

try:
    from convex import ConvexClient
except ImportError:
    ConvexClient = None

load_dotenv()

import novex as nv
from novex import novex
from auth_extra import auth_extra_bp

# ============ CONVEX ============
CONVEX_URL = os.getenv("CONVEX_URL")
if not CONVEX_URL:
    print("WARNING: CONVEX_URL not set")
convex_client = ConvexClient(CONVEX_URL) if (CONVEX_URL and ConvexClient) else None


def cq(path, args):
    if not convex_client:
        raise ValueError("CONVEX_URL not configured")
    return convex_client.query(path, args)


def cm(path, args):
    if not convex_client:
        raise ValueError("CONVEX_URL not configured")
    return convex_client.mutation(path, args)


# ============ COMPAT SHIMS ============
def _active_model():
    return getattr(nv, "ACTIVE_MODEL", None) or getattr(nv, "_ACTIVE_MODEL", "groq:openai/gpt-oss-20b")


def _set_active_model(mid):
    nv.set_model(mid)
    if hasattr(nv, "ACTIVE_MODEL"):
        try:
            nv.ACTIVE_MODEL = mid
        except Exception:
            pass


def _quiz_active(sid):
    if hasattr(nv, "is_quiz_active"):
        try:
            return nv.is_quiz_active(sid)
        except Exception:
            pass
    if hasattr(nv, "_quiz_state"):
        st = nv._quiz_state.get(sid) or {}
        return bool(st.get("active"))
    return False


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

# ============ CONFIG ============
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@novex.local")
FROM_NAME = os.getenv("FROM_NAME", "NOVEX AI")
APP_URL = os.getenv("APP_URL", "http://localhost:10000")

UPLOADS_DIR = "uploads"
VOICE_DIR = "voice"
for d in [UPLOADS_DIR, VOICE_DIR]:
    os.makedirs(d, exist_ok=True)

AVAILABLE_MODELS = [
    {"id": "groq:openai/gpt-oss-120b", "name": "Novex Pro",
     "provider": "Groq", "desc": "Best for coding"},
    {"id": "groq:openai/gpt-oss-20b", "name": "Novex Balanced",
     "provider": "Groq", "desc": "Speed + quality"},
    {"id": "groq:llama-3.3-70b-versatile", "name": "Novex Turbo",
     "provider": "Groq", "desc": "Balanced fast"},
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

rate_buckets = defaultdict(list)


# ============ HELPERS ============
def current_user():
    return session.get("user")


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


def check_rate_limit(key, max_attempts=5, window_sec=300):
    now = time.time()
    bucket = rate_buckets[key]
    bucket[:] = [t for t in bucket if now - t < window_sec]
    if len(bucket) >= max_attempts:
        return False
    bucket.append(now)
    return True


def get_client_ip():
    return request.headers.get("X-Forwarded-For",
                              request.remote_addr or "unknown").split(",")[0].strip()


def send_email(to, subject, body):
    if not BREVO_API_KEY:
        print("\n" + "=" * 60, flush=True)
        print(f"[EMAIL FALLBACK] -> {to}", flush=True)
        print(f"Subject: {subject}", flush=True)
        print(body, flush=True)
        print("=" * 60 + "\n", flush=True)
        return True
    try:
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {"api-key": BREVO_API_KEY, "Content-Type": "application/json"}
        payload = {"sender": {"email": FROM_EMAIL, "name": FROM_NAME},
                   "to": [{"email": to}], "subject": subject, "textContent": body}
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        return resp.status_code in (200, 201, 202)
    except Exception as e:
        print(f"[EMAIL ERROR] {e}", flush=True)
        return False


def user_by_username(u):
    return cq("users:getByUsername", {"username": (u or "").lower()})


def user_by_email(e):
    return cq("users:getByEmail", {"email": (e or "").lower()})


def record_login(uid, success=True):
    try:
        cm("auth:recordLogin", {"user_id": uid, "ip": get_client_ip(),
                                "ua": (request.headers.get("User-Agent") or "")[:200],
                                "success": success})
    except Exception:
        pass


# ============ GAMIFICATION HELPERS ============
def _get_or_create_progress(user_id):
    p = cq("misc:getProgress", {"user_id": user_id})
    if not p:
        cm("misc:createProgress", {"user_id": user_id})
        p = cq("misc:getProgress", {"user_id": user_id})
    return p or {}


def _award_exp(user_id, action, meta=""):
    try:
        amount = nv.EXP_REWARDS.get(action, 0)
        if amount <= 0:
            return
        p = _get_or_create_progress(user_id)
        new_exp = (p.get("exp") or 0) + amount
        lvl = nv.calculate_level(new_exp)
        cm("misc:updateProgress", {"user_id": user_id, "exp": new_exp,
                                   "level": lvl["level"], "level_icon": lvl["icon"]})
        cm("misc:logExp", {"user_id": user_id, "action": action,
                           "exp_gained": amount, "meta": meta})
    except Exception as e:
        print(f"[_award_exp] {e}", flush=True)


def _increment_counter(user_id, field, amount=1):
    try:
        cm("misc:incrementCounter", {"user_id": user_id, "field": field, "amount": amount})
    except Exception as e:
        print(f"[_increment_counter] {e}", flush=True)


def _check_badges(user_id):
    try:
        p = _get_or_create_progress(user_id)
        existing = cq("misc:listBadges", {"user_id": user_id}) or []
        have = {b["badge_id"] for b in existing}
        checks = [
            ("first_quiz", (p.get("quiz_count") or 0) >= 1),
            ("quiz_master", (p.get("quiz_count") or 0) >= 50),
            ("perfect_quiz", (p.get("perfect_quizzes") or 0) >= 1),
            ("flashcard_100", (p.get("flashcards_reviewed") or 0) >= 100),
            ("doc_writer", (p.get("docs_generated") or 0) >= 10),
            ("focus_10", (p.get("pomodoros_done") or 0) >= 10),
            ("doubt_solver", (p.get("doubts_solved") or 0) >= 10),
            ("memory_keeper", (p.get("memory_count") or 0) >= 20),
        ]
        for bid, cond in checks:
            if cond and bid not in have:
                icon, name, desc = nv.BADGES[bid]
                cm("misc:unlockBadge", {"user_id": user_id, "badge_id": bid,
                                        "badge_icon": icon, "badge_name": name,
                                        "badge_desc": desc})
    except Exception as e:
        print(f"[_check_badges] {e}", flush=True)


# ============================================================
# AUTH ROUTES
# ============================================================
@app.route("/auth/check-username", methods=["POST"])
def auth_check_username():
    data = request.get_json() or {}
    u = (data.get("username") or "").strip().lower()
    if not u:
        return jsonify({"available": False, "error": "Empty"})
    if len(u) < 3:
        return jsonify({"available": False, "error": "Min 3 chars"})
    if len(u) > 20:
        return jsonify({"available": False, "error": "Max 20 chars"})
    if not u.replace("_", "").isalnum():
        return jsonify({"available": False, "error": "Only letters/numbers/_"})
    if user_by_username(u):
        return jsonify({"available": False, "error": "Already taken"})
    return jsonify({"available": True})


@app.route("/auth/check-email", methods=["POST"])
def auth_check_email():
    data = request.get_json() or {}
    e = (data.get("email") or "").strip().lower()
    if not is_valid_email(e):
        return jsonify({"available": False, "error": "Invalid email"})
    if user_by_email(e):
        return jsonify({"available": False, "error": "Already registered"})
    return jsonify({"available": True})


@app.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or username.title()).strip()[:40]

    if not check_rate_limit(f"reg:{get_client_ip()}", 5, 600):
        return jsonify({"error": "Too many attempts."}), 429
    if not username or not email or not password:
        return jsonify({"error": "Sab fields zaroori"}), 400
    if len(username) < 3 or len(username) > 20:
        return jsonify({"error": "Username 3-20 chars"}), 400
    if not username.replace("_", "").isalnum():
        return jsonify({"error": "Username: letters, numbers, _"}), 400
    if not is_valid_email(email):
        return jsonify({"error": "Valid email daalein"}), 400
    score, _, issues = password_strength(password)
    if score < 2:
        return jsonify({"error": "Password weak: " + ", ".join(issues)}), 400
    if user_by_username(username):
        return jsonify({"error": "Username pehle se hai"}), 400
    if user_by_email(email):
        return jsonify({"error": "Email registered hai"}), 400

    code = gen_code()
    cm("auth:createPending", {"username": username, "email": email,
                              "password_hash": generate_password_hash(password),
                              "display_name": display_name, "code": code})
    send_email(email, "NOVEX AI — Verify",
               f"Hi {display_name},\n\nCode: {code}\n\nValid 15 min.\n— NOVEX")
    masked = email[:2] + "***@" + email.split("@")[1] if "@" in email else email
    return jsonify({"ok": True, "username": username, "email_masked": masked})


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


@app.route("/auth/verify", methods=["POST"])
def auth_verify():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    code = (data.get("code") or "").strip()
    if not username or not code:
        return jsonify({"error": "Dono chahiye"}), 400
    entry = cq("auth:getPending", {"username": username})
    if not entry:
        return jsonify({"error": "Session nahi mila."}), 400
    try:
        if datetime.datetime.fromisoformat(entry["expires"]) < datetime.datetime.now():
            cm("auth:deletePending", {"username": username})
            return jsonify({"error": "Code expire."}), 400
    except Exception:
        pass
    if entry["code"] != code:
        return jsonify({"error": "Galat code."}), 400
    uid = cm("users:create", {"username": username, "email": entry["email"],
                              "password_hash": entry["password_hash"],
                              "display_name": entry["display_name"],
                              "email_verified": True, "auth_provider": "local"})
    cm("auth:deletePending", {"username": username})
    session.permanent = True
    session["user"] = username
    session["user_id"] = uid
    record_login(uid, True)
    try:
        _get_or_create_progress(uid)
    except Exception:
        pass
    return jsonify({"ok": True, "username": username, "display_name": entry["display_name"]})


@app.route("/auth/resend-verify", methods=["POST"])
def auth_resend_verify():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    entry = cq("auth:getPending", {"username": username})
    if not entry:
        return jsonify({"error": "Session expired."}), 400
    if not check_rate_limit(f"resend:{get_client_ip()}:{username}", 3, 300):
        return jsonify({"error": "Too many."}), 429
    code = gen_code()
    cm("auth:updatePendingCode", {"username": username, "code": code})
    send_email(entry["email"], "NOVEX AI — New code", f"Code: {code}")
    return jsonify({"ok": True})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    identifier = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    totp_code = (data.get("totp") or "").strip()

    if not check_rate_limit(f"login:{get_client_ip()}", 8, 300):
        return jsonify({"error": "Too many login attempts."}), 429

    user = user_by_username(identifier) or user_by_email(identifier)
    if not user:
        return jsonify({"error": "Galat credentials"}), 401
    if not user.get("password_hash"):
        return jsonify({"error": "Use Google/Magic Link"}), 401
    if not check_password_hash(user["password_hash"], password):
        record_login(user["_id"], False)
        return jsonify({"error": "Galat credentials"}), 401
    if not user.get("email_verified", False):
        return jsonify({"error": "Email verify nahi hua",
                        "need_verify": True, "username": user["username"]}), 403

    if user.get("totp_enabled") and user.get("totp_secret"):
        if not totp_code:
            return jsonify({"error": "2FA required", "need_2fa": True,
                            "username": user["username"]}), 202
        if not TOTP_AVAILABLE:
            return jsonify({"error": "2FA unavailable"}), 500
        if not pyotp.TOTP(user["totp_secret"]).verify(totp_code, valid_window=1):
            record_login(user["_id"], False)
            return jsonify({"error": "Galat 2FA"}), 401

    session.permanent = True
    session["user"] = user["username"]
    session["user_id"] = user["_id"]
    cm("users:updateLastLogin", {"id": user["_id"]})
    record_login(user["_id"], True)
    try:
        _get_or_create_progress(user["_id"])
    except Exception:
        pass
    return jsonify({"ok": True, "username": user["username"],
                    "display_name": user.get("display_name", user["username"].title())})


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    session.pop("user_id", None)
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
        "logged_in": True, "username": user["username"],
        "display_name": user.get("display_name", user["username"].title()),
        "email": user.get("email", ""),
        "email_verified": user.get("email_verified", False),
        "totp_enabled": user.get("totp_enabled", False),
        "has_password": bool(user.get("password_hash")),
        "auth_provider": user.get("auth_provider", "local"),
        "is_guest": user.get("auth_provider") == "guest",
    })


@app.route("/auth/forgot", methods=["POST"])
def auth_forgot():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not check_rate_limit(f"forgot:{get_client_ip()}", 3, 600):
        return jsonify({"error": "Too many."}), 429
    user = user_by_email(email)
    if not user:
        return jsonify({"ok": True, "message": "If email exists, code sent."})
    code = gen_code()
    cm("auth:createReset", {"token": secrets.token_urlsafe(24),
                            "username": user["username"], "email": email, "code": code})
    send_email(email, "NOVEX AI — Reset", f"Code: {code}")
    return jsonify({"ok": True})


@app.route("/auth/reset", methods=["POST"])
def auth_reset():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    new_password = data.get("new_password") or ""
    if not check_rate_limit(f"reset:{get_client_ip()}", 6, 600):
        return jsonify({"error": "Too many."}), 429
    score, _, issues = password_strength(new_password)
    if score < 2:
        return jsonify({"error": "Password weak"}), 400
    entry = cq("auth:findReset", {"email": email, "code": code})
    if not entry:
        return jsonify({"error": "Galat/expired code"}), 400
    user = user_by_username(entry["username"])
    if not user:
        return jsonify({"error": "Not found"}), 404
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
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.get("email") or user["username"], issuer_name="NOVEX AI")
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
    user = user_by_username(current_user())
    if not user.get("password_hash"):
        return jsonify({"error": "No password"}), 400
    if not check_password_hash(user["password_hash"], data.get("password", "")):
        return jsonify({"error": "Galat password"}), 401
    cm("users:set2FA", {"id": user["_id"], "secret": None, "enabled": False})
    return jsonify({"ok": True})


@app.route("/auth/sessions", methods=["GET"])
@require_login
def auth_sessions():
    user = user_by_username(current_user())
    return jsonify({"sessions": cq("auth:getHistory", {"user_id": user["_id"]}) or []})


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
    user = user_by_username(current_user())
    if user.get("password_hash"):
        if not check_password_hash(user["password_hash"], data.get("old_password", "")):
            return jsonify({"error": "Galat purana password"}), 401
    score, _, issues = password_strength(data.get("new_password", ""))
    if score < 2:
        return jsonify({"error": "Password weak"}), 400
    cm("users:updatePassword", {"id": user["_id"],
                                "password_hash": generate_password_hash(data["new_password"])})
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


@app.route("/users/search", methods=["GET"])
@require_login
def users_search():
    q = (request.args.get("q") or "").strip().lower()
    if len(q) < 2:
        return jsonify({"users": []})
    me = user_by_username(current_user())
    result = cq("users:search", {"q": q, "me_id": me["_id"] if me else None}) or []
    return jsonify({"users": result})


# ============================================================
# SETTINGS / PERSONAS / PROJECTS / MEMORY
# ============================================================
@app.route("/settings", methods=["GET"])
@require_login
def get_settings():
    user = user_by_username(current_user())
    s = cq("misc:getSettings", {"user_id": user["_id"]})
    if not s:
        return jsonify({"custom_instructions": "",
                        "quiet_hours": {"enabled": False, "start": "22:00",
                                        "end": "07:00", "tz_offset": 5.5}})
    return jsonify({"custom_instructions": s.get("custom_instructions", ""),
                    "quiet_hours": s.get("quiet_hours", {"enabled": False, "start": "22:00",
                                                          "end": "07:00", "tz_offset": 5.5})})


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
        patch["quiet_hours"] = {"enabled": bool(qh.get("enabled", False)),
                                "start": str(qh.get("start", "22:00"))[:5],
                                "end": str(qh.get("end", "07:00"))[:5],
                                "tz_offset": float(qh.get("tz_offset", 5.5))}
    cm("misc:updateSettings", patch)
    return jsonify({"ok": True, "settings": patch})


@app.route("/personas", methods=["GET"])
@require_login
def list_personas():
    user = user_by_username(current_user())
    items = cq("misc:listPersonas", {"user_id": user["_id"]}) or []
    return jsonify({"personas": {p["slug"]: {"name": p["name"], "prompt": p["prompt"],
                                              "icon": p["icon"], "created": p["created"]}
                                  for p in items}})


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
    pid = cm("misc:createProject", {"user_id": user["_id"], "name": name, "color": color})
    return jsonify({"ok": True, "id": pid})


@app.route("/projects/<pid>", methods=["DELETE"])
@require_login
def delete_project(pid):
    cm("misc:deleteProject", {"project_id": pid})
    return jsonify({"ok": True})


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
    result = cm("misc:addMemory", {"user_id": user["_id"], "fact": fact, "source": "manual"})
    if not result.get("duplicate"):
        _increment_counter(user["_id"], "memory_count")
        _check_badges(user["_id"])
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
        result = cm("misc:addMemory", {"user_id": user["_id"], "fact": f, "source": "auto"})
        if not result.get("duplicate"):
            added.append(f)
            _increment_counter(user["_id"], "memory_count")
    if added:
        _check_badges(user["_id"])
    return jsonify({"ok": True, "added": added, "count": len(added)})


# ============================================================
# FLASHCARDS + SRS
# ============================================================
@app.route("/flashcards", methods=["GET"])
@require_login
def list_flashcards():
    user = user_by_username(current_user())
    items = cq("misc:listFlashcards", {"user_id": user["_id"]}) or []
    return jsonify({"decks": [{"id": d["_id"], "title": d["title"],
                               "cards": d["cards"], "created": d["created"],
                               "reviewed": d.get("reviewed", 0)} for d in items]})


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
            source = "\n\n".join(m.get("content", "") for m in c.get("messages", [])[-10:])
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
    _award_exp(user["_id"], "flashcard_deck_create")
    return jsonify({"ok": True, "deck": {"id": deck_id,
                                         "title": topic or "Flashcards",
                                         "cards": cards["cards"]}})


@app.route("/flashcards/<deck_id>", methods=["DELETE"])
@require_login
def delete_flashcards(deck_id):
    cm("misc:deleteFlashcardDeck", {"id": deck_id})
    return jsonify({"ok": True})


@app.route("/flashcards/srs/due", methods=["GET"])
@require_login
def srs_due_cards():
    user = user_by_username(current_user())
    decks = cq("misc:listFlashcards", {"user_id": user["_id"]}) or []
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    due = []
    for d in decks:
        for i, card in enumerate(d.get("cards", [])):
            nr = card.get("next_review") or 0
            if nr <= now_ms:
                due.append({"deck_id": d["_id"], "deck_title": d["title"],
                            "card_index": i, "front": card.get("front", ""),
                            "back": card.get("back", ""), "next_review": nr,
                            "repetitions": card.get("repetitions") or 0,
                            "interval_days": card.get("interval_days") or 0})
    due.sort(key=lambda x: x["next_review"])
    return jsonify({"due": due, "count": len(due)})


@app.route("/flashcards/srs/review", methods=["POST"])
@require_login
def srs_review_card():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    deck_id = data.get("deck_id")
    card_index = data.get("card_index")
    rating = int(data.get("rating", 2))
    if deck_id is None or card_index is None:
        return jsonify({"error": "deck_id and card_index required"}), 400
    if rating not in [0, 1, 2, 3]:
        return jsonify({"error": "rating must be 0-3"}), 400
    decks = cq("misc:listFlashcards", {"user_id": user["_id"]}) or []
    deck = next((d for d in decks if d["_id"] == deck_id), None)
    if not deck:
        return jsonify({"error": "Deck not found"}), 404
    cards = deck.get("cards", [])
    if card_index < 0 or card_index >= len(cards):
        return jsonify({"error": "Card index out of range"}), 400
    card = cards[card_index]
    result = nv.srs_next(ease_factor=card.get("ease_factor") or 2.5,
                         interval_days=card.get("interval_days") or 0,
                         repetitions=card.get("repetitions") or 0, rating=rating)
    card.update(result)
    cm("misc:updateFlashcardDeck", {"id": deck_id, "cards": cards,
                                    "reviewed": (deck.get("reviewed") or 0) + 1})
    _award_exp(user["_id"], "flashcard_review")
    _increment_counter(user["_id"], "flashcards_reviewed")
    _check_badges(user["_id"])
    return jsonify({"ok": True, "card": card, "next_review": result["next_review"]})


# ============================================================
# DOCS
# ============================================================
@app.route("/docs", methods=["GET"])
@require_login
def list_docs():
    user = user_by_username(current_user())
    return jsonify({"docs": cq("misc:listDocs", {"user_id": user["_id"]}) or []})


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
    doc_id = cm("misc:createDoc", {"user_id": user["_id"],
                                   "title": result.get("title", topic)[:80],
                                   "topic": topic, "style": style,
                                   "length": length, "language": language,
                                   "outline": result.get("outline", []),
                                   "content": result.get("content", "")})
    _award_exp(user["_id"], "doc_generate")
    _increment_counter(user["_id"], "docs_generated")
    _check_badges(user["_id"])
    return jsonify({"ok": True, "doc": {"id": doc_id,
                                        "title": result.get("title", topic),
                                        "content": result.get("content", "")}})


# ============================================================
# STATS / REMINDERS / MODELS
# ============================================================
@app.route("/stats", methods=["GET"])
@require_login
def stats():
    user = user_by_username(current_user())
    s = cq("misc:getStats", {"user_id": user["_id"]})
    if not s:
        return jsonify({"total_in": 0, "total_out": 0, "calls": 0, "models": {}})
    models = {m["model"]: {"in": m["in"], "out": m["out"], "calls": m["calls"]}
              for m in s.get("model_stats", [])}
    return jsonify({"total_in": s["total_in"], "total_out": s["total_out"],
                    "calls": s["calls"], "models": models})


def record_usage(uid, model, ti, to):
    try:
        cm("misc:recordUsage", {"user_id": uid, "model": model,
                                "tokens_in": ti, "tokens_out": to})
    except Exception as e:
        print(f"[record_usage] {e}", flush=True)


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
        return jsonify({"error": "when ISO format"}), 400
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


@app.route("/models", methods=["GET"])
@require_login
def models():
    return jsonify({"available": AVAILABLE_MODELS, "active": _active_model()})


@app.route("/set-model", methods=["POST"])
@require_login
def set_model_endpoint():
    data = request.get_json() or {}
    mid = data.get("model")
    if not mid:
        return jsonify({"error": "No model"}), 400
    _set_active_model(mid)
    return jsonify({"ok": True, "active": _active_model()})


# ============================================================
# UPLOAD / QUIZ v2 / SEARCH
# ============================================================
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


# 🎯 QUIZ v2 — categories, presets, stats
@app.route("/quiz/start", methods=["POST"])
@require_login
def quiz_start():
    data = request.get_json() or {}
    topic = (data.get("topic") or "General Knowledge").strip()
    difficulty = (data.get("difficulty") or "medium").strip().lower()
    count = data.get("count")
    if difficulty not in nv.DIFFICULTY_PRESETS:
        difficulty = "medium"
    preset = nv.DIFFICULTY_PRESETS[difficulty]
    if count is None:
        count = preset["count"]
    else:
        count = int(count)
        if count < 3:
            count = 3
        if count > 30:
            count = 30
    result = nv.generate_quiz_json(topic, difficulty, count)
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route("/quiz/categories", methods=["GET"])
@require_login
def quiz_categories():
    return jsonify({
        "categories": [{"name": k, "icon": v} for k, v in nv.QUIZ_CATEGORIES.items()],
        "difficulties": list(nv.DIFFICULTY_PRESETS.keys()),
        "presets": nv.DIFFICULTY_PRESETS,
    })


@app.route("/quiz/complete", methods=["POST"])
@require_login
def quiz_complete():
    """Award XP + badges for quiz completion."""
    user = user_by_username(current_user())
    data = request.get_json() or {}
    score = int(data.get("score", 0))
    total = int(data.get("total", 0))
    difficulty = (data.get("difficulty") or "medium").lower()
    max_streak = int(data.get("max_streak", 0))

    multiplier = nv.DIFFICULTY_PRESETS.get(difficulty, {}).get("xp", 1.0)
    base_xp = 25 + score * 10
    total_xp = int(base_xp * multiplier)

    # Bonus XP
    if total > 0 and score == total:
        total_xp += nv.EXP_REWARDS.get("quiz_perfect", 50)
    if max_streak >= 10:
        total_xp += nv.EXP_REWARDS.get("quiz_streak_10", 75)
    elif max_streak >= 5:
        total_xp += nv.EXP_REWARDS.get("quiz_streak_5", 30)

    try:
        p = _get_or_create_progress(user["_id"])
        new_exp = (p.get("exp") or 0) + total_xp
        lvl = nv.calculate_level(new_exp)
        cm("misc:updateProgress", {"user_id": user["_id"], "exp": new_exp,
                                   "level": lvl["level"], "level_icon": lvl["icon"]})
        cm("misc:logExp", {"user_id": user["_id"], "action": "quiz_complete",
                           "exp_gained": total_xp,
                           "meta": f"{score}/{total} {difficulty}"})
        _increment_counter(user["_id"], "quiz_count")
        if total > 0 and score == total:
            _increment_counter(user["_id"], "perfect_quizzes")
        _check_badges(user["_id"])
    except Exception as e:
        print(f"[quiz_complete] {e}", flush=True)

    return jsonify({
        "ok": True,
        "exp_gained": total_xp,
        "multiplier": multiplier,
        "score": score,
        "total": total,
    })


@app.route("/search", methods=["POST"])
@require_login
def web_search_endpoint():
    data = request.get_json() or {}
    q = (data.get("q") or "").strip()
    max_results = int(data.get("max_results") or 6)
    if not q:
        return jsonify({"error": "Query chahiye"}), 400
    if max_results > 20:
        max_results = 20
    try:
        results = nv.web_search_structured(q, max_results=max_results)
        return jsonify({"ok": True, "query": q, "results": results,
                        "provider": nv._last_search_provider,
                        "count": len(results)})
    except Exception as e:
        print(f"[search endpoint] {e}", flush=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/search/providers", methods=["GET"])
@require_login
def search_providers():
    return jsonify({
        "providers": {
            "serper": bool(os.getenv("SERPER_API_KEY")),
            "ddgs": True,
        },
        "default": os.getenv("SEARCH_DEFAULT_PROVIDER", "serper"),
        "max_results": int(os.getenv("SEARCH_MAX_RESULTS", "6")),
        "region": os.getenv("SEARCH_REGION", "in-en"),
    })


# ============================================================
# DOUBT SCANNER
# ============================================================
@app.route("/doubt-scanner", methods=["POST"])
@require_login
def doubt_scanner():
    user = user_by_username(current_user())
    if not user:
        return jsonify({"error": "User not found"}), 401
    if "file" in request.files:
        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "Empty file"}), 400
        uid = uuid.uuid4().hex[:8]
        path = os.path.join(UPLOADS_DIR, f"{uid}_{f.filename}")
        f.save(path)
        question = (request.form.get("question") or "").strip()
        language = (request.form.get("language") or "hinglish").strip()
    else:
        data = request.get_json() or {}
        path = (data.get("path") or "").strip()
        question = (data.get("question") or "").strip()
        language = (data.get("language") or "hinglish").strip()
        if not path or not os.path.exists(path):
            return jsonify({"error": "Image path invalid"}), 400
    answer = nv.solve_image(path, question, language)
    chat_id = cm("chats:create", {"user_id": user["_id"],
                                  "title": f"📸 {question[:40] or os.path.basename(path)[:40]}"})
    cm("chats:appendMessage", {"chat_id": chat_id, "role": "user",
                               "content": f"📸 [Image: {os.path.basename(path)}]\n{question}"})
    cm("chats:appendMessage", {"chat_id": chat_id, "role": "assistant", "content": answer})
    _award_exp(user["_id"], "doubt_scanner")
    _increment_counter(user["_id"], "doubts_solved")
    _check_badges(user["_id"])
    return jsonify({"ok": True, "answer": answer, "chat_id": chat_id})


# ============================================================
# GAMIFICATION
# ============================================================
@app.route("/gamification/profile", methods=["GET"])
@require_login
def gamification_profile():
    user = user_by_username(current_user())
    p = _get_or_create_progress(user["_id"])
    badges = cq("misc:listBadges", {"user_id": user["_id"]}) or []
    lvl = nv.calculate_level(p.get("exp") or 0)
    have = {b["badge_id"] for b in badges}
    all_badges = [{"id": bid, "icon": icon, "name": name,
                   "desc": desc, "unlocked": bid in have}
                  for bid, (icon, name, desc) in nv.BADGES.items()]
    return jsonify({
        "exp": p.get("exp") or 0, "level": lvl["level"], "level_icon": lvl["icon"],
        "progress_pct": lvl["progress_pct"],
        "next_level": lvl.get("next_level"), "next_at": lvl.get("next_at"),
        "stats": {
            "quiz_count": p.get("quiz_count") or 0,
            "perfect_quizzes": p.get("perfect_quizzes") or 0,
            "flashcards_reviewed": p.get("flashcards_reviewed") or 0,
            "docs_generated": p.get("docs_generated") or 0,
            "pomodoros_done": p.get("pomodoros_done") or 0,
            "doubts_solved": p.get("doubts_solved") or 0,
            "memory_count": p.get("memory_count") or 0,
        },
        "badges": all_badges,
        "unlocked_count": len(have),
        "total_badges": len(nv.BADGES),
    })


@app.route("/gamification/award", methods=["POST"])
@require_login
def gamification_award():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    action = (data.get("action") or "").strip()
    if action not in nv.EXP_REWARDS:
        return jsonify({"error": "Unknown action"}), 400
    _award_exp(user["_id"], action, (data.get("meta") or "").strip())
    _check_badges(user["_id"])
    return jsonify({"ok": True})


# ============================================================
# BATCH 1 — Study Tools+
# ============================================================
@app.route("/formula-sheet/generate", methods=["POST"])
@require_login
def formula_sheet_generate():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    subject = (data.get("subject") or "Physics").strip()
    chapters = data.get("chapters") or []
    board = (data.get("board") or "CBSE").strip()
    result = nv.generate_formula_sheet(subject, chapters, board)
    if "error" in result:
        return jsonify(result), 500
    fid = cm("misc:createFormulaSheet", {"user_id": user["_id"], "subject": subject,
                                          "chapters": chapters, "content": result["content"]})
    _award_exp(user["_id"], "doc_generate")
    return jsonify({"ok": True, "id": fid, **result})


@app.route("/formula-sheets", methods=["GET"])
@require_login
def list_formula_sheets():
    user = user_by_username(current_user())
    items = cq("misc:listFormulaSheets", {"user_id": user["_id"]}) or []
    return jsonify({"sheets": items})


@app.route("/formula-sheets/<sid>", methods=["DELETE"])
@require_login
def delete_formula_sheet(sid):
    cm("misc:deleteFormulaSheet", {"id": sid})
    return jsonify({"ok": True})


@app.route("/mind-map/generate", methods=["POST"])
@require_login
def mind_map_generate():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "Topic required"}), 400
    depth = int(data.get("depth") or 3)
    result = nv.generate_mind_map(topic, depth)
    if "error" in result:
        return jsonify(result), 500
    mid = cm("misc:createMindMap", {"user_id": user["_id"], "title": topic,
                                     "source": topic, "markdown": result["markdown"]})
    _award_exp(user["_id"], "doc_generate")
    return jsonify({"ok": True, "id": mid, **result})


@app.route("/mind-maps", methods=["GET"])
@require_login
def list_mind_maps():
    user = user_by_username(current_user())
    items = cq("misc:listMindMaps", {"user_id": user["_id"]}) or []
    return jsonify({"maps": items})


@app.route("/mind-maps/<mid>", methods=["DELETE"])
@require_login
def delete_mind_map(mid):
    cm("misc:deleteMindMap", {"id": mid})
    return jsonify({"ok": True})


@app.route("/weak-topics/analyze", methods=["GET"])
@require_login
def weak_topics_analyze():
    user = user_by_username(current_user())
    attempts = cq("progress:listQuizAttempts", {"user_id": user["_id"], "limit": 200}) or []
    weak = nv.analyze_weak_topics(attempts)
    return jsonify({"weak": weak, "total_attempts": len(attempts)})


@app.route("/podcast/generate", methods=["POST"])
@require_login
def podcast_generate():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    source = (data.get("source") or "").strip()
    title = (data.get("title") or "Study Podcast").strip()
    lang = (data.get("language") or "hinglish").strip()
    chat_id = data.get("chat_id")
    if chat_id and not source:
        c = cq("chats:getById", {"id": chat_id, "viewer_id": user["_id"]})
        if c:
            source = "\n".join(m.get("content", "") for m in c.get("messages", [])[-8:])
    if not source:
        return jsonify({"error": "Source text required"}), 400
    result = nv.generate_podcast_script(source[:3000], title, lang)
    if "error" in result:
        return jsonify(result), 500
    pid = cm("misc:createPodcast", {"user_id": user["_id"], "title": result["title"],
                                     "source_text": source[:3000],
                                     "script_json": json.dumps(result["lines"]),
                                     "audio_url": "",
                                     "duration_sec": len(result["lines"]) * 10})
    _award_exp(user["_id"], "doc_generate")
    return jsonify({"ok": True, "id": pid, **result})


@app.route("/podcasts", methods=["GET"])
@require_login
def list_podcasts():
    user = user_by_username(current_user())
    items = cq("misc:listPodcasts", {"user_id": user["_id"]}) or []
    return jsonify({"podcasts": items})


@app.route("/podcasts/<pid>", methods=["DELETE"])
@require_login
def delete_podcast(pid):
    cm("misc:deletePodcast", {"id": pid})
    return jsonify({"ok": True})


@app.route("/debate/start", methods=["POST"])
@require_login
def debate_start():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    topic = (data.get("topic") or "").strip()
    rounds = int(data.get("rounds") or 5)
    if not topic:
        return jsonify({"error": "Topic required"}), 400
    did = cm("misc:createDebate", {"user_id": user["_id"], "topic": topic, "rounds": rounds})
    return jsonify({"ok": True, "debate_id": did, "topic": topic})


@app.route("/debate/round", methods=["POST"])
@require_login
def debate_round():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    did = data.get("debate_id")
    topic = (data.get("topic") or "").strip()
    round_num = int(data.get("round") or 1)
    history = data.get("history") or []
    if not did or not topic:
        return jsonify({"error": "debate_id and topic required"}), 400
    arg_a = nv.debate_generate(topic, round_num, history, "A")
    hist_with_a = history + [{"speaker": "A", "content": arg_a}]
    arg_b = nv.debate_generate(topic, round_num, hist_with_a, "B")
    cm("misc:appendDebateMessage", {"debate_id": did, "speaker": "A", "content": arg_a})
    cm("misc:appendDebateMessage", {"debate_id": did, "speaker": "B", "content": arg_b})
    return jsonify({"ok": True, "arg_a": arg_a, "arg_b": arg_b})


@app.route("/debate/verdict", methods=["POST"])
@require_login
def debate_verdict_ep():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    did = data.get("debate_id")
    topic = data.get("topic", "")
    history = data.get("history") or []
    verdict = nv.debate_verdict(topic, history)
    if did:
        cm("misc:setDebateVerdict", {"debate_id": did, "verdict": verdict})
    return jsonify({"ok": True, "verdict": verdict})


@app.route("/written-test/generate", methods=["POST"])
@require_login
def written_test_generate():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    topic = (data.get("topic") or "").strip()
    qtype = (data.get("qtype") or "fill_blank").strip()
    count = int(data.get("count") or 5)
    if not topic:
        return jsonify({"error": "Topic required"}), 400
    result = nv.generate_written_test(topic, qtype, count)
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route("/mock-test/generate", methods=["POST"])
@require_login
def mock_test_generate():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    exam = (data.get("exam") or "JEE Main").strip()
    subjects = data.get("subjects") or ["Physics", "Chemistry", "Mathematics"]
    count = int(data.get("count") or 10)
    difficulty = (data.get("difficulty") or "medium").strip()
    result = nv.generate_mock_test(exam, subjects, count, difficulty)
    if "error" in result:
        return jsonify(result), 500
    tid = cm("misc:createMockTest", {"user_id": user["_id"], "exam": exam,
                                      "subjects": subjects,
                                      "duration_min": result.get("duration_min", count * 2),
                                      "total_questions": count,
                                      "questions_json": json.dumps(result.get("questions", []))})
    return jsonify({"ok": True, "id": tid, **result})


@app.route("/mock-test/<tid>/submit", methods=["POST"])
@require_login
def mock_test_submit(tid):
    user = user_by_username(current_user())
    data = request.get_json() or {}
    answers = data.get("answers") or []
    time_taken = int(data.get("time_taken") or 0)
    test = cq("misc:getMockTest", {"id": tid})
    if not test:
        return jsonify({"error": "Not found"}), 404
    try:
        questions = json.loads(test["questions_json"])
    except Exception:
        return jsonify({"error": "Invalid test"}), 400
    correct = wrong = unattempted = total_marks = 0
    subject_stats = {}
    for i, q in enumerate(questions):
        subj = q.get("subject", "General")
        subject_stats.setdefault(subj, {"correct": 0, "wrong": 0, "total": 0})
        subject_stats[subj]["total"] += 1
        ans = next((a for a in answers if a.get("idx") == i), None)
        marks = q.get("marks", 4)
        neg = q.get("negative", 1)
        if not ans or not ans.get("choice"):
            unattempted += 1
            continue
        if ans.get("choice") == q.get("answer"):
            correct += 1
            total_marks += marks
            subject_stats[subj]["correct"] += 1
        else:
            wrong += 1
            total_marks -= neg
            subject_stats[subj]["wrong"] += 1
    analysis = {"subject_stats": subject_stats, "correct": correct,
                "wrong": wrong, "unattempted": unattempted}
    cm("misc:submitMockTest", {"id": tid, "score": total_marks,
                                "analysis_json": json.dumps(analysis)})
    _award_exp(user["_id"], "quiz_complete")
    _increment_counter(user["_id"], "quiz_count")
    _check_badges(user["_id"])
    return jsonify({"ok": True, "score": total_marks, "analysis": analysis})


@app.route("/mock-tests", methods=["GET"])
@require_login
def list_mock_tests():
    user = user_by_username(current_user())
    items = cq("misc:listMockTests", {"user_id": user["_id"]}) or []
    return jsonify({"tests": items})


@app.route("/parent-report/generate", methods=["POST"])
@require_login
def parent_report_generate():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    parent_email = (data.get("parent_email") or "").strip()
    period = (data.get("period") or "weekly").strip()
    attempts = cq("progress:listQuizAttempts", {"user_id": user["_id"], "limit": 50}) or []
    progress = cq("misc:getProgress", {"user_id": user["_id"]}) or {}
    weak = nv.analyze_weak_topics(attempts)
    total_q = sum(a.get("total", 0) for a in attempts)
    total_c = sum(a.get("score", 0) for a in attempts)
    avg = round((total_c / total_q) * 100) if total_q else 0
    content = f"📊 **{user.get('display_name', user['username'])} — {period.capitalize()} Report**\n\n"
    content += f"- 🎯 **Level:** {progress.get('level', 'Beginner')} ({progress.get('exp', 0)} EXP)\n"
    content += f"- 📝 **Quizzes:** {len(attempts)} attempts, avg {avg}%\n"
    content += f"- 📚 **Flashcards:** {progress.get('flashcards_reviewed', 0)} reviewed\n"
    content += f"- 📸 **Doubts Solved:** {progress.get('doubts_solved', 0)}\n"
    content += f"- ⏱️ **Focus Sessions:** {progress.get('pomodoros_done', 0)}\n\n"
    if weak:
        content += "⚠️ **Weak Topics:**\n"
        for w in weak[:5]:
            content += f"- {w['topic']} — {w['accuracy']}%\n"
    else:
        content += "✅ No weak topics detected. Great work!\n"
    content += "\n— NOVEX AI"
    rid = cm("misc:createParentReport", {"user_id": user["_id"], "parent_email": parent_email,
                                          "period": period, "content": content, "sent": False})
    return jsonify({"ok": True, "id": rid, "content": content})


@app.route("/parent-report/send", methods=["POST"])
@require_login
def parent_report_send():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    rid = data.get("report_id")
    if not rid:
        return jsonify({"error": "report_id required"}), 400
    report = cq("misc:getParentReport", {"id": rid})
    if not report:
        return jsonify({"error": "Not found"}), 404
    if report.get("parent_email"):
        send_email(report["parent_email"], "NOVEX AI — Student Progress Report",
                   report.get("content", ""))
        cm("misc:markParentReportSent", {"id": rid})
    return jsonify({"ok": True})


# ============================================================
# BATCH 2 — Voice Tutor / Rooms / Avatar / Peer Doubts
# ============================================================
@app.route("/voice/tutor/start", methods=["POST"])
@require_login
def voice_tutor_start():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    topic = (data.get("topic") or "General").strip()
    sid = cm("misc:createVoiceSession", {"user_id": user["_id"], "topic": topic})
    return jsonify({"ok": True, "session_id": sid, "topic": topic})


@app.route("/voice/tutor/message", methods=["POST"])
@require_login
def voice_tutor_message():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    sid = data.get("session_id")
    speech = (data.get("speech") or "").strip()
    if not sid or not speech:
        return jsonify({"error": "session_id and speech required"}), 400
    session_data = cq("misc:getVoiceSession", {"id": sid})
    history = []
    if session_data:
        history = [{"role": m["role"], "content": m["content"]}
                   for m in session_data.get("messages", [])]
    result = nv.voice_tutor_reply(
        session_data.get("topic", "General") if session_data else "General",
        speech, history)
    if "error" in result:
        return jsonify(result), 500
    cm("misc:appendVoiceMessage", {"session_id": sid, "role": "user", "content": speech})
    cm("misc:appendVoiceMessage", {"session_id": sid, "role": "tutor", "content": result["reply"]})
    _award_exp(user["_id"], "chat_message")
    return jsonify({"ok": True, "reply": result["reply"]})


@app.route("/voice/tutor/stop", methods=["POST"])
@require_login
def voice_tutor_stop():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    sid = data.get("session_id")
    if sid:
        cm("misc:endVoiceSession", {"session_id": sid})
    _award_exp(user["_id"], "quiz_complete")
    return jsonify({"ok": True})


@app.route("/rooms/create", methods=["POST"])
@require_login
def rooms_create():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    topic = (data.get("topic") or "General Knowledge").strip()
    difficulty = (data.get("difficulty") or "medium").strip()
    count = int(data.get("count") or 10)
    questions = nv.generate_room_questions(topic, difficulty, count)
    if not questions:
        return jsonify({"error": "Could not generate questions"}), 500
    code = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=6))
    rid = cm("misc:createStudyRoom", {
        "host_id": user["_id"], "host_name": user.get("display_name", user["username"]),
        "room_code": code, "topic": topic, "difficulty": difficulty,
        "question_count": count, "questions_json": json.dumps(questions),
        "avatar": (user.get("display_name") or "U")[0].upper(),
    })
    return jsonify({"ok": True, "room_id": rid, "room_code": code,
                    "topic": topic, "count": len(questions)})


@app.route("/rooms/join", methods=["POST"])
@require_login
def rooms_join():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "Room code required"}), 400
    room = cq("misc:getRoomByCode", {"code": code})
    if not room:
        return jsonify({"error": "Room not found"}), 404
    if room.get("status") == "finished":
        return jsonify({"error": "Room ended"}), 400
    result = cm("misc:joinStudyRoom", {"room_id": room["_id"], "user_id": user["_id"],
                                        "username": user["username"],
                                        "display_name": user.get("display_name", user["username"]),
                                        "avatar": (user.get("display_name") or "U")[0].upper()})
    return jsonify({"ok": True, "room_id": room["_id"], **result})


@app.route("/rooms/<rid>", methods=["GET"])
@require_login
def rooms_get(rid):
    room = cq("misc:getStudyRoom", {"id": rid})
    if not room:
        return jsonify({"error": "Not found"}), 404
    return jsonify(room)


@app.route("/rooms/<rid>/start", methods=["POST"])
@require_login
def rooms_start(rid):
    user = user_by_username(current_user())
    room = cq("misc:getStudyRoom", {"id": rid})
    if not room:
        return jsonify({"error": "Not found"}), 404
    if room.get("host_id") != user["_id"]:
        return jsonify({"error": "Only host can start"}), 403
    cm("misc:startStudyRoom", {"room_id": rid})
    return jsonify({"ok": True})


@app.route("/rooms/<rid>/answer", methods=["POST"])
@require_login
def rooms_answer(rid):
    user = user_by_username(current_user())
    data = request.get_json() or {}
    idx = int(data.get("idx") or 0)
    choice = (data.get("choice") or "").strip().upper()
    time_ms = int(data.get("time_ms") or 0)
    result = cm("misc:submitRoomAnswer", {"room_id": rid, "user_id": user["_id"],
                                            "idx": idx, "choice": choice, "time_ms": time_ms})
    return jsonify({"ok": True, **result})


@app.route("/rooms/<rid>/next", methods=["POST"])
@require_login
def rooms_next(rid):
    user = user_by_username(current_user())
    room = cq("misc:getStudyRoom", {"id": rid})
    if not room:
        return jsonify({"error": "Not found"}), 404
    if room.get("host_id") != user["_id"]:
        return jsonify({"error": "Only host"}), 403
    result = cm("misc:nextRoomQuestion", {"room_id": rid})
    return jsonify({"ok": True, **result})


@app.route("/rooms/<rid>/leave", methods=["POST"])
@require_login
def rooms_leave(rid):
    user = user_by_username(current_user())
    cm("misc:leaveStudyRoom", {"room_id": rid, "user_id": user["_id"]})
    return jsonify({"ok": True})


@app.route("/avatar/me", methods=["GET"])
@require_login
def avatar_get():
    user = user_by_username(current_user())
    av = cq("misc:getAvatar", {"user_id": user["_id"]})
    if not av:
        cm("misc:createAvatar", {"user_id": user["_id"]})
        av = cq("misc:getAvatar", {"user_id": user["_id"]})
    unlocks = cq("misc:listUnlocks", {"user_id": user["_id"]}) or []
    return jsonify({"avatar": av, "unlocks": unlocks})


@app.route("/avatar/update", methods=["POST"])
@require_login
def avatar_update():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    patch = {}
    for k in ("emoji", "color", "bg_pattern", "equipped"):
        if k in data:
            patch[k] = str(data[k])[:30]
    cm("misc:updateAvatar", {"user_id": user["_id"], **patch})
    return jsonify({"ok": True})


@app.route("/avatar/unlock", methods=["POST"])
@require_login
def avatar_unlock():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    item_id = (data.get("item_id") or "").strip()
    item_type = (data.get("item_type") or "accessory").strip()
    if not item_id:
        return jsonify({"error": "item_id required"}), 400
    result = cm("misc:unlockItem", {"user_id": user["_id"], "item_id": item_id,
                                     "item_type": item_type})
    return jsonify({"ok": True, **result})


@app.route("/peer-doubts", methods=["GET"])
@require_login
def peer_doubts_list():
    subject = request.args.get("subject", "")
    status = request.args.get("status", "open")
    items = cq("misc:listPeerDoubts", {"subject": subject, "status": status}) or []
    return jsonify({"doubts": items[:50]})


@app.route("/peer-doubts", methods=["POST"])
@require_login
def peer_doubts_create():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    subject = (data.get("subject") or "General").strip()
    topic = (data.get("topic") or "").strip()
    image_url = (data.get("image_url") or "").strip()
    if not title or not body:
        return jsonify({"error": "Title aur body required"}), 400
    payload = {"user_id": user["_id"], "username": user["username"],
               "display_name": user.get("display_name", user["username"]),
               "avatar": (user.get("display_name") or "U")[0].upper(),
               "title": title[:200], "body": body[:3000],
               "subject": subject, "topic": topic}
    if image_url:
        payload["image_url"] = image_url
    did = cm("misc:createPeerDoubt", payload)
    _award_exp(user["_id"], "chat_message")
    return jsonify({"ok": True, "id": did})


@app.route("/peer-doubts/<did>/answer", methods=["POST"])
@require_login
def peer_doubts_answer(did):
    user = user_by_username(current_user())
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Answer required"}), 400
    doubt = cq("misc:getPeerDoubt", {"id": did})
    if not doubt:
        return jsonify({"error": "Not found"}), 404
    ai = nv.verify_peer_answer(doubt.get("title", ""), content, doubt.get("subject", "General"))
    result = cm("misc:addPeerAnswer", {"doubt_id": did, "user_id": user["_id"],
                                        "username": user["username"],
                                        "display_name": user.get("display_name", user["username"]),
                                        "avatar": (user.get("display_name") or "U")[0].upper(),
                                        "content": content[:3000],
                                        "is_verified": bool(ai.get("is_correct", False)),
                                        "ai_rating": int(ai.get("rating", 3))})
    if ai.get("is_correct"):
        _award_exp(user["_id"], "quiz_correct")
    return jsonify({"ok": True, "ai_feedback": ai, **result})


@app.route("/peer-doubts/<did>/upvote", methods=["POST"])
@require_login
def peer_doubts_upvote(did):
    cm("misc:upvotePeerDoubt", {"doubt_id": did})
    return jsonify({"ok": True})


@app.route("/peer-doubts/<did>/solve", methods=["POST"])
@require_login
def peer_doubts_solve(did):
    user = user_by_username(current_user())
    data = request.get_json() or {}
    idx = data.get("answer_idx")
    doubt = cq("misc:getPeerDoubt", {"id": did})
    if not doubt:
        return jsonify({"error": "Not found"}), 404
    if doubt.get("user_id") != user["_id"]:
        return jsonify({"error": "Only asker can mark solved"}), 403
    cm("misc:markDoubtSolved", {"doubt_id": did, "answer_idx": idx})
    return jsonify({"ok": True})


@app.route("/preferences", methods=["GET"])
@require_login
def prefs_get():
    user = user_by_username(current_user())
    p = cq("misc:getPreferences", {"user_id": user["_id"]})
    if not p:
        cm("misc:createPreferences", {"user_id": user["_id"]})
        p = cq("misc:getPreferences", {"user_id": user["_id"]})
    return jsonify(p or {})


@app.route("/preferences", methods=["POST"])
@require_login
def prefs_update():
    user = user_by_username(current_user())
    data = request.get_json() or {}
    patch = {}
    for k in ("ui_language", "ai_language"):
        if k in data:
            patch[k] = str(data[k])[:10]
    for k in ("voice_enabled", "auto_speak", "notifications"):
        if k in data:
            patch[k] = bool(data[k])
    if "voice_speed" in data:
        patch["voice_speed"] = max(0.5, min(2.0, float(data["voice_speed"])))
    cm("misc:updatePreferences", {"user_id": user["_id"], **patch})
    return jsonify({"ok": True})


@app.route("/transcribe", methods=["POST"])
@require_login
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400
    f = request.files["audio"]
    uid = uuid.uuid4().hex[:8]
    ext = os.path.splitext(f.filename)[1] or ".webm"
    path = os.path.join(UPLOADS_DIR, f"voice_{uid}{ext}")
    f.save(path)
    text = nv.transcribe_audio_whisper(path)
    try:
        os.remove(path)
    except Exception:
        pass
    return jsonify({"ok": True, "text": text})


# ============================================================
# LINGUA
# ============================================================
@app.route("/languages/all", methods=["GET"])
def lingua_all_langs():
    from_lang = (request.args.get("from") or "en").strip()
    all_langs = cq("language:listLanguages", {"from_lang": from_lang}) or []
    learners = ["en", "hi", "ta", "te", "bn", "mr", "pa", "gu", "kn", "ml", "ur"]
    return jsonify({"from_lang": from_lang, "learnable": all_langs,
                    "learner_languages": learners})


@app.route("/languages/from/<from_code>", methods=["GET"])
def lingua_langs_from(from_code):
    langs = cq("language:listLanguages", {"from_lang": from_code}) or []
    return jsonify({"from_lang": from_code, "languages": langs})


@app.route("/languages/<code>/units", methods=["GET"])
@require_login
def lingua_units(code):
    from_lang = (request.args.get("from") or "en").strip()
    units = cq("language:listUnits", {"language_code": code, "from_lang": from_lang}) or []
    return jsonify({"units": units})


@app.route("/languages/<code>/progress", methods=["GET"])
@require_login
def lingua_progress(code):
    user = user_by_username(current_user())
    p = cq("language:getUserProgress", {"user_id": user["_id"], "language_code": code})
    return jsonify(p or {"current_unit": 1, "current_lesson": 1, "total_xp": 0,
                          "daily_streak": 0, "lessons_completed": 0, "words_learned": 0})


@app.route("/languages/<code>/units/<unit_id>/lessons/<int:lesson_num>", methods=["GET"])
@require_login
def lingua_get_lesson(code, unit_id, lesson_num):
    from_lang = (request.args.get("from") or "en").strip()
    units = cq("language:listUnits", {"language_code": code, "from_lang": from_lang}) or []
    unit_title = "Basics"
    for u in units:
        if u["_id"] == unit_id:
            unit_title = u["title"]
            break
    existing = cq("language:getLesson", {"unit_id": unit_id, "lesson_number": lesson_num})
    if existing:
        try:
            data = json.loads(existing["exercises_json"])
            return jsonify({"ok": True, "lesson": {"id": existing["_id"],
                                                    "title": existing["title"], **data}})
        except Exception:
            pass
    lesson_data = nv.generate_lesson(target_lang=code, from_lang=from_lang,
                                      unit_title=unit_title,
                                      lesson_title=f"Lesson {lesson_num}",
                                      level="A1", count=12)
    if "error" in lesson_data:
        return jsonify({"error": lesson_data["error"]}), 500
    lid = cm("language:saveLesson", {"language_code": code, "unit_id": unit_id,
                                      "lesson_number": lesson_num,
                                      "title": lesson_data.get("title", f"Lesson {lesson_num}"),
                                      "exercises_json": json.dumps(lesson_data)})
    return jsonify({"ok": True, "lesson": {"id": lid, **lesson_data}})


@app.route("/languages/<code>/lessons/<lesson_id>/complete", methods=["POST"])
@require_login
def lingua_complete_lesson(code, lesson_id):
    user = user_by_username(current_user())
    data = request.get_json() or {}
    score = int(data.get("score", 0))
    total = int(data.get("total", 1))
    unit_number = int(data.get("unit_number", 1))
    lesson_number = int(data.get("lesson_number", 1))
    time_taken = int(data.get("time_taken", 0))
    mistakes = data.get("mistakes", [])
    vocab_learned = data.get("vocab", [])
    pct = int((score / total) * 100) if total else 0
    xp = 10 + score * 2 + (20 if pct == 100 else 0)
    cm("language:recordAttempt", {"user_id": user["_id"], "language_code": code,
                                   "lesson_id": lesson_id, "unit_number": unit_number,
                                   "lesson_number": lesson_number,
                                   "score": score, "total": total, "time_taken": time_taken,
                                   "mistakes_json": json.dumps(mistakes), "xp_gained": xp})
    result = cm("language:upsertProgress", {"user_id": user["_id"], "language_code": code,
                                             "from_lang": "en",
                                             "current_unit": unit_number,
                                             "current_lesson": lesson_number + 1,
                                             "xp_delta": xp, "lessons_delta": 1,
                                             "words_delta": len(vocab_learned)})
    if vocab_learned:
        cm("language:bulkAddVocab", {"user_id": user["_id"], "language_code": code,
                                      "words": [{"word": v.get("word", ""),
                                                 "translation": v.get("translation", ""),
                                                 "example": v.get("example", "")}
                                                for v in vocab_learned],
                                      "source": "lesson"})
    _award_exp(user["_id"], "language_lesson")
    _check_badges(user["_id"])
    return jsonify({"ok": True, "xp_gained": xp, "streak": result.get("streak", 1)})


@app.route("/languages/<code>/vocab", methods=["GET"])
@require_login
def lingua_vocab(code):
    user = user_by_username(current_user())
    items = cq("language:listVocab", {"user_id": user["_id"], "language_code": code}) or []
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    due = [v for v in items if (v.get("next_review") or 0) <= now_ms]
    return jsonify({"vocab": items, "due_count": len(due), "total": len(items)})


@app.route("/languages/<code>/vocab/due", methods=["GET"])
@require_login
def lingua_vocab_due(code):
    user = user_by_username(current_user())
    items = cq("language:listVocab", {"user_id": user["_id"], "language_code": code}) or []
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    due = [v for v in items if (v.get("next_review") or 0) <= now_ms]
    due.sort(key=lambda x: x.get("next_review", 0))
    return jsonify({"due": due[:20], "total_due": len(due)})


@app.route("/languages/<code>/vocab/review", methods=["POST"])
@require_login
def lingua_vocab_review(code):
    user = user_by_username(current_user())
    data = request.get_json() or {}
    vocab_id = data.get("vocab_id")
    rating = int(data.get("rating", 2))
    if not vocab_id:
        return jsonify({"error": "vocab_id required"}), 400
    items = cq("language:listVocab", {"user_id": user["_id"], "language_code": code}) or []
    card = next((v for v in items if v["_id"] == vocab_id), None)
    if not card:
        return jsonify({"error": "Not found"}), 404
    result = nv.srs_next(ease_factor=card.get("ease_factor") or 2.5,
                          interval_days=card.get("interval_days") or 0,
                          repetitions=card.get("repetitions") or 0, rating=rating)
    cm("language:updateVocabSRS", {"id": vocab_id, **result})
    _award_exp(user["_id"], "language_review")
    _check_badges(user["_id"])
    return jsonify({"ok": True, "next_review": result["next_review"]})


@app.route("/languages/<code>/vocab/add", methods=["POST"])
@require_login
def lingua_vocab_add(code):
    user = user_by_username(current_user())
    data = request.get_json() or {}
    word = (data.get("word") or "").strip()
    translation = (data.get("translation") or "").strip()
    if not word or not translation:
        return jsonify({"error": "word aur translation required"}), 400
    result = cm("language:addVocab", {"user_id": user["_id"], "language_code": code,
                                       "word": word, "translation": translation,
                                       "example": data.get("example", ""), "source": "custom"})
    return jsonify({"ok": True, "id": result.get("id"),
                    "duplicate": result.get("duplicate", False)})


@app.route("/languages/<code>/vocab/<vocab_id>", methods=["DELETE"])
@require_login
def lingua_vocab_delete(code, vocab_id):
    cm("language:deleteVocab", {"id": vocab_id})
    return jsonify({"ok": True})


@app.route("/languages/<code>/vocab/extract", methods=["POST"])
@require_login
def lingua_vocab_extract(code):
    user = user_by_username(current_user())
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    words = nv.extract_vocab_from_text(text, code, "en", 20)
    if not words:
        return jsonify({"error": "Could not extract"}), 500
    result = cm("language:bulkAddVocab", {"user_id": user["_id"], "language_code": code,
                                            "words": words, "source": "custom"})
    return jsonify({"ok": True, "added": result.get("added", 0),
                    "skipped": result.get("skipped", 0), "words": words})


@app.route("/languages/<code>/chat/start", methods=["POST"])
@require_login
def lingua_chat_start(code):
    user = user_by_username(current_user())
    data = request.get_json() or {}
    scenario = (data.get("scenario") or "casual conversation").strip()
    cid = cm("language:createConvo", {"user_id": user["_id"], "language_code": code,
                                        "scenario": scenario})
    return jsonify({"ok": True, "convo_id": cid})


@app.route("/languages/<code>/chat/message", methods=["POST"])
@require_login
def lingua_chat_message(code):
    user = user_by_username(current_user())
    data = request.get_json() or {}
    convo_id = data.get("convo_id")
    message = (data.get("message") or "").strip()
    if not convo_id or not message:
        return jsonify({"error": "convo_id and message required"}), 400
    convo = cq("language:getConvo", {"id": convo_id})
    if not convo:
        return jsonify({"error": "Convo not found"}), 404
    history = [{"role": m["role"], "content": m["content"]} for m in convo.get("messages", [])]
    result = nv.language_chat(code, message, convo.get("scenario", ""), history)
    cm("language:appendConvoMessage", {"convo_id": convo_id, "role": "user", "content": message})
    msg_payload = {"convo_id": convo_id, "role": "assistant",
                   "content": result.get("reply", "")}
    if result.get("translation"):
        msg_payload["translation"] = result.get("translation")
    if result.get("correction"):
        msg_payload["correction"] = result.get("correction")
    cm("language:appendConvoMessage", msg_payload)
    _award_exp(user["_id"], "language_chat")
    return jsonify({"ok": True, **result})


@app.route("/languages/<code>/chat/list", methods=["GET"])
@require_login
def lingua_chat_list(code):
    user = user_by_username(current_user())
    convos = cq("language:listConvos", {"user_id": user["_id"], "language_code": code}) or []
    return jsonify({"convos": convos})


@app.route("/languages/<code>/mistake-explain", methods=["POST"])
@require_login
def lingua_mistake_explain(code):
    data = request.get_json() or {}
    exercise = data.get("exercise") or {}
    user_answer = (data.get("user_answer") or "").strip()
    explanation = nv.explain_mistake(exercise, user_answer, code, "en")
    return jsonify({"ok": True, "explanation": explanation})


@app.route("/curriculum/<board>/<int:class_num>/<subject>", methods=["GET"])
def curriculum_get(board, class_num, subject):
    items = cq("language:listCurriculum", {"board": board, "class_num": class_num,
                                             "subject": subject}) or []
    return jsonify({"curriculum": items})


@app.route("/pyqs", methods=["GET"])
def pyqs_list():
    exam = request.args.get("exam", "JEE Main")
    subject = request.args.get("subject", "")
    year = request.args.get("year")
    args = {"exam": exam}
    if subject:
        args["subject"] = subject
    if year:
        args["year"] = int(year)
    items = cq("language:listPYQs", args) or []
    return jsonify({"pyqs": items[:50]})


# ============================================================
# CHAT STREAM
# ============================================================
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
    sid = user["username"]
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
        create_payload = {
            "user_id": chat_owner_id,
            "title": title_src[:45] + ("…" if len(title_src) > 45 else ""),
        }
        if project_id:
            create_payload["project_id"] = project_id
        chat_id = cm("chats:create", create_payload)
    final_message = message
    if attachments:
        final_message = ((message or "Analyze") + "\n\n[Attached: " + ", ".join(attachments) + "]")
    sender = user["username"] if chat_owner_id != user["_id"] else None

    user_msg_payload = {
        "chat_id": chat_id,
        "role": "user",
        "content": ("💡 Deep Explain: " if deep_explain else "") + final_message,
    }
    if attachments:
        user_msg_payload["attachments"] = attachments
    if sender:
        user_msg_payload["sender"] = sender
    cm("chats:appendMessage", user_msg_payload)

    user_settings = cq("misc:getSettings", {"user_id": user["_id"]}) or {}
    persona_items = cq("misc:listPersonas", {"user_id": user["_id"]}) or []
    user_personas = {p["slug"]: {"name": p["name"], "prompt": p["prompt"], "icon": p["icon"]}
                     for p in persona_items}
    memory_items = cq("misc:listMemory", {"user_id": user["_id"]}) or []
    user_memory = [{"fact": m["fact"]} for m in memory_items]

    def _on_usage(_uid, model, ti, to):
        record_usage(user["_id"], model, ti, to)

    def generate():
        yield f"data: {json.dumps({'chat_id': chat_id})}\n\n".encode("utf-8")
        full = ""
        try:
            if deep_explain:
                for chunk in nv.ask_groq_stream(
                    final_message, system_prompt=nv.DEEP_EXPLAIN_SYSTEM,
                    custom_instructions=user_settings.get("custom_instructions", ""),
                    user_personas=user_personas, user=sid, on_usage=_on_usage,
                    memory=user_memory, session_id=sid):
                    full += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n".encode("utf-8")
                cm("chats:appendMessage", {"chat_id": chat_id, "role": "assistant", "content": full})
                try:
                    _award_exp(user["_id"], "chat_message")
                    _check_badges(user["_id"])
                except Exception:
                    pass
                yield f"data: {json.dumps({'done': True, 'full': full})}\n\n".encode("utf-8")
                return

            reminder_result = nv.parse_reminder(message)
            if reminder_result:
                when_dt = datetime.datetime.fromisoformat(reminder_result["when"])
                cm("misc:createReminder", {"user_id": user["_id"],
                                            "text": reminder_result["text"],
                                            "when_iso": reminder_result["when"]})
                qh = user_settings.get("quiet_hours", {})
                extra = ""
                if qh.get("enabled"):
                    extra = f"\n\n_🌙 Quiet hours ({qh.get('start')}–{qh.get('end')})._"
                full = (f"✓ **Reminder set**\n\n- **Kaam:** {reminder_result['text']}\n"
                        f"- **Kab:** {when_dt.strftime('%A, %d %B %Y, %I:%M %p')}{extra}")
                for i in range(0, len(full), 4):
                    yield f"data: {json.dumps({'chunk': full[i:i+4]})}\n\n".encode("utf-8")
                cm("chats:appendMessage", {"chat_id": chat_id, "role": "assistant", "content": full})
                yield f"data: {json.dumps({'done': True, 'full': full})}\n\n".encode("utf-8")
                return

            p = message.lower().strip()
            is_quiz = (p == "/quiz" or p == "quiz" or p.startswith("/quiz ")
                       or p.startswith("quiz ") or p.endswith(" quiz"))
            simple_prefixes = ("time", "weather", "news", "search", "wiki", "calc",
                                "note", "notes", "translate", "pdf ", "save code", "calculate ")
            simple_words = ["mausam", "samay", "khabar", "baj", "waqt", "dhundo",
                            "hello", "hi", "hey", "namaste", "bye", "thanks"]
            is_simple = p.startswith(simple_prefixes) or any(w in p for w in simple_words)
            quiz_running = _quiz_active(sid)

            if p.startswith(("search ", "google ", "dhundo ", "khojo ", "dhoondo ")):
                q = re.sub(r"^(search|google|dhundo|khojo|dhoondo)\s+", "", message,
                           flags=re.IGNORECASE).strip()
                results = nv.web_search_structured(q, max_results=5)
                full = nv.format_search_results_with_citations(q, results)
                for i in range(0, len(full), 4):
                    yield f"data: {json.dumps({'chunk': full[i:i+4]})}\n\n".encode("utf-8")
            elif p.startswith(("news ", "khabar ", "khabrein ")):
                topic = re.sub(r"^(news|khabar|khabrein)\s+", "", message,
                               flags=re.IGNORECASE).strip()
                full = nv.get_news(topic or None, max_items=5)
                for i in range(0, len(full), 4):
                    yield f"data: {json.dumps({'chunk': full[i:i+4]})}\n\n".encode("utf-8")
            elif is_simple or is_quiz or quiz_running or _active_model().startswith("ollama:"):
                full = novex(final_message, user=sid, settings=user_settings,
                              personas=user_personas, memory=user_memory, session_id=sid)
                for i in range(0, len(full), 4):
                    yield f"data: {json.dumps({'chunk': full[i:i+4]})}\n\n".encode("utf-8")
            else:
                for chunk in nv.ask_groq_stream(
                    final_message,
                    custom_instructions=user_settings.get("custom_instructions", ""),
                    user_personas=user_personas, user=sid, on_usage=_on_usage,
                    memory=user_memory, session_id=sid):
                    full += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n".encode("utf-8")
        except Exception as e:
            import traceback
            traceback.print_exc()
            full = f"Error: {e}"
            yield f"data: {json.dumps({'chunk': full})}\n\n".encode("utf-8")
        cm("chats:appendMessage", {"chat_id": chat_id, "role": "assistant", "content": full})
        try:
            _award_exp(user["_id"], "chat_message")
            _check_badges(user["_id"])
        except Exception:
            pass
        yield f"data: {json.dumps({'done': True, 'full': full})}\n\n".encode("utf-8")

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


# ============================================================
# CHATS
# ============================================================
@app.route("/chats", methods=["GET"])
@require_login
def list_chats():
    user = user_by_username(current_user())
    project_filter = request.args.get("project")
    pid = project_filter if project_filter else None
    return jsonify(cq("chats:listByUser", {"user_id": user["_id"], "project_id": pid}) or [])


@app.route("/chats/<cid>", methods=["GET"])
@require_login
def get_chat(cid):
    user = user_by_username(current_user())
    c = cq("chats:getById", {"id": cid, "viewer_id": user["_id"]})
    if not c:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"id": c["_id"], "title": c["title"], "messages": c["messages"],
                    "updated": c["updated"], "project_id": c.get("project_id")})


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


# ============================================================
# SHARE / MULTI-USER
# ============================================================
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
<style>body{{background:#000;color:#ececec;font-family:system-ui;margin:0;padding:20px}}.wrap{{max-width:780px;margin:0 auto}}.head{{border-bottom:1px solid #ffffff20;padding-bottom:16px;margin-bottom:24px;display:flex;justify-content:space-between}}.head h1{{font-size:20px;margin:0}}.head a{{color:#10a37f;text-decoration:none;font-weight:700}}.msg{{margin-bottom:20px;padding:14px 18px;border-radius:12px;background:#1a1a1a}}.msg.user{{background:#262626;margin-left:auto;max-width:80%}}.msg.bot{{background:#000;border:1px solid #ffffff10}}.role{{font-size:11px;text-transform:uppercase;color:#8e8e8e;margin-bottom:6px;font-weight:600}}.content{{white-space:pre-wrap;line-height:1.7}}.footer{{margin-top:40px;padding-top:20px;border-top:1px solid #ffffff20;text-align:center;color:#8e8e8e;font-size:13px}}.footer a{{color:#10a37f}}</style></head><body><div class="wrap"><div class="head"><h1>{esc(chat.get("title","Shared"))}</h1><a href="/">NOVEX AI →</a></div>{msgs}<div class="footer">Read-only · <a href="/">Try NOVEX AI</a></div></div></body></html>'''


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
    return jsonify(cq("chats:getSharedWithUser", {"user_id": user["_id"]}) or [])


# ============================================================
# TTS / VOICES / TRANSLATE / STATIC
# ============================================================
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


@app.route("/languages-list", methods=["GET"])
def languages_list():
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


# ============================================================
# STATIC FILES
# ============================================================
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


@app.route("/themes.css")
def themes_css():
    try:
        return send_from_directory(".", "themes.css")
    except Exception:
        return ("/* themes.css not found */", 404, {"Content-Type": "text/css"})
@app.route("/themes-extra.css")
def themes_extra_css():
    try:
        return send_from_directory(".", "themes-extra.css")
    except Exception:
        return ("/* themes-extra.css not found */", 404, {"Content-Type": "text/css"})


@app.route("/ui-modes.css")
def ui_modes_css():
    try:
        return send_from_directory(".", "ui-modes.css")
    except Exception:
        return ("/* ui-modes.css not found */", 404, {"Content-Type": "text/css"})


@app.route("/ui-modes.js")
def ui_modes_js():
    try:
        return send_from_directory(".", "ui-modes.js")
    except Exception:
        return ("/* ui-modes.js not found */", 404, {"Content-Type": "application/javascript"})

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
        "ok": True, "service": "novex-ai", "version": "7.0",
        "totp": TOTP_AVAILABLE, "brevo": bool(BREVO_API_KEY),
        "convex": convex_ok,
        "search": {
            "serper": bool(os.getenv("SERPER_API_KEY")),
            "ddgs": True,
        },
        "features": {
            "deep_explain": True,
            "session_isolation": True,
            "doubt_scanner": True,
            "gamification": True,
            "srs": True,
            "lingua": True,
            "voice_tutor": True,
            "rooms": True,
            "peer_doubts": True,
            "batch1": True,
            "quiz_v2": True,
            "search_realtime": True,
            "themes": 32,
        },
    })


# ============ INIT auth_extra ============
from auth_extra import init as _auth_extra_init

_auth_extra_init(cq, cm, send_email, APP_URL, password_strength)


if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 10000))
    HOST = os.getenv("HOST", "0.0.0.0")
    print("=" * 60)
    print("  NOVEX AI v7.0")
    print(f"  URL: http://{HOST}:{PORT}")
    print(f"  Convex: {os.getenv('CONVEX_URL', 'NOT SET')}")
    print(f"  Brevo: {'✓' if BREVO_API_KEY else '✗ (console fallback)'}")
    print(f"  2FA: {'✓' if TOTP_AVAILABLE else '✗'}")
    print(f"  Search: Serper {'✓' if os.getenv('SERPER_API_KEY') else '✗'} + DDGS ✓")
    print(f"  Quiz: v2 (categories, streaks, speed bonus)")
    print(f"  Themes: 32 (including 11 realistic)")
    print("=" * 60)
    serve(app, host=HOST, port=PORT, threads=16, send_bytes=1, channel_timeout=300)