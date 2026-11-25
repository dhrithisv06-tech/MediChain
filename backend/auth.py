from functools import wraps
import random
import string
from flask import session, redirect, url_for, flash, request, abort
from database.db import execute_query

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please sign in to access this page.", "warning")
                return redirect(url_for("auth.login", next=request.url))
            
            user_role = session.get("role")
            if user_role not in roles:
                flash(f"Access denied. This section is reserved for {', '.join(roles)}s.", "danger")
                if user_role == "patient":
                    return redirect(url_for("patient.dashboard"))
                elif user_role == "doctor":
                    return redirect(url_for("doctor.dashboard"))
                elif user_role == "admin":
                    return redirect(url_for("admin.dashboard"))
                return redirect(url_for("main.index"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_current_user():
    """Retrieve current user dict from session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return execute_query(
        "SELECT id, user_id, email, role, full_name, phone, is_active FROM users WHERE user_id = %s",
        (user_id,),
        fetchone=True
    )

def generate_patient_id() -> str:
    """Generate a unique patient identifier, e.g. PAT-2026-4821."""
    while True:
        num = random.randint(1000, 9999)
        candidate = f"PAT-2026-{num}"
        exists = execute_query(
            "SELECT id FROM users WHERE user_id = %s",
            (candidate,),
            fetchone=True
        )
        if not exists:
            return candidate

def generate_doctor_id() -> str:
    """Generate a unique doctor identifier, e.g. DOC-2026-5192."""
    while True:
        num = random.randint(1000, 9999)
        candidate = f"DOC-2026-{num}"
        exists = execute_query(
            "SELECT id FROM users WHERE user_id = %s",
            (candidate,),
            fetchone=True
        )
        if not exists:
            return candidate

def generate_record_id() -> str:
    """Generate a unique medical record identifier, e.g. REC-2026-A8F2."""
    chars = string.ascii_uppercase + string.digits
    while True:
        suffix = "".join(random.choices(chars, k=5))
        candidate = f"REC-2026-{suffix}"
        exists = execute_query(
            "SELECT id FROM medical_records WHERE record_id = %s",
            (candidate,),
            fetchone=True
        )
        if not exists:
            return candidate

def generate_request_id() -> str:
    """Generate a unique access request identifier, e.g. REQ-2026-B3E9."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=5))
    return f"REQ-2026-{suffix}"
