import functools
import hashlib
import secrets
import smtplib
import time
from email.message import EmailMessage

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)

RESET_TTL_SECONDS = 3600
MIN_PASSWORD = 8


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)
    return wrapped


def onboarded_required(view):
    """Logged in and has finished onboarding."""
    @functools.wraps(view)
    @login_required
    def wrapped(**kwargs):
        row = get_db().execute("SELECT onboarded FROM settings WHERE user_id = ?",
                               (g.user["id"],)).fetchone()
        if not row or not row["onboarded"]:
            return redirect(url_for("settings.onboarding"))
        return view(**kwargs)
    return wrapped


def _start_session(user_id):
    session.clear()
    session["user_id"] = user_id


@bp.route("/signup", methods=("GET", "POST"))
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        error = None
        if "@" not in email or len(email) > 254:
            error = "Enter a valid email address."
        elif len(password) < MIN_PASSWORD:
            error = f"Password must be at least {MIN_PASSWORD} characters."
        if error is None:
            db = get_db()
            try:
                cur = db.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                                 (email, generate_password_hash(password)))
            except db.IntegrityError:
                error = "An account with that email already exists."
            else:
                db.execute("INSERT INTO settings (user_id) VALUES (?)", (cur.lastrowid,))
                db.commit()
                _start_session(cur.lastrowid)
                return redirect(url_for("settings.onboarding"))
        flash(error, "error")
    return render_template("auth/signup.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            _start_session(user["id"])
            target = request.args.get("next", "")
            # Only follow local paths, never another site.
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("index")
            return redirect(target)
        flash("Incorrect email or password.", "error")
    return render_template("auth/login.html")


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


@bp.route("/forgot", methods=("GET", "POST"))
def forgot():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        db = get_db()
        user = db.execute("SELECT id, email FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO reset_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                       (_hash_token(token), user["id"], int(time.time()) + RESET_TTL_SECONDS))
            db.commit()
            _send_reset_email(user["email"], url_for("auth.reset", token=token, _external=True))
        # Same message either way so the form doesn't reveal who has an account.
        flash("If that email has an account, a reset link is on its way.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot.html")


@bp.route("/reset/<token>", methods=("GET", "POST"))
def reset(token):
    db = get_db()
    row = db.execute("SELECT * FROM reset_tokens WHERE token_hash = ?", (_hash_token(token),)).fetchone()
    if not row or row["used"] or row["expires_at"] < time.time():
        flash("That reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < MIN_PASSWORD:
            flash(f"Password must be at least {MIN_PASSWORD} characters.", "error")
        else:
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                       (generate_password_hash(password), row["user_id"]))
            db.execute("UPDATE reset_tokens SET used = 1 WHERE user_id = ?", (row["user_id"],))
            db.commit()
            flash("Password updated. You can log in now.", "info")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset.html")


def _send_reset_email(to, link):
    cfg = current_app.config
    if not cfg.get("SMTP_HOST"):
        # Development: no mail server configured, so print the link to the console.
        current_app.logger.warning("Password reset link for %s: %s", to, link)
        print(f"\n*** Password reset link for {to}: {link}\n", flush=True)
        return
    msg = EmailMessage()
    msg["Subject"] = "Reset your Day Planner password"
    msg["From"] = cfg["MAIL_FROM"]
    msg["To"] = to
    msg.set_content(f"Use this link to choose a new password (valid for 1 hour):\n\n{link}\n\n"
                    "If you didn't ask for this, you can ignore this email.")
    with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"]) as smtp:
        smtp.starttls()
        if cfg.get("SMTP_USER"):
            smtp.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
        smtp.send_message(msg)
