
from flask import Flask
from db import init_db
from db import close_db
from routes import bp as routes_bp

def create_app():
    app = Flask(__name__)
    app.register_blueprint(routes_bp, url_prefix="/api")

    @app.before_request
    def before_request():
        pass  # ensures DB opens per request

    @app.teardown_appcontext
    def teardown_db(exception):
        close_db()

    with app.app_context():
        init_db()

    return app
