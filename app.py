from __future__ import annotations

from flask import Flask, redirect, url_for
from flask_login import LoginManager

from auth import auth_bp
from database import close_db, init_db
from models import get_user
from routes import main_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY="cambia-esta-clave-en-produccion",
        DATABASE="app.db",
    )

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Inicia sesión para continuar."
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        return get_user(user_id)

    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    @app.route("/")
    def index():
        return redirect(url_for("main.dashboard"))

    with app.app_context():
        init_db()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
