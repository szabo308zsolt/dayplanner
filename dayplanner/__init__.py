import os
import secrets
from pathlib import Path

from flask import Flask, abort, g, redirect, request, session, url_for
from markupsafe import Markup

from . import db
from .timeutil import fmt_duration, min_to_hm


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.update(
        DATABASE=os.path.join(app.instance_path, "dayplanner.sqlite"),
        SECRET_KEY=os.environ.get("SECRET_KEY") or _instance_secret(app.instance_path),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SMTP_HOST=os.environ.get("SMTP_HOST"),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USER=os.environ.get("SMTP_USER"),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD"),
        MAIL_FROM=os.environ.get("MAIL_FROM", "no-reply@dayplanner.local"),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    from . import auth, planner, settings
    app.register_blueprint(auth.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(planner.bp)

    app.jinja_env.filters["hm"] = min_to_hm
    app.jinja_env.filters["dur"] = fmt_duration

    @app.before_request
    def load_user_and_check_csrf():
        g.user = None
        uid = session.get("user_id")
        if uid is not None:
            g.user = db.get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if request.method == "POST" and not app.config.get("TESTING_NO_CSRF"):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not sent or not secrets.compare_digest(sent, session.get("csrf_token", "")):
                abort(400, "Form expired. Go back, reload the page and try again.")

    def csrf():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return Markup('<input type="hidden" name="csrf_token" value="%s">') % session["csrf_token"]

    app.jinja_env.globals["csrf"] = csrf

    @app.route("/")
    def index():
        if g.user is None:
            return redirect(url_for("auth.login"))
        return redirect(url_for("planner.today"))

    return app


def _instance_secret(instance_path):
    path = Path(instance_path) / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip()
