import os
import pymysql
import logging
from pymysql.cursors import DictCursor
from werkzeug.security import generate_password_hash

logger = logging.getLogger(__name__)

def get_db_connection():
    """
    Establish and return a PyMySQL connection with DictCursor.
    Tries TCP connection (127.0.0.1:3306) and falls back to unix socket if needed.
    """
    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = int(os.getenv("DB_PORT", 3306))
    db_user = os.getenv("DB_USER", "root")
    db_pass = os.getenv("DB_PASSWORD", "")
    db_name = os.getenv("DB_NAME", "medical_record_blockchain")
    db_socket = os.getenv("DB_SOCKET", "/tmp/medichain_mysql.sock")

    try:
        # First attempt: TCP connection
        conn = pymysql.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_pass,
            database=db_name,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True
        )
        return conn
    except Exception as tcp_err:
        # Second attempt: Unix socket if file exists
        if os.path.exists(db_socket):
            try:
                conn = pymysql.connect(
                    user=db_user,
                    password=db_pass,
                    database=db_name,
                    unix_socket=db_socket,
                    charset="utf8mb4",
                    cursorclass=DictCursor,
                    autocommit=True
                )
                return conn
            except Exception as sock_err:
                logger.error(f"Socket connection also failed: {sock_err}")
        
        logger.error(f"Database connection error: {tcp_err}")
        raise tcp_err

def execute_query(sql, params=None, fetchone=False, fetchall=False, commit=False):
    """
    Safely execute parameterized SQL queries to prevent SQL injection.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            if commit:
                conn.commit()
            if fetchone:
                return cursor.fetchone()
            if fetchall:
                return cursor.fetchall()
            return cursor.lastrowid or cursor.rowcount
    finally:
        conn.close()

def log_audit(user_id: str, role: str, action: str, details: str = "", ip_address: str = "127.0.0.1"):
    """Record an audit log entry for security and compliance monitoring."""
    sql = """
        INSERT INTO audit_logs (user_id, user_role, action, details, ip_address)
        VALUES (%s, %s, %s, %s, %s)
    """
    try:
        execute_query(sql, (user_id, role, action, details, ip_address), commit=True)
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")

def record_blockchain_tx(tx_hash: str, block_number: int, from_addr: str, to_addr: str,
                         function_name: str, record_id: str = None, patient_id: str = None,
                         doctor_id: str = None, gas_used: int = None):
    """Save an on-chain transaction reference to the database."""
    sql = """
        INSERT INTO blockchain_transactions 
        (tx_hash, block_number, from_address, to_address, contract_function, record_id, patient_id, doctor_id, gas_used)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE block_number=VALUES(block_number), gas_used=VALUES(gas_used)
    """
    try:
        execute_query(
            sql,
            (tx_hash, block_number, from_addr, to_addr, function_name, record_id, patient_id, doctor_id, gas_used),
            commit=True
        )
    except Exception as e:
        logger.error(f"Failed to record blockchain transaction: {e}")

def init_db():
    """
    Initialize database schema and seed default administrator and demo records.
    """
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"schema.sql not found at {schema_path}")

    # Read schema.sql
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Create tables
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Split by statements
            statements = [stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()]
            for stmt in statements:
                # Skip CREATE DATABASE / USE as connection is already bound
                if stmt.upper().startswith("CREATE DATABASE") or stmt.upper().startswith("USE"):
                    continue
                cursor.execute(stmt)
        conn.commit()
        logger.info("Database schema initialized successfully.")
    finally:
        conn.close()

    # Seed initial Admin user if not exists
    admin = execute_query(
        "SELECT id FROM users WHERE role = 'admin' LIMIT 1",
        fetchone=True
    )
    if not admin:
        admin_email = os.getenv("ADMIN_EMAIL", "admin@medichain.com")
        admin_pass = os.getenv("ADMIN_PASSWORD", "Admin@12345")
        admin_hash = generate_password_hash(admin_pass)
        
        execute_query(
            """
            INSERT INTO users (user_id, email, password_hash, role, full_name, phone)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            ("ADM-001", admin_email, admin_hash, "admin", "MediChain Chief Admin", "+1-800-MEDICHAIN"),
            commit=True
        )
        logger.info(f"Default admin seeded: {admin_email} / {admin_pass}")

    # Seed demo Patient if not exists
    demo_patient = execute_query(
        "SELECT id FROM users WHERE user_id = 'PAT-2026-1001' LIMIT 1",
        fetchone=True
    )
    if not demo_patient:
        pat_hash = generate_password_hash("Patient@123")
        execute_query(
            """
            INSERT INTO users (user_id, email, password_hash, role, full_name, phone)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            ("PAT-2026-1001", "emily@example.com", pat_hash, "patient", "Emily Rose", "+1-555-019-2834"),
            commit=True
        )
        execute_query(
            """
            INSERT INTO patient_profiles (user_id, patient_id, date_of_birth, gender, blood_group, emergency_contact, allergies, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            ("PAT-2026-1001", "PAT-2026-1001", "1998-05-14", "Female", "O+", "David Rose (+1-555-019-2835)", "Penicillin, Peanuts", "742 Evergreen Terrace, Springfield"),
            commit=True
        )
        logger.info("Demo patient seeded: emily@example.com / Patient@123 (PAT-2026-1001)")

    # Seed demo Doctor if not exists
    demo_doc = execute_query(
        "SELECT id FROM users WHERE user_id = 'DOC-2026-2001' LIMIT 1",
        fetchone=True
    )
    if not demo_doc:
        doc_hash = generate_password_hash("Doctor@123")
        execute_query(
            """
            INSERT INTO users (user_id, email, password_hash, role, full_name, phone)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            ("DOC-2026-2001", "dr.sarah@example.com", doc_hash, "doctor", "Dr. Sarah Jenkins, M.D.", "+1-555-012-9876"),
            commit=True
        )
        execute_query(
            """
            INSERT INTO doctor_profiles (user_id, doctor_id, specialization, license_number, hospital, years_experience, bio)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            ("DOC-2026-2001", "DOC-2026-2001", "Cardiology", "MD-CARDIO-88921", "St. Jude Memorial Hospital", 8, "Consultant Cardiologist specializing in preventive cardiac wellness and non-invasive diagnostics."),
            commit=True
        )
    
