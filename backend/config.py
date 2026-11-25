import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Flask Security
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
    PERMANENT_SESSION_LIFETIME = timedelta(hours=3)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # AES-256-GCM Master Key (32 bytes = 64 hex characters)
    AES_SECRET_KEY = os.getenv("AES_SECRET_KEY", "7a94b593efd9b3d2b271d18408f90c4c43bc204f7626960d70b02bcda772183e")

    # MySQL Configuration
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "medical_record_blockchain")
    DB_SOCKET = os.getenv("DB_SOCKET", "/tmp/medichain_mysql.sock")

    # Blockchain Configuration
    BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
    CONTRACT_DEPLOYMENT_PATH = os.path.join(BACKEND_DIR, "contract_deployment.json")

    # Document Upload Configuration
    UPLOAD_FOLDER = os.path.join(BACKEND_DIR, "uploads", "encrypted")
    TEMP_FOLDER = os.path.join(BACKEND_DIR, "uploads", "temp")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file upload
    ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}

    # Admin Credentials for Seeding
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@medichain.com")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@12345")
