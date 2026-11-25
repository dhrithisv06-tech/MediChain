import os
from flask import Flask, render_template
from config import Config
from database.db import init_db
from blockchain_client import blockchain_client
from auth import get_current_user

def create_app(config_class=Config):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)

    # Ensure upload directories exist
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["TEMP_FOLDER"], exist_ok=True)

    # Initialize database
    try:
        init_db()
    except Exception as e:
        app.logger.error(f"Failed to initialize database: {e}")

    # Register blueprints
    from routes.main_routes import main_bp
    from routes.auth_routes import auth_bp
    from routes.patient_routes import patient_bp
    from routes.doctor_routes import doctor_bp
    from routes.admin_routes import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(admin_bp)

    # Context processors for global template variables
    @app.context_processor
    def inject_global_vars():
        user = get_current_user()
        chain_status = blockchain_client.get_status_info()
        return {
            "current_user": user,
            "chain_status": chain_status
        }

    # Error Handlers
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template(
            "base.html",
            layout_override=True,
            error_code=403,
            error_title="Access Forbidden",
            error_message="You do not have authorization to view this medical resource."
        ), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template(
            "base.html",
            layout_override=True,
            error_code=404,
            error_title="Page Not Found",
            error_message="The requested medical resource or page could not be located."
        ), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template(
            "base.html",
            layout_override=True,
            error_code=500,
            error_title="System Error",
            error_message="An unexpected server error occurred. Please contact the administrator."
        ), 500

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
