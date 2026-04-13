"""
app/__init__.py - Flask application factory
"""
import logging
import os

from flask import Flask
from flask_cors import CORS

from config import FLASK_DEBUG, SECRET_KEY
from datetime import timedelta


def create_app() -> Flask:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, "templates"),
        static_folder=os.path.join(project_root, "static"),
        static_url_path="/static",
    )

    # Secret key (required for session cookies)
    app.secret_key = SECRET_KEY
    app.permanent_session_lifetime = timedelta(days=7)

    # Max upload size: 20 MB (applies to /api/ai/ask file uploads)
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

    # CORS for API routes and public /v1/* API
    CORS(app, resources={
        r"/api/*": {"origins": "*"},
        r"/v1/*":  {"origins": "*"},
    })

    # Logging
    log_level = logging.DEBUG if FLASK_DEBUG else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    # ── Database init (creates tables + seeds providers) ──────────────────
    import sys
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from database import init_db
    init_db()

    # ── Blueprints ─────────────────────────────────────────────────────────
    from app.routes                   import api_bp
    from app.frontend                 import frontend_bp
    from routes.provider_routes       import provider_bp
    from routes.public_api_routes     import public_api_bp
    from routes.ai_api                import ai_api_bp
    from routes.auth_routes           import auth_bp
    from routes.logs_routes           import logs_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(logs_bp)                 # handles /login + /api/auth/*
    app.register_blueprint(api_bp,        url_prefix="/api")
    app.register_blueprint(provider_bp)             # handles /settings + /api/providers/*
    app.register_blueprint(public_api_bp)           # handles /v1/*
    app.register_blueprint(ai_api_bp)               # handles /api/ai/ask
    app.register_blueprint(frontend_bp,   url_prefix="/")

    logger.info("Routes registered:")
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        methods = ", ".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        logger.info("  %-42s [%s]", rule.rule, methods)

    return app
