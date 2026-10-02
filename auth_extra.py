"""
Advanced auth blueprint: Magic Link + Guest Mode + Account Linking.
Google OAuth login is in app.py — this blueprint adds the extras.

Injected via: init(cq, cm, send_email, app_url, pw_strength)

Improvements:
  - Thread-safe rate limiting
  - Session fixation protection
  - Timing-safe token comparison
  - Safe-redirect allow-list
  - Guest → Registered data migration
  - Proper structured logging
  - Account-linking flow
  - /auth/providers introspection endpoint
"""
from flask import Blueprint, request, jsonify, session, redirect
from urllib.parse import urlencode, urlparse
import os
import re
import secrets
import datetime
import logging
import threading
import time
from collections import defaultdict
import requests
from werkzeug.security import generate_password_hash

log = logging.getLogger("novex.auth_extra")

auth_extra_bp = Blueprint("auth_extra", __name__)

# ============================================================
# DEPENDENCY INJECTION
# ============================================================
_cq = None
_cm = None
_send_email = None
_APP_URL = None
_pw_strength = None


def init(cq_fn, cm_fn, send_email_fn, app_url, pw_strength_fn):
    """Called once from app.py after Convex client is ready."""
    global _cq, _cm, _send_email, _APP_URL, _pw_strength
    _cq = cq_fn
    _cm = cm_fn
    _send_email = send_email_fn
    _APP_URL = app_url
    _pw_strength = pw_strength_fn
    log.info("auth_extra initialized (app_url=%s)", app_url)


# ============================================================
# CONFIG
# ============================================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")

MAGIC_LINK_TTL_MIN = int(os.getenv("MAGIC_LINK_TTL_MIN", "15"))
GUEST_SESSION_DAYS = int(os.getenv("GUEST_SESSION_DAYS", "30"))

# Only these redirect paths are allowed after login
_SAFE_REDIRECT_PATHS = ("/", "/app", "/chat", "/settings", "/profile",
                        "/dashboard", "/quiz", "/lingua")


# ============================================================
# RATE LIMIT (thread-safe)
# ============================================================
_rl_lock = threading.Lock()
_rl_buckets: "defaultdict[str, list]" = defaultdict(list)


def _rate_limit(key, max_attempts=5, window_sec=600):
    """Sliding window. Returns True if allowed."""
    now = time.time()
    with _rl_lock:
        bucket = _rl_buckets[key]
        bucket[:] = [t for t in bucket if now - t < window_sec]
        if len(bucket) >= max_attempts:
            return False
        bucket.append(now)
        return True


def _client_ip():
    return (request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
            .split(",")[0].strip())


# ============================================================
# SMALL HELPERS
# ============================================================
def _safe_redirect(path, default="/"):
    """Reject absolute URLs (open-redirect protection)."""
    if not path:
        return default
    parsed = urlparse(path)
    if parsed.netloc or parsed.scheme:
        return default
    if not path.startswith("/"):
        return default
    if path in _SAFE_REDIRECT_PATHS:
        return path
    if path.startswith("/s/"):  # shared links OK
        return path
    return default


def _timing_safe_eq(a, b):
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    if len(a) != len(b):
        return False
    return secrets.compare_digest(a, b)


def _is_valid_email(email):
    return bool(re.match(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        email or ""
    ))


def _gen_username(email):
    """Generate a unique username from email."""
    base = (email or "user").split("@")[0].lower()
    base = "".join(c for c in base if c.isalnum() or c == "_")[:15] or "user"
    for i in range(20):
        cand = base if i == 0 else f"{base}{i}"
        try:
            if not _cq("users:getByUsername", {"username": cand}):
                return cand
        except Exception as e:
            log.warning("_gen_username check failed: %s", e)
    return f"user{secrets.token_hex(4)}"


def _login_session(user):
    """Set session safely — clears old data (session fixation protection)."""
    session.clear()
    session.permanent = True
    session["user"] = user["username"]
    session["user_id"] = user["_id"]


def _record_login(uid, success=True):
    try:
        _cm("auth:recordLogin", {
            "user_id": uid,
            "ip": _client_ip(),
            "ua": (request.headers.get("User-Agent") or "")[:200],
            "success": success,
        })
    except Exception:
        pass


# ============================================================
# PROVIDERS INTROSPECTION
# ============================================================
@auth_extra_bp.route("/auth/providers", methods=["GET"])
def auth_providers():
    """Return which auth methods are enabled (used by login UI)."""
    return jsonify({
        "local": True,
        "google": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        "magic_link": True,
        "guest": True,
    })


# ============================================================
# MAGIC LINK
# ============================================================
@auth_extra_bp.route("/auth/magic-link", methods=["POST"])
def magic_link_send():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()

    if not email or not _is_valid_email(email):
        return jsonify({"error": "Valid email chahiye"}), 400

    # Rate-limit: per-IP and per-email
    if not _rate_limit(f"ml_ip:{_client_ip()}", 5, 600):
        return jsonify({"error": "Too many requests"}), 429
    if not _rate_limit(f"ml_email:{email}", 3, 600):
        return jsonify({"error": "Too many requests"}), 429

    try:
        user = _cq("users:getByEmail", {"email": email})
    except Exception as e:
        log.warning("magic_link lookup: %s", e)
        user = None

    # Prevent account enumeration — always return same message
    if not user:
        return jsonify({"ok": True, "message": "If email exists, link sent."})

    token = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1000000):06d}"

    try:
        _cm("auth:createReset", {
            "token": token,
            "username": user["username"],
            "email": email,
            "code": code,
        })
    except Exception:
        log.exception("magic_link createReset failed")
        return jsonify({"error": "Could not send"}), 500

    link = f"{_APP_URL}/auth/magic-verify?token={token}"
    body = (
        f"Hi {user.get('display_name', user['username'])},\n\n"
        f"Click this link to login to NOVEX AI:\n\n{link}\n\n"
        f"Or use this code: {code}\n\n"
        f"Valid {MAGIC_LINK_TTL_MIN} minutes. "
        f"If you didn't request this, ignore.\n\n— NOVEX AI"
    )
    try:
        _send_email(email, "NOVEX AI — Magic Login Link", body)
    except Exception:
        log.exception("magic_link send failed")

    return jsonify({"ok": True, "message": "If email exists, link sent."})


@auth_extra_bp.route("/auth/magic-verify")
def magic_link_verify():
    token = (request.args.get("token") or "").strip()
    if not token or len(token) < 16:
        return redirect("/?error=invalid_token")

    try:
        entry = _cq("auth:findResetByToken", {"token": token})
    except Exception as e:
        log.warning("magic_verify lookup: %s", e)
        return redirect("/?error=server_error")

    if not entry:
        return redirect("/?error=expired")

    # Timing-safe token comparison
    if not _timing_safe_eq(entry.get("token", ""), token):
        return redirect("/?error=expired")

    # Expiry check
    try:
        if datetime.datetime.fromisoformat(entry["expires"]) < datetime.datetime.now():
            return redirect("/?error=expired")
    except Exception:
        pass

    try:
        user = _cq("users:getByUsername", {"username": entry["username"]})
    except Exception:
        return redirect("/?error=server_error")

    if not user:
        return redirect("/?error=user_not_found")

    # Single-use — delete immediately
    try:
        _cm("auth:deleteReset", {"token": token})
    except Exception:
        pass

    _login_session(user)
    _record_login(user["_id"], True)
    return redirect("/")


# ============================================================
# GUEST LOGIN
# ============================================================
@auth_extra_bp.route("/auth/guest", methods=["POST"])
def guest_login():
    if not _rate_limit(f"guest:{_client_ip()}", 5, 600):
        return jsonify({"error": "Too many requests"}), 429

    # Returning guest?
    guest_id = session.get("guest_id")
    if guest_id:
        try:
            user = _cq("users:getById", {"id": guest_id})
        except Exception:
            user = None
        if user and user.get("auth_provider") == "guest":
            session.permanent = True
            session["user"] = user["username"]
            session["user_id"] = user["_id"]
            return jsonify({
                "ok": True,
                "username": user["username"],
                "display_name": "Guest",
                "returning": True,
            })

    # New guest
    username = f"guest_{secrets.token_hex(4)}"
    try:
        uid = _cm("users:create", {
            "username": username,
            "email": f"{username}@guest.novex.local",
            "password_hash": None,
            "display_name": "Guest",
            "email_verified": True,
            "auth_provider": "guest",
        })
    except Exception:
        log.exception("guest create failed")
        return jsonify({"error": "Guest login failed"}), 500

    session.permanent = True
    session["user"] = username
    session["user_id"] = uid
    session["guest_id"] = uid
    session["guest_since"] = datetime.datetime.now().isoformat()
    return jsonify({
        "ok": True,
        "username": username,
        "display_name": "Guest",
        "returning": False,
    })


# ============================================================
# GUEST UPGRADE (with data migration)
# ============================================================
@auth_extra_bp.route("/auth/guest-upgrade", methods=["POST"])
def guest_upgrade():
    guest_id = session.get("guest_id")
    if not guest_id:
        return jsonify({"error": "Not a guest session"}), 400

    if not _rate_limit(f"upgrade:{_client_ip()}", 5, 600):
        return jsonify({"error": "Too many requests"}), 429

    try:
        user = _cq("users:getById", {"id": guest_id})
    except Exception:
        user = None
    if not user or user.get("auth_provider") != "guest":
        return jsonify({"error": "Not a guest"}), 400

    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    # Validation
    if not username or not email or not password:
        return jsonify({"error": "Sab fields chahiye"}), 400
    if len(username) < 3 or len(username) > 20:
        return jsonify({"error": "Username 3-20 chars"}), 400
    if not username.replace("_", "").isalnum():
        return jsonify({"error": "Username: letters, numbers, _"}), 400
    if not _is_valid_email(email):
        return jsonify({"error": "Valid email daalein"}), 400

    # Uniqueness
    try:
        if _cq("users:getByUsername", {"username": username}):
            return jsonify({"error": "Username taken"}), 400
        if _cq("users:getByEmail", {"email": email}):
            return jsonify({"error": "Email already registered"}), 400
    except Exception as e:
        log.warning("guest_upgrade lookup: %s", e)
        return jsonify({"error": "Server error"}), 500

    # Password strength
    score, _label, issues = _pw_strength(password)
    if score < 2:
        return jsonify({"error": "Password weak: " + ", ".join(issues)}), 400

    # Create the real account
    try:
        new_uid = _cm("users:create", {
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
            "display_name": user.get("display_name", username)[:40],
            "email_verified": True,
            "auth_provider": "local",
            "upgraded_from_guest": guest_id,
        })
    except Exception:
        log.exception("guest_upgrade create failed")
        return jsonify({"error": "Could not create user"}), 500

    # ---- Best-effort data migration ----
    migrations = {
        "chats": ("chats:reassignUser",
                  {"from_user_id": guest_id, "to_user_id": new_uid}),
        "progress": ("misc:reassignProgress",
                     {"from_user_id": guest_id, "to_user_id": new_uid}),
        "memory": ("misc:reassignMemory",
                   {"from_user_id": guest_id, "to_user_id": new_uid}),
        "flashcards": ("misc:reassignFlashcards",
                       {"from_user_id": guest_id, "to_user_id": new_uid}),
    }
    migrated = []
    for name, (mutation, args) in migrations.items():
        try:
            _cm(mutation, args)
            migrated.append(name)
        except Exception as e:
            log.info("%s migration skipped: %s", name, e)

    # Mark old guest as migrated (so it doesn't linger)
    try:
        _cm("users:markMigrated", {"id": guest_id, "new_id": new_uid})
    except Exception:
        pass

    # Load fresh user doc
    try:
        new_user = _cq("users:getByUsername", {"username": username})
    except Exception:
        return jsonify({
            "ok": True,
            "message": "Account created — please log in",
            "username": username,
        }), 200

    _login_session(new_user)
    session.pop("guest_id", None)
    session.pop("guest_since", None)
    return jsonify({
        "ok": True,
        "username": username,
        "display_name": new_user.get("display_name", username),
        "migrated": migrated,
    })


# ============================================================
# GUEST LOGOUT (forget session, keep guest user)
# ============================================================
@auth_extra_bp.route("/auth/guest-logout", methods=["POST"])
def guest_logout():
    session.pop("guest_id", None)
    session.pop("guest_since", None)
    session.pop("user", None)
    session.pop("user_id", None)
    return jsonify({"ok": True})


# ============================================================
# ACCOUNT LINKING (start Google link flow)
# ============================================================
@auth_extra_bp.route("/auth/link/google", methods=["POST"])
def link_google_start():
    """
    Start Google account linking for an already-logged-in user.
    Redirects to Google; the existing /auth/google/callback
    detects `oauth_link_mode` and links instead of logging in.
    """
    if "user" not in session:
        return jsonify({"error": "Login required"}), 401
    if not GOOGLE_CLIENT_ID:
        return jsonify({"error": "Google not configured"}), 400

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    session["oauth_link_mode"] = True

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return jsonify({"ok": True, "url": url})


# ============================================================
# GOOGLE OAUTH — intentionally NOT defined here.
# ------------------------------------------------------------
# /auth/google and /auth/google/callback live in app.py.
# If you ever run this blueprint standalone (without app.py),
# uncomment the block below:
# ============================================================
# @auth_extra_bp.route("/auth/google")
# def google_login():
#     if not GOOGLE_CLIENT_ID:
#         return redirect("/?error=google_not_configured")
#     state = secrets.token_urlsafe(24)
#     session["oauth_state"] = state
#     params = {
#         "client_id": GOOGLE_CLIENT_ID,
#         "redirect_uri": GOOGLE_REDIRECT_URI,
#         "response_type": "code",
#         "scope": "openid email profile",
#         "state": state,
#         "access_type": "offline",
#         "prompt": "select_account",
#     }
#     return redirect("https://accounts.google.com/o/oauth2/v2/auth?"
#                     + urlencode(params))


# ============================================================
# DEBUG: rate-limit state (dev only)
# ============================================================
@auth_extra_bp.route("/auth/_rl_stats", methods=["GET"])
def _rl_stats():
    if os.getenv("FLASK_ENV") == "production":
        return jsonify({"error": "Not available"}), 404
    with _rl_lock:
        return jsonify({
            "buckets": len(_rl_buckets),
            "keys": {k: len(v) for k, v in list(_rl_buckets.items())[:20]},
        })