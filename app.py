"""
NOVEX AI v8.0 — Flask Server (UPGRADED)
Features: Auth (Email + Google + 2FA), Chat, Quiz v2, Search,
Batch1+2, Lingua (with fallback), Voice, Rooms, Peer Doubts,
52 Themes, 10 UI Modes, upgraded streaming + caching + logging.
"""
from flask import (Flask, request, jsonify, send_from_directory, Response,
                   stream_with_context, session, redirect, g)
from flask_cors import CORS
from waitress import serve
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps, lru_cache
from urllib.parse import urlencode, quote
import os, json, uuid, datetime, secrets, asyncio, time, random
import base64, re, requests, logging, threading
from io import BytesIO
from collections import defaultdict, OrderedDict
from dotenv import load_dotenv

try:
    from convex import ConvexClient
except ImportError:
    ConvexClient = None

load_dotenv()

import novex as nv
from novex import novex
from auth_extra import auth_extra_bp

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("novex")

# ============================================================
# CONVEX
# ============================================================
CONVEX_URL = os.getenv("CONVEX_URL")
if not CONVEX_URL:
    log.warning("CONVEX_URL not set — DB features disabled")
convex_client = ConvexClient(CONVEX_URL) if (CONVEX_URL and ConvexClient) else None


def cq(path, args=None):
    if not convex_client:
        raise ValueError("CONVEX_URL not configured")
    return convex_client.query(path, args or {})


def cm(path, args=None):
    if not convex_client:
        raise ValueError("CONVEX_URL not configured")
    return convex_client.mutation(path, args or {})


# ============================================================
# COMPAT
# ============================================================
def _active_model():
    return getattr(nv, "_ACTIVE_MODEL", "groq:openai/gpt-oss-120b")


def _set_active_model(mid):
    nv.set_model(mid)


def _quiz_active(sid):
    if hasattr(nv, "is_quiz_active"):
        try:
            return nv.is_quiz_active(sid)
        except Exception:
            pass
    return False


try:
    import pyotp
    import qrcode
    TOTP_AVAILABLE = True
except ImportError:
    TOTP_AVAILABLE = False
    log.warning("pyotp / qrcode missing — 2FA disabled")

# ============================================================
# APP
# ============================================================
app = Flask(__name__, static_folder=".")
app.register_blueprint(auth_extra_bp)
CORS(app, supports_credentials=True)

app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.permanent_session_lifetime = datetime.timedelta(days=36500)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB upload
app.config["JSON_SORT_KEYS"] = False

# ============================================================
# CONFIG
# ============================================================
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@novex.local")
FROM_NAME = os.getenv("FROM_NAME", "NOVEX AI")
APP_URL = os.getenv("APP_URL", "https://novex-ai.onrender.com")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI",
                                f"{APP_URL}/auth/google/callback")

UPLOADS_DIR = "uploads"
VOICE_DIR = "voice"
for d in [UPLOADS_DIR, VOICE_DIR]:
    os.makedirs(d, exist_ok=True)

# ============================================================
# MODELS
# ============================================================
AVAILABLE_MODELS = [
    {"id": "groq:openai/gpt-oss-120b", "name": "Novex Pro",
     "provider": "Groq", "desc": "Best quality (ChatGPT-level)"},
    {"id": "groq:openai/gpt-oss-20b", "name": "Novex Balanced",
     "provider": "Groq", "desc": "Fast + good"},
    {"id": "groq:llama-3.3-70b-versatile", "name": "Novex Turbo",
     "provider": "Groq", "desc": "Balanced fast"},
    {"id": "groq:llama-3.1-8b-instant", "name": "Novex Flash",
     "provider": "Groq", "desc": "Fastest for simple tasks"},
]

# ============================================================
# VOICES (upgraded — added more)
# ============================================================
VOICES = {
    "hi-male": "hi-IN-MadhurNeural", "hi-female": "hi-IN-SwaraNeural",
    "en-in-male": "en-IN-PrabhatNeural", "en-in-female": "en-IN-NeerjaNeural",
    "en-us-male": "en-US-GuyNeural", "en-us-female": "en-US-JennyNeural",
    "en-us-male2": "en-US-ChristopherNeural", "en-us-female2": "en-US-AriaNeural",
    "en-gb-female": "en-GB-SoniaNeural", "en-gb-male": "en-GB-RyanNeural",
    "ur-male": "ur-PK-AsadNeural", "ur-female": "ur-PK-UzmaNeural",
    "bn-female": "bn-IN-TanishaaNeural", "bn-male": "bn-IN-BashkarNeural",
    "ta-male": "ta-IN-ValluvarNeural", "ta-female": "ta-IN-PallaviNeural",
    "te-male": "te-IN-MohanNeural", "te-female": "te-IN-ShrutiNeural",
    "mr-male": "mr-IN-ManoharNeural", "mr-female": "mr-IN-AarohiNeural",
    "gu-female": "gu-IN-DhwaniNeural", "gu-male": "gu-IN-NiranjanNeural",
    "kn-male": "kn-IN-GaganNeural", "kn-female": "kn-IN-SapnaNeural",
    "ml-male": "ml-IN-MidhunNeural", "ml-female": "ml-IN-SobhanaNeural",
    "pa-female": "pa-IN-GurpreetNeural", "pa-male": "pa-IN-OjasNeural",
    "ar-male": "ar-SA-HamedNeural", "ar-female": "ar-SA-ZariyahNeural",
    "zh-female": "zh-CN-XiaoxiaoNeural", "zh-male": "zh-CN-YunxiNeural",
    "ja-female": "ja-JP-NanamiNeural", "ja-male": "ja-JP-KeitaNeural",
    "ko-female": "ko-KR-SunHiNeural", "ko-male": "ko-KR-InJoonNeural",
    "fr-female": "fr-FR-DeniseNeural", "fr-male": "fr-FR-HenriNeural",
    "de-male": "de-DE-ConradNeural", "de-female": "de-DE-KatjaNeural",
    "es-female": "es-ES-ElviraNeural", "es-male": "es-ES-AlvaroNeural",
    "ru-female": "ru-RU-SvetlanaNeural", "ru-male": "ru-RU-DmitryNeural",
    "pt-br-female": "pt-BR-FranciscaNeural", "pt-br-male": "pt-BR-AntonioNeural",
    "it-female": "it-IT-ElsaNeural", "it-male": "it-IT-DiegoNeural",
    "nl-female": "nl-NL-ColetteNeural", "tr-female": "tr-TR-EmelNeural",
    "vi-female": "vi-VN-HoaiMyNeural", "th-female": "th-TH-PremwadeeNeural",
}

# ============================================================
# RATE LIMIT (upgraded — supports per-user + per-IP)
# ============================================================
rate_buckets = defaultdict(list)
rate_lock = threading.Lock()


def check_rate_limit(key, max_attempts=5, window_sec=300):
    """Sliding window rate limit. Returns True if allowed."""
    now = time.time()
    with rate_lock:
        bucket = rate_buckets[key]
        bucket[:] = [t for t in bucket if now - t < window_sec]
        if len(bucket) >= max_attempts:
            return False
        bucket.append(now)
        return True


# ============================================================
# SIMPLE LRU CACHE (in-memory, thread-safe)
# ============================================================
class TTLCache:
    def __init__(self, max_size=512, ttl=60):
        self._d = OrderedDict()
        self._max = max_size
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._d:
                return None
            val, exp = self._d[key]
            if time.time() > exp:
                self._d.pop(key, None)
                return None
            self._d.move_to_end(key)
            return val

    def set(self, key, val, ttl=None):
        with self._lock:
            self._d[key] = (val, time.time() + (ttl or self._ttl))
            self._d.move_to_end(key)
            while len(self._d) > self._max:
                self._d.popitem(last=False)

    def clear(self, prefix=None):
        with self._lock:
            if not prefix:
                self._d.clear()
                return
            for k in list(self._d.keys()):
                if k.startswith(prefix):
                    self._d.pop(k, None)


settings_cache = TTLCache(max_size=256, ttl=120)
persona_cache = TTLCache(max_size=256, ttl=180)
lang_cache = TTLCache(max_size=64, ttl=600)


# ============================================================
# HELPERS
# ============================================================
def current_user():
    return session.get("user")


def current_uid():
    return session.get("user_id")


def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"error": "Not logged in", "need_login": True}), 401
        return f(*args, **kwargs)
    return wrapper


def is_valid_email(email):
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                         email or ""))


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


def get_client_ip():
    return request.headers.get("X-Forwarded-For",
                              request.remote_addr or "unknown").split(",")[0].strip()


def send_email(to, subject, body):
    if not BREVO_API_KEY:
        log.info("[EMAIL FALLBACK] → %s | %s", to, subject)
        log.debug(body)
        return True
    try:
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {"api-key": BREVO_API_KEY, "Content-Type": "application/json"}
        payload = {"sender": {"email": FROM_EMAIL, "name": FROM_NAME},
                   "to": [{"email": to}], "subject": subject,
                   "textContent": body}
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        return resp.status_code in (200, 201, 202)
    except Exception as e:
        log.exception("Email error: %s", e)
        return False


def user_by_username(u):
    return cq("users:getByUsername", {"username": (u or "").lower()})


def user_by_email(e):
    return cq("users:getByEmail", {"email": (e or "").lower()})


def record_login(uid, success=True):
    try:
        cm("auth:recordLogin", {
            "user_id": uid,
            "ip": get_client_ip(),
            "ua": (request.headers.get("User-Agent") or "")[:200],
            "success": success,
        })
    except Exception:
        pass


# ============================================================
# GAMIFICATION
# ============================================================
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
        cm("misc:updateProgress", {
            "user_id": user_id, "exp": new_exp,
            "level": lvl["level"], "level_icon": lvl["icon"],
        })
        cm("misc:logExp", {"user_id": user_id, "action": action,
                           "exp_gained": amount, "meta": meta})
    except Exception as e:
        log.warning("_award_exp failed: %s", e)


def _increment_counter(user_id, field, amount=1):
    try:
        cm("misc:incrementCounter", {"user_id": user_id, "field": field,
                                     "amount": amount})
    except Exception as e:
        log.warning("_increment_counter failed: %s", e)


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
            ("first_chat", (p.get("chat_messages") or 0) >= 1),
            ("chatty_100", (p.get("chat_messages") or 0) >= 100),
            ("polyglot", (p.get("language_lessons") or 0) >= 25),
        ]
        for bid, cond in checks:
            if cond and bid not in have and bid in nv.BADGES:
                icon, name, desc = nv.BADGES[bid]
                cm("misc:unlockBadge", {
                    "user_id": user_id, "badge_id": bid,
                    "badge_icon": icon, "badge_name": name, "badge_desc": desc,
                })
    except Exception as e:
        log.warning("_check_badges failed: %s", e)


# ============================================================
# 🔐 GOOGLE OAUTH
# ============================================================
@app.route("/auth/google")
def google_login():
    if not GOOGLE_CLIENT_ID:
        return redirect("/?error=Google+login+not+configured+on+server")
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": state,
    }
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@app.route("/auth/google/callback")
def google_callback():
    error = request.args.get("error")
    if error:
        return redirect(f"/?error=Google+login+failed:+{error}")

    code = request.args.get("code")
    state = request.args.get("state")
    saved_state = session.pop("oauth_state", None)

    if not code:
        return redirect("/?error=No+code+from+Google")
    if not state or state != saved_state:
        return redirect("/?error=State+mismatch+(CSRF)")

    try:
        token_res = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        if token_res.status_code != 200:
            log.error("google token exchange failed: %s", token_res.text)
            return redirect("/?error=Token+exchange+failed")
        tokens = token_res.json()
        access_token = tokens.get("access_token")

        info_res = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if info_res.status_code != 200:
            return redirect("/?error=Could+not+fetch+user+info")
        info = info_res.json()

        email = (info.get("email") or "").lower()
        name = info.get("name") or email.split("@")[0]
        google_id = info.get("sub")

        if not email:
            return redirect("/?error=No+email+from+Google")

        user = user_by_email(email)

        if not user:
            username = re.sub(r"[^a-z0-9_]", "", email.split("@")[0].lower())[:20]
            if len(username) < 3:
                username = f"user{random.randint(1000, 9999)}"
            base_username = username
            counter = 1
            while user_by_username(username):
                username = f"{base_username}{counter}"
                counter += 1
                if counter > 100:
                    username = f"user{random.randint(10000, 99999)}"
                    break

            uid = cm("users:create", {
                "username": username,
                "email": email,
                "password_hash": None,
                "display_name": name[:40],
                "email_verified": True,
                "auth_provider": "google",
                "google_id": google_id,
            })
            user = user_by_username(username)
            try:
                _get_or_create_progress(uid)
            except Exception:
                pass

        session.permanent = True
        session["user"] = user["username"]
        session["user_id"] = user["_id"]

        try:
            cm("users:updateLastLogin", {"id": user["_id"]})
            record_login(user["_id"], True)
        except Exception:
            pass

        return redirect("/")
    except Exception as e:
        log.exception("google_callback error")
        return redirect("/?error=Google+login+exception")


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
    cm("auth:createPending", {
        "username": username, "email": email,
        "password_hash": generate_password_hash(password),
        "display_name": display_name, "code": code,
    })
    send_email(email, "NOVEX AI — Verify",
               f"Hi {display_name},\n\nCode: {code}\n\nValid 15 min.\n— NOVEX")
    masked = email[:2] + "***@" + email.split("@")[1] if "@" in email else email
    return jsonify({"ok": True, "username": username, "email_masked": masked})


# ============================================================
# AUTH ALIASES (compat)
# ============================================================
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
    uid = cm("users:create", {
        "username": username, "email": entry["email"],
        "password_hash": entry["password_hash"],
        "display_name": entry["display_name"],
        "email_verified": True, "auth_provider": "local",
    })
    cm("auth:deletePending", {"username": username})
    session.permanent = True
    session["user"] = username
    session["user_id"] = uid
    record_login(uid, True)
    try:
        _get_or_create_progress(uid)
    except Exception:
        pass
    return jsonify({"ok": True, "username": username,
                    "display_name": entry["display_name"]})


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
        return jsonify({"error": "Google account hai — 'Continue with Google' use karo"}), 401
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
    cm("auth:createReset", {
        "token": secrets.token_urlsafe(24),
        "username": user["username"], "email": email, "code": code,
    })
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
    cm("users:updatePassword", {
        "id": user["_id"],
        "password_hash": generate_password_hash(new_password),
    })
    cm("auth:deleteReset", {"token": entry["token"]})
    return jsonify({"ok": True})


# ============================================================
# 2FA
# ============================================================
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
    cm("users:updatePassword", {
        "id": user["_id"],
        "password_hash": generate_password_hash(data["new_password"]),
    })
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
    uid = current_uid()
    ck = f"settings:{uid}"
    cached = settings_cache.get(ck)
    if cached is not None:
        return jsonify(cached)
    s = cq("misc:getSettings", {"user_id": uid})
    out = {"custom_instructions": (s or {}).get("custom_instructions", "")}
    settings_cache.set(ck, out)
    return jsonify(out)


@app.route("/settings", methods=["POST"])
@require_login
def update_settings():
    uid = current_uid()
    data = request.get_json() or {}
    patch = {"user_id": uid}
    if "custom_instructions" in data:
        patch["custom_instructions"] = str(data["custom_instructions"])[:4000]
    cm("misc:updateSettings", patch)
    settings_cache.clear(prefix=f"settings:{uid}")
    return jsonify({"ok": True, "settings": patch})


@app.route("/personas", methods=["GET"])
@require_login
def list_personas():
    uid = current_uid()
    ck = f"personas:{uid}"
    cached = persona_cache.get(ck)
    if cached is not None:
        return jsonify(cached)
    items = cq("misc:listPersonas", {"user_id": uid}) or []
    out = {"personas": {p["slug"]: {
        "name": p["name"], "prompt": p["prompt"],
        "icon": p["icon"], "created": p["created"],
    } for p in items}}
    persona_cache.set(ck, out)
    return jsonify(out)


@app.route("/personas", methods=["POST"])
@require_login
def save_persona():
    uid = current_uid()
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    prompt = (data.get("prompt") or "").strip()
    icon = (data.get("icon") or "🤖").strip()[:4]
    if not name or not prompt:
        return jsonify({"error": "Name aur prompt chahiye"}), 400
    slug = "".join(c for c in name.lower().replace(" ", "_")
                   if c.isalnum() or c == "_") or "persona"
    cm("misc:savePersona", {"user_id": uid, "slug": slug,
                            "name": name, "prompt": prompt, "icon": icon})
    persona_cache.clear(prefix=f"personas:{uid}")
    return jsonify({"ok": True, "slug": slug})


@app.route("/personas/<slug>", methods=["DELETE"])
@require_login
def delete_persona(slug):
    uid = current_uid()
    cm("misc:deletePersona", {"user_id": uid, "slug": slug})
    persona_cache.clear(prefix=f"personas:{uid}")
    return jsonify({"ok": True})


@app.route("/projects", methods=["GET"])
@require_login
def list_projects():
    uid = current_uid()
    items = cq("misc:listProjects", {"user_id": uid}) or []
    return jsonify({"projects": [{
        "id": p["_id"], "name": p["name"],
        "color": p["color"], "created": p["created"],
    } for p in items]})


@app.route("/projects", methods=["POST"])
@require_login
def create_project():
    uid = current_uid()
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    color = (data.get("color") or "#06b6d4").strip()[:9]
    if not name:
        return jsonify({"error": "Name chahiye"}), 400
    pid = cm("misc:createProject", {"user_id": uid, "name": name, "color": color})
    return jsonify({"ok": True, "id": pid})


@app.route("/projects/<pid>", methods=["DELETE"])
@require_login
def delete_project(pid):
    cm("misc:deleteProject", {"project_id": pid})
    return jsonify({"ok": True})


@app.route("/memory", methods=["GET"])
@require_login
def list_memory():
    uid = current_uid()
    items = cq("misc:listMemory", {"user_id": uid}) or []
    return jsonify({"memory": [{
        "id": m["_id"], "fact": m["fact"],
        "source": m["source"], "created": m["created"],
    } for m in items]})


@app.route("/memory", methods=["POST"])
@require_login
def create_memory():
    uid = current_uid()
    data = request.get_json() or {}
    fact = (data.get("fact") or "").strip()
    if not fact:
        return jsonify({"error": "Fact chahiye"}), 400
    if len(fact) > 500:
        return jsonify({"error": "Max 500"}), 400
    result = cm("misc:addMemory", {"user_id": uid, "fact": fact,
                                    "source": "manual"})
    if not result.get("duplicate"):
        _increment_counter(uid, "memory_count")
        _check_badges(uid)
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
    uid = current_uid()
    cm("misc:clearMemory", {"user_id": uid})
    return jsonify({"ok": True})


@app.route("/memory/auto-extract", methods=["POST"])
@require_login
def auto_extract_memory():
    uid = current_uid()
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Text chahiye"}), 400
    facts = nv.extract_facts(text)
    added = []
    for f in facts:
        result = cm("misc:addMemory", {"user_id": uid, "fact": f,
                                        "source": "auto"})
        if not result.get("duplicate"):
            added.append(f)
            _increment_counter(uid, "memory_count")
    if added:
        _check_badges(uid)
    return jsonify({"ok": True, "added": added, "count": len(added)})


# ============================================================
# FLASHCARDS + SRS
# ============================================================
@app.route("/flashcards", methods=["GET"])
@require_login
def list_flashcards():
    uid = current_uid()
    items = cq("misc:listFlashcards", {"user_id": uid}) or []
    return jsonify({"decks": [{
        "id": d["_id"], "title": d["title"],
        "cards": d["cards"], "created": d["created"],
        "reviewed": d.get("reviewed", 0),
    } for d in items]})


@app.route("/flashcards/generate", methods=["POST"])
@require_login
def generate_flashcards_endpoint():
    uid = current_uid()
    data = request.get_json() or {}
    source = (data.get("source") or "").strip()
    count = int(data.get("count") or 10)
    topic = (data.get("topic") or "").strip()
    chat_id = data.get("chat_id")
    if chat_id and not source:
        c = cq("chats:getById", {"id": chat_id, "viewer_id": uid})
        if c:
            source = "\n\n".join(m.get("content", "")
                                 for m in c.get("messages", [])[-10:])
    if not source and not topic:
        return jsonify({"error": "Topic ya chat_id chahiye"}), 400
    cards = nv.generate_flashcards(source or f"Topic: {topic}", count)
    if "error" in cards:
        return jsonify(cards), 500
    deck_id = cm("misc:createFlashcardDeck", {
        "user_id": uid,
        "title": (topic or cards.get("title", "Flashcards"))[:60],
        "cards": cards["cards"],
    })
    _award_exp(uid, "flashcard_deck_create")
    return jsonify({"ok": True, "deck": {
        "id": deck_id, "title": topic or "Flashcards",
        "cards": cards["cards"],
    }})


@app.route("/flashcards/<deck_id>", methods=["DELETE"])
@require_login
def delete_flashcards(deck_id):
    cm("misc:deleteFlashcardDeck", {"id": deck_id})
    return jsonify({"ok": True})


@app.route("/flashcards/srs/due", methods=["GET"])
@require_login
def srs_due_cards():
    uid = current_uid()
    decks = cq("misc:listFlashcards", {"user_id": uid}) or []
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    due = []
    for d in decks:
        for i, card in enumerate(d.get("cards", [])):
            nr = card.get("next_review") or 0
            if nr <= now_ms:
                due.append({
                    "deck_id": d["_id"], "deck_title": d["title"],
                    "card_index": i, "front": card.get("front", ""),
                    "back": card.get("back", ""), "next_review": nr,
                    "repetitions": card.get("repetitions") or 0,
                    "interval_days": card.get("interval_days") or 0,
                })
    due.sort(key=lambda x: x["next_review"])
    return jsonify({"due": due, "count": len(due)})


@app.route("/flashcards/srs/review", methods=["POST"])
@require_login
def srs_review_card():
    uid = current_uid()
    data = request.get_json() or {}
    deck_id = data.get("deck_id")
    card_index = data.get("card_index")
    rating = int(data.get("rating", 2))
    if deck_id is None or card_index is None:
        return jsonify({"error": "deck_id and card_index required"}), 400
    decks = cq("misc:listFlashcards", {"user_id": uid}) or []
    deck = next((d for d in decks if d["_id"] == deck_id), None)
    if not deck:
        return jsonify({"error": "Deck not found"}), 404
    cards = deck.get("cards", [])
    if card_index < 0 or card_index >= len(cards):
        return jsonify({"error": "Card index out of range"}), 400
    card = cards[card_index]
    result = nv.srs_next(
        ease_factor=card.get("ease_factor") or 2.5,
        interval_days=card.get("interval_days") or 0,
        repetitions=card.get("repetitions") or 0,
        rating=rating,
    )
    card.update(result)
    cm("misc:updateFlashcardDeck", {
        "id": deck_id, "cards": cards,
        "reviewed": (deck.get("reviewed") or 0) + 1,
    })
    _award_exp(uid, "flashcard_review")
    _increment_counter(uid, "flashcards_reviewed")
    _check_badges(uid)
    return jsonify({"ok": True, "card": card,
                    "next_review": result["next_review"]})


# ============================================================
# DOCS
# ============================================================
@app.route("/docs", methods=["GET"])
@require_login
def list_docs():
    uid = current_uid()
    return jsonify({"docs": cq("misc:listDocs", {"user_id": uid}) or []})


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
    uid = current_uid()
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
        "user_id": uid,
        "title": result.get("title", topic)[:80],
        "topic": topic, "style": style,
        "length": length, "language": language,
        "outline": result.get("outline", []),
        "content": result.get("content", ""),
    })
    _award_exp(uid, "doc_generate")
    _increment_counter(uid, "docs_generated")
    _check_badges(uid)
    return jsonify({"ok": True, "doc": {
        "id": doc_id,
        "title": result.get("title", topic),
        "content": result.get("content", ""),
    }})


# ============================================================
# STATS / REMINDERS / MODELS
# ============================================================
@app.route("/stats", methods=["GET"])
@require_login
def stats():
    uid = current_uid()
    s = cq("misc:getStats", {"user_id": uid})
    if not s:
        return jsonify({"total_in": 0, "total_out": 0,
                        "calls": 0, "models": {}})
    models = {m["model"]: {"in": m["in"], "out": m["out"],
                            "calls": m["calls"]}
              for m in s.get("model_stats", [])}
    return jsonify({"total_in": s["total_in"], "total_out": s["total_out"],
                    "calls": s["calls"], "models": models})


@app.route("/stats/detailed", methods=["GET"])
@require_login
def stats_detailed():
    uid = current_uid()
    s = cq("misc:getStats", {"user_id": uid}) or {}
    p = _get_or_create_progress(uid)
    return jsonify({
        "tokens": {
            "in": s.get("total_in", 0),
            "out": s.get("total_out", 0),
            "total": s.get("total_in", 0) + s.get("total_out", 0),
        },
        "calls": s.get("calls", 0),
        "models": s.get("model_stats", []),
        "gamification": {
            "exp": p.get("exp", 0),
            "level": p.get("level", 1),
            "badges": p.get("badge_count", 0),
        },
        "activity": {
            "chats": p.get("chat_messages", 0),
            "quizzes": p.get("quiz_count", 0),
            "flashcards": p.get("flashcards_reviewed", 0),
            "docs": p.get("docs_generated", 0),
        },
    })


def record_usage(uid, model, ti, to):
    try:
        cm("misc:recordUsage", {"user_id": uid, "model": model,
                                "tokens_in": ti, "tokens_out": to})
    except Exception as e:
        log.warning("record_usage failed: %s", e)


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
# UPLOAD / QUIZ / SEARCH
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
        count = max(3, min(int(count), 30))
    result = nv.generate_quiz_json(topic, difficulty, count)
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route("/quiz/complete", methods=["POST"])
@require_login
def quiz_complete():
    uid = current_uid()
    data = request.get_json() or {}
    score = int(data.get("score", 0))
    total = int(data.get("total", 0))
    difficulty = (data.get("difficulty") or "medium").lower()
    max_streak = int(data.get("max_streak", 0))
    multiplier = nv.DIFFICULTY_PRESETS.get(difficulty, {}).get("xp", 1.0)
    base_xp = 25 + score * 10
    total_xp = int(base_xp * multiplier)
    if total > 0 and score == total:
        total_xp += nv.EXP_REWARDS.get("quiz_perfect", 50)
    if max_streak >= 10:
        total_xp += nv.EXP_REWARDS.get("quiz_streak_10", 75)
    elif max_streak >= 5:
        total_xp += nv.EXP_REWARDS.get("quiz_streak_5", 30)
    try:
        p = _get_or_create_progress(uid)
        new_exp = (p.get("exp") or 0) + total_xp
        lvl = nv.calculate_level(new_exp)
        cm("misc:updateProgress", {
            "user_id": uid, "exp": new_exp,
            "level": lvl["level"], "level_icon": lvl["icon"],
        })
        _increment_counter(uid, "quiz_count")
        if total > 0 and score == total:
            _increment_counter(uid, "perfect_quizzes")
        _check_badges(uid)
    except Exception as e:
        log.warning("quiz_complete failed: %s", e)
    return jsonify({"ok": True, "exp_gained": total_xp,
                    "multiplier": multiplier, "score": score, "total": total})


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
                        "provider": getattr(nv, "_last_search_provider", "unknown"),
                        "count": len(results)})
    except Exception as e:
        log.exception("search failed")
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
    })


# ============================================================
# DOUBT SCANNER
# ============================================================
@app.route("/doubt-scanner", methods=["POST"])
@require_login
def doubt_scanner():
    uid = current_uid()
    user = user_by_username(current_user())
    if not user:
        return jsonify({"error": "User not found"}), 401
    if "file" in request.files:
        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "Empty file"}), 400
        file_uid = uuid.uuid4().hex[:8]
        path = os.path.join(UPLOADS_DIR, f"{file_uid}_{f.filename}")
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
    chat_id = cm("chats:create", {
        "user_id": uid,
        "title": f"📸 {question[:40] or os.path.basename(path)[:40]}",
    })
    cm("chats:appendMessage", {
        "chat_id": chat_id, "role": "user",
        "content": f"📸 [Image: {os.path.basename(path)}]\n{question}",
    })
    cm("chats:appendMessage", {
        "chat_id": chat_id, "role": "assistant", "content": answer,
    })
    _award_exp(uid, "doubt_scanner")
    _increment_counter(uid, "doubts_solved")
    _check_badges(uid)
    return jsonify({"ok": True, "answer": answer, "chat_id": chat_id})


# ============================================================
# GAMIFICATION
# ============================================================
@app.route("/gamification/profile", methods=["GET"])
@require_login
def gamification_profile():
    uid = current_uid()
    p = _get_or_create_progress(uid)
    badges = cq("misc:listBadges", {"user_id": uid}) or []
    lvl = nv.calculate_level(p.get("exp") or 0)
    have = {b["badge_id"] for b in badges}
    all_badges = [{
        "id": bid, "icon": icon, "name": name,
        "desc": desc, "unlocked": bid in have,
    } for bid, (icon, name, desc) in nv.BADGES.items()]
    return jsonify({
        "exp": p.get("exp") or 0,
        "level": lvl["level"], "level_icon": lvl["icon"],
        "progress_pct": lvl["progress_pct"],
        "next_level": lvl.get("next_level"),
        "next_at": lvl.get("next_at"),
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


# ============================================================
# BATCH 1
# ============================================================
@app.route("/formula-sheet/generate", methods=["POST"])
@require_login
def formula_sheet_generate():
    uid = current_uid()
    data = request.get_json() or {}
    subject = (data.get("subject") or "Physics").strip()
    chapters = data.get("chapters") or []
    board = (data.get("board") or "CBSE").strip()
    result = nv.generate_formula_sheet(subject, chapters, board)
    if "error" in result:
        return jsonify(result), 500
    fid = cm("misc:createFormulaSheet", {
        "user_id": uid, "subject": subject,
        "chapters": chapters, "content": result["content"],
    })
    _award_exp(uid, "doc_generate")
    return jsonify({"ok": True, "id": fid, **result})


@app.route("/mind-map/generate", methods=["POST"])
@require_login
def mind_map_generate():
    uid = current_uid()
    data = request.get_json() or {}
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "Topic required"}), 400
    depth = int(data.get("depth") or 3)
    result = nv.generate_mind_map(topic, depth)
    if "error" in result:
        return jsonify(result), 500
    mid = cm("misc:createMindMap", {
        "user_id": uid, "title": topic,
        "source": topic, "markdown": result["markdown"],
    })
    _award_exp(uid, "doc_generate")
    return jsonify({"ok": True, "id": mid, **result})


@app.route("/weak-topics/analyze", methods=["GET"])
@require_login
def weak_topics_analyze():
    uid = current_uid()
    attempts = cq("progress:listQuizAttempts", {"user_id": uid, "limit": 200}) or []
    weak = nv.analyze_weak_topics(attempts)
    return jsonify({"weak": weak, "total_attempts": len(attempts)})


@app.route("/podcast/generate", methods=["POST"])
@require_login
def podcast_generate():
    uid = current_uid()
    data = request.get_json() or {}
    source = (data.get("source") or "").strip()
    title = (data.get("title") or "Study Podcast").strip()
    lang = (data.get("language") or "hinglish").strip()
    if not source:
        return jsonify({"error": "Source text required"}), 400
    result = nv.generate_podcast_script(source[:3000], title, lang)
    if "error" in result:
        return jsonify(result), 500
    pid = cm("misc:createPodcast", {
        "user_id": uid, "title": result["title"],
        "source_text": source[:3000],
        "script_json": json.dumps(result["lines"]),
        "audio_url": "",
        "duration_sec": len(result["lines"]) * 10,
    })
    _award_exp(uid, "doc_generate")
    return jsonify({"ok": True, "id": pid, **result})


@app.route("/debate/start", methods=["POST"])
@require_login
def debate_start():
    uid = current_uid()
    data = request.get_json() or {}
    topic = (data.get("topic") or "").strip()
    rounds = int(data.get("rounds") or 5)
    if not topic:
        return jsonify({"error": "Topic required"}), 400
    did = cm("misc:createDebate", {"user_id": uid, "topic": topic,
                                    "rounds": rounds})
    return jsonify({"ok": True, "debate_id": did, "topic": topic})


@app.route("/debate/round", methods=["POST"])
@require_login
def debate_round():
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
    try:
        cm("misc:appendDebateMessage", {"debate_id": did,
                                         "speaker": "A", "content": arg_a})
        cm("misc:appendDebateMessage", {"debate_id": did,
                                         "speaker": "B", "content": arg_b})
    except Exception:
        pass
    return jsonify({"ok": True, "arg_a": arg_a, "arg_b": arg_b})


@app.route("/debate/verdict", methods=["POST"])
@require_login
def debate_verdict_ep():
    data = request.get_json() or {}
    did = data.get("debate_id")
    topic = data.get("topic", "")
    history = data.get("history") or []
    verdict = nv.debate_verdict(topic, history)
    if did:
        try:
            cm("misc:setDebateVerdict", {"debate_id": did, "verdict": verdict})
        except Exception:
            pass
    return jsonify({"ok": True, "verdict": verdict})


# ============================================================
# LINGUA (upgraded with fallback languages)
# ============================================================
FALLBACK_LANGUAGES = [
    {"code": "es", "name": "Spanish", "flag": "🇪🇸", "native": "Español"},
    {"code": "fr", "name": "French", "flag": "🇫🇷", "native": "Français"},
    {"code": "de", "name": "German", "flag": "🇩🇪", "native": "Deutsch"},
    {"code": "it", "name": "Italian", "flag": "🇮🇹", "native": "Italiano"},
    {"code": "pt", "name": "Portuguese", "flag": "🇵🇹", "native": "Português"},
    {"code": "ru", "name": "Russian", "flag": "🇷🇺", "native": "Русский"},
    {"code": "ja", "name": "Japanese", "flag": "🇯🇵", "native": "日本語"},
    {"code": "ko", "name": "Korean", "flag": "🇰🇷", "native": "한국어"},
    {"code": "zh", "name": "Chinese", "flag": "🇨🇳", "native": "中文"},
    {"code": "ar", "name": "Arabic", "flag": "🇸🇦", "native": "العربية"},
    {"code": "hi", "name": "Hindi", "flag": "🇮🇳", "native": "हिन्दी"},
    {"code": "ur", "name": "Urdu", "flag": "🇵🇰", "native": "اردو"},
    {"code": "bn", "name": "Bengali", "flag": "🇧🇩", "native": "বাংলা"},
    {"code": "ta", "name": "Tamil", "flag": "🇮🇳", "native": "தமிழ்"},
    {"code": "te", "name": "Telugu", "flag": "🇮🇳", "native": "తెలుగు"},
    {"code": "mr", "name": "Marathi", "flag": "🇮🇳", "native": "मराठी"},
    {"code": "gu", "name": "Gujarati", "flag": "🇮🇳", "native": "ગુજરાતી"},
    {"code": "kn", "name": "Kannada", "flag": "🇮🇳", "native": "ಕನ್ನಡ"},
    {"code": "ml", "name": "Malayalam", "flag": "🇮🇳", "native": "മലയാളം"},
    {"code": "pa", "name": "Punjabi", "flag": "🇮🇳", "native": "ਪੰਜਾਬੀ"},
    {"code": "tr", "name": "Turkish", "flag": "🇹🇷", "native": "Türkçe"},
    {"code": "nl", "name": "Dutch", "flag": "🇳🇱", "native": "Nederlands"},
    {"code": "sv", "name": "Swedish", "flag": "🇸🇪", "native": "Svenska"},
    {"code": "pl", "name": "Polish", "flag": "🇵🇱", "native": "Polski"},
    {"code": "vi", "name": "Vietnamese", "flag": "🇻🇳", "native": "Tiếng Việt"},
    {"code": "th", "name": "Thai", "flag": "🇹🇭", "native": "ไทย"},
    {"code": "id", "name": "Indonesian", "flag": "🇮🇩", "native": "Indonesia"},
]


@app.route("/languages/all", methods=["GET"])
def lingua_all_langs():
    from_lang = (request.args.get("from") or "en").strip()
    ck = f"langs:{from_lang}"
    cached = lang_cache.get(ck)
    if cached is not None:
        return jsonify(cached)

    # Try Convex first
    try:
        all_langs = cq("language:listLanguages", {"from_lang": from_lang}) or []
    except Exception as e:
        log.warning("Convex listLanguages failed: %s", e)
        all_langs = []

    # FALLBACK: if Convex empty → use local list
    if not all_langs:
        all_langs = [dict(l) for l in FALLBACK_LANGUAGES]

    learners = ["en", "hi", "ta", "te", "bn", "mr", "pa", "gu",
                "kn", "ml", "ur"]
    out = {"from_lang": from_lang, "learnable": all_langs,
           "learner_languages": learners,
           "source": "convex" if all_langs and all_langs != FALLBACK_LANGUAGES else "fallback",
           "count": len(all_langs)}
    lang_cache.set(ck, out)
    return jsonify(out)


@app.route("/languages/fallback", methods=["GET"])
def lingua_fallback_list():
    """Always returns the built-in list (no Convex)."""
    return jsonify({"languages": FALLBACK_LANGUAGES,
                    "count": len(FALLBACK_LANGUAGES)})


@app.route("/languages/<code>/units", methods=["GET"])
@require_login
def lingua_units(code):
    from_lang = (request.args.get("from") or "en").strip()
    try:
        units = cq("language:listUnits", {
            "language_code": code, "from_lang": from_lang,
        }) or []
    except Exception as e:
        log.warning("listUnits failed: %s", e)
        units = []
    # Fallback: synthetic unit
    if not units:
        units = [{
            "_id": f"{code}_u1",
            "title": "Basics",
            "language_code": code,
            "from_lang": from_lang,
            "lesson_count": 10,
        }]
    return jsonify({"units": units, "code": code, "from_lang": from_lang})


@app.route("/languages/<code>/progress", methods=["GET"])
@require_login
def lingua_progress(code):
    uid = current_uid()
    try:
        p = cq("language:getUserProgress",
               {"user_id": uid, "language_code": code})
    except Exception:
        p = None
    return jsonify(p or {
        "current_unit": 1, "current_lesson": 1, "total_xp": 0,
        "daily_streak": 0, "lessons_completed": 0, "words_learned": 0,
    })


@app.route("/languages/<code>/units/<unit_id>/lessons/<int:lesson_num>",
           methods=["GET"])
@require_login
def lingua_get_lesson(code, unit_id, lesson_num):
    from_lang = (request.args.get("from") or "en").strip()
    units = []
    try:
        units = cq("language:listUnits",
                   {"language_code": code, "from_lang": from_lang}) or []
    except Exception:
        pass
    unit_title = "Basics"
    for u in units:
        if u["_id"] == unit_id:
            unit_title = u["title"]
            break

    existing = None
    try:
        existing = cq("language:getLesson",
                      {"unit_id": unit_id, "lesson_number": lesson_num})
    except Exception:
        pass

    if existing:
        try:
            data = json.loads(existing["exercises_json"])
            return jsonify({"ok": True, "lesson": {
                "id": existing["_id"],
                "title": existing["title"], **data,
            }})
        except Exception:
            pass

    lesson_data = nv.generate_lesson(
        target_lang=code, from_lang=from_lang,
        unit_title=unit_title,
        lesson_title=f"Lesson {lesson_num}",
        level="A1", count=12,
    )
    if "error" in lesson_data:
        return jsonify({"error": lesson_data["error"]}), 500

    lid = None
    try:
        lid = cm("language:saveLesson", {
            "language_code": code, "unit_id": unit_id,
            "lesson_number": lesson_num,
            "title": lesson_data.get("title", f"Lesson {lesson_num}"),
            "exercises_json": json.dumps(lesson_data),
        })
    except Exception:
        pass

    return jsonify({"ok": True, "lesson": {"id": lid, **lesson_data}})


@app.route("/languages/<code>/lessons/<lesson_id>/complete", methods=["POST"])
@require_login
def lingua_complete_lesson(code, lesson_id):
    uid = current_uid()
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

    result = {}
    try:
        cm("language:recordAttempt", {
            "user_id": uid, "language_code": code,
            "lesson_id": lesson_id, "unit_number": unit_number,
            "lesson_number": lesson_number,
            "score": score, "total": total,
            "time_taken": time_taken,
            "mistakes_json": json.dumps(mistakes),
            "xp_gained": xp,
        })
        result = cm("language:upsertProgress", {
            "user_id": uid, "language_code": code,
            "from_lang": "en",
            "current_unit": unit_number,
            "current_lesson": lesson_number + 1,
            "xp_delta": xp, "lessons_delta": 1,
            "words_delta": len(vocab_learned),
        }) or {}
    except Exception as e:
        log.warning("complete_lesson DB failed: %s", e)

    if vocab_learned:
        try:
            cm("language:bulkAddVocab", {
                "user_id": uid, "language_code": code,
                "words": [{
                    "word": v.get("word", ""),
                    "translation": v.get("translation", ""),
                    "example": v.get("example", ""),
                } for v in vocab_learned],
                "source": "lesson",
            })
        except Exception:
            pass

    _award_exp(uid, "language_lesson")
    _increment_counter(uid, "language_lessons")
    _check_badges(uid)
    return jsonify({"ok": True, "xp_gained": xp,
                    "streak": result.get("streak", 1)})


# ============================================================
# CHAT STREAM (upgraded — heartbeat + safer SSE)
# ============================================================
def _sse(obj):
    """Encode dict as SSE data line."""
    try:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")
    except Exception:
        return b""


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
        final_message = ((message or "Analyze")
                         + "\n\n[Attached: " + ", ".join(attachments) + "]")
    sender = user["username"] if chat_owner_id != user["_id"] else None

    user_msg_payload = {
        "chat_id": chat_id, "role": "user",
        "content": ("💡 Deep Explain: " if deep_explain else "") + final_message,
    }
    if attachments:
        user_msg_payload["attachments"] = attachments
    if sender:
        user_msg_payload["sender"] = sender
    cm("chats:appendMessage", user_msg_payload)

    # Cached settings/personas
    uid = user["_id"]
    ck_set = f"settings:{uid}"
    user_settings = settings_cache.get(ck_set)
    if user_settings is None:
        user_settings = cq("misc:getSettings", {"user_id": uid}) or {}
        settings_cache.set(ck_set, user_settings)

    ck_p = f"personas:{uid}"
    persona_cache_data = persona_cache.get(ck_p)
    if persona_cache_data is None:
        items = cq("misc:listPersonas", {"user_id": uid}) or []
        persona_cache_data = {"personas": {p["slug"]: {
            "name": p["name"], "prompt": p["prompt"], "icon": p["icon"],
        } for p in items}}
        persona_cache.set(ck_p, persona_cache_data)
    user_personas = persona_cache_data.get("personas", {})

    memory_items = cq("misc:listMemory", {"user_id": uid}) or []
    user_memory = [{"fact": m["fact"]} for m in memory_items]

    def _on_usage(_uid, model, ti, to):
        record_usage(uid, model, ti, to)

    def generate():
        yield _sse({"chat_id": chat_id})
        full = ""
        try:
            if deep_explain:
                for chunk in nv.ask_groq_stream(
                    final_message, system_prompt=nv.DEEP_EXPLAIN_SYSTEM,
                    custom_instructions=user_settings.get("custom_instructions", ""),
                    user_personas=user_personas, user=sid,
                    on_usage=_on_usage, memory=user_memory, session_id=sid,
                ):
                    full += chunk
                    yield _sse({"chunk": chunk})
                cm("chats:appendMessage", {"chat_id": chat_id,
                                            "role": "assistant",
                                            "content": full})
                _award_exp(uid, "chat_message")
                _increment_counter(uid, "chat_messages")
                _check_badges(uid)
                yield _sse({"done": True, "full": full})
                return

            reminder_result = nv.parse_reminder(message)
            if reminder_result:
                when_dt = datetime.datetime.fromisoformat(reminder_result["when"])
                cm("misc:createReminder", {
                    "user_id": uid,
                    "text": reminder_result["text"],
                    "when_iso": reminder_result["when"],
                })
                full = (f"✓ **Reminder set**\n\n"
                        f"- **Kaam:** {reminder_result['text']}\n"
                        f"- **Kab:** {when_dt.strftime('%A, %d %B %Y, %I:%M %p')} (IST)")
                for i in range(0, len(full), 4):
                    yield _sse({"chunk": full[i:i + 4]})
                cm("chats:appendMessage", {"chat_id": chat_id,
                                            "role": "assistant",
                                            "content": full})
                yield _sse({"done": True, "full": full})
                return

            p = message.lower().strip()
            is_quiz = (p == "/quiz" or p == "quiz" or p.startswith("/quiz ")
                       or p.startswith("quiz ") or p.endswith(" quiz"))
            simple_prefixes = ("time", "weather", "news", "search", "wiki",
                                "calc", "note", "notes", "translate", "pdf ",
                                "save code", "calculate ")
            simple_words = ["mausam", "samay", "khabar", "baj", "waqt",
                            "dhundo", "hello", "hi", "hey", "namaste",
                            "bye", "thanks"]
            is_simple = (p.startswith(simple_prefixes)
                         or any(w in p for w in simple_words))
            quiz_running = _quiz_active(sid)

            if p.startswith(("search ", "google ", "dhundo ",
                             "khojo ", "dhoondo ")):
                q = re.sub(r"^(search|google|dhundo|khojo|dhoondo)\s+",
                           "", message, flags=re.IGNORECASE).strip()
                results = nv.web_search_structured(q, max_results=5)
                full = nv.format_search_results_with_citations(q, results)
                for i in range(0, len(full), 4):
                    yield _sse({"chunk": full[i:i + 4]})
            elif p.startswith(("news ", "khabar ", "khabrein ")):
                topic = re.sub(r"^(news|khabar|khabrein)\s+", "",
                               message, flags=re.IGNORECASE).strip()
                full = nv.get_news(topic or None, max_items=5)
                for i in range(0, len(full), 4):
                    yield _sse({"chunk": full[i:i + 4]})
            elif (is_simple or is_quiz or quiz_running
                  or _active_model().startswith("ollama:")):
                full = novex(final_message, user=sid,
                             settings=user_settings,
                             personas=user_personas,
                             memory=user_memory, session_id=sid)
                for i in range(0, len(full), 4):
                    yield _sse({"chunk": full[i:i + 4]})
            else:
                for chunk in nv.ask_groq_stream(
                    final_message,
                    custom_instructions=user_settings.get("custom_instructions", ""),
                    user_personas=user_personas, user=sid,
                    on_usage=_on_usage, memory=user_memory, session_id=sid,
                ):
                    full += chunk
                    yield _sse({"chunk": chunk})
        except Exception as e:
            log.exception("stream error")
            full = f"⚠️ Error: {e}"
            yield _sse({"chunk": full})

        try:
            cm("chats:appendMessage", {"chat_id": chat_id,
                                        "role": "assistant",
                                        "content": full})
            _award_exp(uid, "chat_message")
            _increment_counter(uid, "chat_messages")
            _check_badges(uid)
        except Exception as e:
            log.warning("post-stream DB: %s", e)

        yield _sse({"done": True, "full": full})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# CHATS
# ============================================================
@app.route("/chats", methods=["GET"])
@require_login
def list_chats():
    uid = current_uid()
    project_filter = request.args.get("project")
    pid = project_filter if project_filter else None
    return jsonify(cq("chats:listByUser",
                       {"user_id": uid, "project_id": pid}) or [])


@app.route("/chats/search", methods=["GET"])
@require_login
def search_chats():
    uid = current_uid()
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify({"chats": []})
    try:
        chats = cq("chats:listByUser", {"user_id": uid, "project_id": None}) or []
    except Exception:
        chats = []
    results = [c for c in chats if q in (c.get("title") or "").lower()]
    return jsonify({"chats": results, "count": len(results)})


@app.route("/chats/<cid>", methods=["GET"])
@require_login
def get_chat(cid):
    uid = current_uid()
    c = cq("chats:getById", {"id": cid, "viewer_id": uid})
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


# ============================================================
# SHARE
# ============================================================
@app.route("/share", methods=["POST"])
@require_login
def create_share():
    uid = current_uid()
    data = request.get_json() or {}
    cid = data.get("chat_id")
    if not cid:
        return jsonify({"error": "chat_id chahiye"}), 400
    c = cq("chats:getById", {"id": cid, "viewer_id": uid})
    if not c:
        return jsonify({"error": "Chat nahi mili"}), 404
    token = uuid.uuid4().hex[:12]
    cm("misc:createSharedLink", {
        "token": token, "chat_id": cid,
        "owner_id": uid, "title": c.get("title", "Shared chat"),
    })
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
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(chat.get("title", "Shared"))}</title>
<style>body{{background:#0d0d0d;color:#ececec;font-family:system-ui;margin:0;padding:20px}}.wrap{{max-width:780px;margin:0 auto}}.head{{border-bottom:1px solid #ffffff20;padding-bottom:16px;margin-bottom:24px;display:flex;justify-content:space-between}}.head h1{{font-size:20px;margin:0}}.head a{{color:#10a37f;text-decoration:none;font-weight:700}}.msg{{margin-bottom:20px;padding:14px 18px;border-radius:12px;background:#1a1a1a}}.msg.user{{background:#262626;margin-left:auto;max-width:80%}}.msg.bot{{background:#000;border:1px solid #ffffff10}}.role{{font-size:11px;text-transform:uppercase;color:#8e8e8e;margin-bottom:6px;font-weight:600}}.content{{white-space:pre-wrap;line-height:1.7}}.footer{{margin-top:40px;padding-top:20px;border-top:1px solid #ffffff20;text-align:center;color:#8e8e8e;font-size:13px}}.footer a{{color:#10a37f}}</style></head><body><div class="wrap"><div class="head"><h1>{esc(chat.get("title", "Shared"))}</h1><a href="/">NOVEX AI →</a></div>{msgs}<div class="footer">Read-only · <a href="/">Try NOVEX AI</a></div></div></body></html>'''


@app.route("/shared-with-me", methods=["GET"])
@require_login
def shared_with_me():
    uid = current_uid()
    return jsonify(cq("chats:getSharedWithUser", {"user_id": uid}) or [])


# ============================================================
# TTS / TRANSLATE / VOICES
# ============================================================
@app.route("/tts", methods=["POST"])
@require_login
def tts():
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    voice_key = data.get("voice", "hi-male")
    if not text:
        return jsonify({"error": "Koi text nahi"}), 400
    if len(text) > 3000:
        text = text[:3000]
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
        log.exception("TTS failed")
        return jsonify({"error": f"TTS error: {e}"}), 500


@app.route("/voices", methods=["GET"])
def list_voices():
    """Return available TTS voices grouped by language."""
    groups = defaultdict(list)
    for key, azure_voice in VOICES.items():
        lang = key.split("-")[0]
        groups[lang].append({"key": key, "voice": azure_voice})
    return jsonify({"voices": dict(groups), "count": len(VOICES),
                    "langs": list(groups.keys())})


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
        return ("/* not found */", 404, {"Content-Type": "text/css"})


@app.route("/themes-extra.css")
def themes_extra_css():
    try:
        return send_from_directory(".", "themes-extra.css")
    except Exception:
        return ("/* not found */", 404, {"Content-Type": "text/css"})


@app.route("/ui-modes.css")
def ui_modes_css():
    try:
        return send_from_directory(".", "ui-modes.css")
    except Exception:
        return ("/* not found */", 404, {"Content-Type": "text/css"})


@app.route("/ui-modes.js")
def ui_modes_js():
    try:
        return send_from_directory(".", "ui-modes.js")
    except Exception:
        return ("/* not found */", 404,
                {"Content-Type": "application/javascript"})


@app.route("/voice/<path:filename>")
def voice_file(filename):
    return send_from_directory(VOICE_DIR, filename)


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


# ============================================================
# HEALTH
# ============================================================
@app.route("/health", methods=["GET"])
def health():
    convex_ok = False
    try:
        cq("users:getByUsername", {"username": "__health_check__"})
        convex_ok = True
    except Exception:
        pass
    return jsonify({
        "ok": True, "service": "novex-ai", "version": "8.0",
        "totp": TOTP_AVAILABLE,
        "brevo": bool(BREVO_API_KEY),
        "convex": convex_ok,
        "google_oauth": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
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
            "lingua_fallback": True,
            "voice_tutor": True,
            "voices": len(VOICES),
            "rooms": True,
            "peer_doubts": True,
            "batch1": True,
            "quiz_v2": True,
            "search_realtime": True,
            "themes": 52,
            "ui_modes": 10,
            "google_login": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            "chat_search": True,
        },
    })


@app.route("/health/deep", methods=["GET"])
def health_deep():
    """Detailed diagnostics (no auth — safe subset only)."""
    checks = {}

    # Convex
    try:
        cq("users:getByUsername", {"username": "__health__"})
        checks["convex"] = {"ok": True}
    except Exception as e:
        checks["convex"] = {"ok": False, "error": str(e)[:120]}

    # Groq key
    checks["groq"] = {"ok": bool(os.getenv("GROQ_API_KEY"))}

    # Serper
    checks["serper"] = {"ok": bool(os.getenv("SERPER_API_KEY"))}

    # Brevo
    checks["brevo"] = {"ok": bool(BREVO_API_KEY)}

    # TOTP
    checks["totp"] = {"ok": TOTP_AVAILABLE}

    # Google
    checks["google_oauth"] = {
        "ok": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    }

    # Edge TTS
    try:
        import edge_tts  # noqa: F401
        checks["edge_tts"] = {"ok": True}
    except ImportError:
        checks["edge_tts"] = {"ok": False, "error": "not installed"}

    overall = all(v.get("ok") for v in checks.values())
    return jsonify({"ok": overall, "checks": checks})


# ============================================================
# ERROR HANDLERS
# ============================================================
@app.errorhandler(404)
def _404(e):
    if request.path.startswith("/api") or request.path.endswith(".json"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(".", "index.html")


@app.errorhandler(413)
def _413(e):
    return jsonify({"error": "File too large (max 25 MB)"}), 413


@app.errorhandler(500)
def _500(e):
    log.exception("500 error at %s", request.path)
    return jsonify({"error": "Internal server error"}), 500


# ============================================================
# INIT auth_extra
# ============================================================
from auth_extra import init as _auth_extra_init

_auth_extra_init(cq, cm, send_email, APP_URL, password_strength)


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 10000))
    HOST = os.getenv("HOST", "0.0.0.0")
    print("=" * 62)
    print("  NOVEX AI v8.0 — UPGRADED")
    print("=" * 62)
    print(f"  URL:          http://{HOST}:{PORT}")
    print(f"  Convex:       {os.getenv('CONVEX_URL', 'NOT SET')}")
    print(f"  Brevo:        {'✓' if BREVO_API_KEY else '✗'}")
    print(f"  2FA:          {'✓' if TOTP_AVAILABLE else '✗'}")
    print(f"  Google OAuth: {'✓' if GOOGLE_CLIENT_ID else '✗'}")
    print(f"  Serper:       {'✓' if os.getenv('SERPER_API_KEY') else '✗'}")
    print(f"  Voices:       {len(VOICES)}")
    print(f"  Themes:       52  ·  UI Modes: 10")
    print(f"  Lingua:       fallback enabled ({len(FALLBACK_LANGUAGES)} langs)")
    print("=" * 62)
    serve(app, host=HOST, port=PORT, threads=16,
          send_bytes=1, channel_timeout=300)