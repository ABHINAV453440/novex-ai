"""
Advanced auth blueprint: Google OAuth + Magic Link + Guest.
Injected with cq/cm/send_email from server.py.
"""
from flask import Blueprint, request, jsonify, session, redirect
from urllib.parse import urlencode
import os
import secrets
import datetime
import requests
from werkzeug.security import generate_password_hash

auth_extra_bp = Blueprint("auth_extra", __name__)

_cq = None
_cm = None
_send_email = None
_APP_URL = None
_pw_strength = None

def init(cq_fn, cm_fn, send_email_fn, app_url, pw_strength_fn):
    global _cq, _cm, _send_email, _APP_URL, _pw_strength
    _cq = cq_fn
    _cm = cm_fn
    _send_email = send_email_fn
    _APP_URL = app_url
    _pw_strength = pw_strength_fn

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")


# ============ GOOGLE OAUTH ============
@auth_extra_bp.route("/auth/google")
def google_login():
    if not GOOGLE_CLIENT_ID:
        return redirect("/?error=google_not_configured")
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@auth_extra_bp.route("/auth/google/callback")
def google_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or state != session.get("oauth_state"):
        return redirect("/?error=oauth_state")
    session.pop("oauth_state", None)
    try:
        token_res = requests.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }, timeout=15).json()
    except Exception:
        return redirect("/?error=token_exchange")
    if "access_token" not in token_res:
        return redirect("/?error=token_missing")
    try:
        info = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_res['access_token']}"},
            timeout=15,
        ).json()
    except Exception:
        return redirect("/?error=userinfo")
    google_id = info.get("id")
    email = (info.get("email") or "").lower()
    name = info.get("name") or email.split("@")[0]
    if not google_id or not email:
        return redirect("/?error=no_email")
    user = _cq("users:getByGoogleId", {"google_id": google_id})
    if not user:
        user = _cq("users:getByEmail", {"email": email})
        if user:
            _cm("users:linkGoogle", {"id": user["_id"], "google_id": google_id})
        else:
            username = _gen_username(email)
            uid = _cm("users:create", {
                "username": username,
                "email": email,
                "password_hash": "",
                "display_name": name[:40],
                "email_verified": True,
                "google_id": google_id,
                "auth_provider": "google",
            })
            user = _cq("users:getById", {"id": uid})
    if not user:
        return redirect("/?error=user_creation")
    session.permanent = True
    session["user"] = user["username"]
    session["user_id"] = user["_id"]
    return redirect("/")


def _gen_username(email):
    base = email.split("@")[0].lower()
    base = "".join(c for c in base if c.isalnum() or c == "_")[:15] or "user"
    for i in range(20):
        cand = base if i == 0 else f"{base}{i}"
        if not _cq("users:getByUsername", {"username": cand}):
            return cand
    return f"user{secrets.token_hex(4)}"


# ============ MAGIC LINK ============
@auth_extra_bp.route("/auth/magic-link", methods=["POST"])
def magic_link_send():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "Email chahiye"}), 400
    user = _cq("users:getByEmail", {"email": email})
    # Always OK (prevent enumeration)
    if not user:
        return jsonify({"ok": True, "message": "If email exists, link sent."})
    token = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1000000):06d}"
    _cm("auth:createReset", {
        "token": token, "username": user["username"],
        "email": email, "code": code,
    })
    link = f"{_APP_URL}/auth/magic-verify?token={token}"
    body = (
        f"Hi {user.get('display_name', user['username'])},\n\n"
        f"Click this link to login to NOVEX AI:\n\n{link}\n\n"
        f"Or use this code: {code}\n\n"
        f"Valid 15 minutes. If you didn't request this, ignore.\n\n— NOVEX AI"
    )
    _send_email(email, "NOVEX AI — Magic Login Link", body)
    return jsonify({"ok": True, "message": "If email exists, link sent."})


@auth_extra_bp.route("/auth/magic-verify")
def magic_link_verify():
    token = request.args.get("token")
    if not token:
        return redirect("/?error=invalid_token")
    entry = _cq("auth:findResetByToken", {"token": token})
    if not entry:
        return redirect("/?error=expired")
    try:
        if datetime.datetime.fromisoformat(entry["expires"]) < datetime.datetime.now():
            return redirect("/?error=expired")
    except Exception:
        pass
    user = _cq("users:getByUsername", {"username": entry["username"]})
    if not user:
        return redirect("/?error=user_not_found")
    _cm("auth:deleteReset", {"token": token})
    session.permanent = True
    session["user"] = user["username"]
    session["user_id"] = user["_id"]
    return redirect("/")


# ============ GUEST LOGIN ============
@auth_extra_bp.route("/auth/guest", methods=["POST"])
def guest_login():
    guest_id = session.get("guest_id")
    if guest_id:
        user = _cq("users:getById", {"id": guest_id})
        if user:
            session.permanent = True
            session["user"] = user["username"]
            session["user_id"] = user["_id"]
            return jsonify({"ok": True, "username": user["username"], "display_name": "Guest"})
    username = f"guest_{secrets.token_hex(4)}"
    uid = _cm("users:create", {
        "username": username,
        "email": f"{username}@guest.novex.local",
        "password_hash": "",
        "display_name": "Guest",
        "email_verified": True,
        "auth_provider": "guest",
    })
    session.permanent = True
    session["user"] = username
    session["user_id"] = uid
    session["guest_id"] = uid
    return jsonify({"ok": True, "username": username, "display_name": "Guest"})


# ============ GUEST UPGRADE ============
@auth_extra_bp.route("/auth/guest-upgrade", methods=["POST"])
def guest_upgrade():
    guest_id = session.get("guest_id")
    if not guest_id:
        return jsonify({"error": "Not a guest session"}), 400
    user = _cq("users:getById", {"id": guest_id})
    if not user or user.get("auth_provider") != "guest":
        return jsonify({"error": "Not a guest"}), 400
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not email or not password:
        return jsonify({"error": "Sab fields chahiye"}), 400
    if len(username) < 3 or len(username) > 20:
        return jsonify({"error": "Username 3-20 chars"}), 400
    if not username.replace("_", "").isalnum():
        return jsonify({"error": "Username: letters, numbers, _"}), 400
    if _cq("users:getByUsername", {"username": username}):
        return jsonify({"error": "Username taken"}), 400
    if _cq("users:getByEmail", {"email": email}):
        return jsonify({"error": "Email already registered"}), 400
    score, label, issues = _pw_strength(password)
    if score < 2:
        return jsonify({"error": "Password weak: " + ", ".join(issues)}), 400
    _cm("users:create", {
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password),
        "display_name": user.get("display_name", username)[:40],
        "email_verified": True,
        "auth_provider": "local",
    })
    # Note: chats stay attached to old user_id. Migrate on Convex if needed.
    # For now, log in as new user
    new_user = _cq("users:getByUsername", {"username": username})
    session.permanent = True
    session["user"] = new_user["username"]
    session["user_id"] = new_user["_id"]
    session.pop("guest_id", None)
    return jsonify({"ok": True, "username": username, "display_name": new_user.get("display_name", username)})