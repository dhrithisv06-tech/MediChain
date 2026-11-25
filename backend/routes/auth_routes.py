from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash, generate_password_hash
from database.db import execute_query, log_audit
from auth import generate_patient_id, generate_doctor_id

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        role = session.get("role")
        if role == "patient":
            return redirect(url_for("patient.dashboard"))
        elif role == "doctor":
            return redirect(url_for("doctor.dashboard"))
        elif role == "admin":
            return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("auth/login.html")

        user = execute_query(
            "SELECT * FROM users WHERE email = %s LIMIT 1",
            (email,),
            fetchone=True
        )

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password. Please try again.", "danger")
            log_audit("ANONYMOUS", "guest", "FAILED_LOGIN", f"Failed attempt for email: {email}", request.remote_addr)
            return render_template("auth/login.html")

        if not user.get("is_active", True):
            flash("Your account has been deactivated by the administrator.", "danger")
            return render_template("auth/login.html")

        # Set session
        session.clear()
        session["user_id"] = user["user_id"]
        session["role"] = user["role"]
        session["full_name"] = user["full_name"]
        session["email"] = user["email"]
        session.permanent = True

        log_audit(user["user_id"], user["role"], "USER_LOGIN", "Successful login", request.remote_addr)
        flash(f"Welcome back, {user['full_name']}! 🌸", "success")

        # Redirect according to role
        if user["role"] == "patient":
            return redirect(url_for("patient.dashboard"))
        elif user["role"] == "doctor":
            return redirect(url_for("doctor.dashboard"))
        elif user["role"] == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("main.index"))

    return render_template("auth/login.html")

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("main.index"))

    if request.method == "POST":
        role = request.form.get("role", "patient").lower()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        if not full_name or not email or not password:
            flash("All required fields must be filled out.", "danger")
            return render_template("auth/register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("auth/register.html")

        if role not in ["patient", "doctor"]:
            flash("Invalid registration role.", "danger")
            return render_template("auth/register.html")

        # Check existing email
        existing_user = execute_query(
            "SELECT id FROM users WHERE email = %s",
            (email,),
            fetchone=True
        )
        if existing_user:
            flash("An account with this email address already exists.", "danger")
            return render_template("auth/register.html")

        password_hash = generate_password_hash(password)

        if role == "patient":
            assigned_id = generate_patient_id()
            blood_group = request.form.get("blood_group", "O+")
            dob = request.form.get("date_of_birth") or None
            gender = request.form.get("gender", "Other")
            emergency_contact = request.form.get("emergency_contact", "").strip()
            allergies = request.form.get("allergies", "").strip()

            # Insert into users
            execute_query(
                """
                INSERT INTO users (user_id, email, password_hash, role, full_name, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (assigned_id, email, password_hash, "patient", full_name, phone),
                commit=True
            )

            # Insert into patient_profiles
            execute_query(
                """
                INSERT INTO patient_profiles (user_id, patient_id, date_of_birth, gender, blood_group, emergency_contact, allergies)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (assigned_id, assigned_id, dob, gender, blood_group, emergency_contact, allergies),
                commit=True
            )

        elif role == "doctor":
            assigned_id = generate_doctor_id()
            specialization = request.form.get("specialization", "General Medicine").strip()
            license_number = request.form.get("license_number", "").strip() or f"LIC-{assigned_id[-4:]}"
            hospital = request.form.get("hospital", "General Healthcare Center").strip()
            years_experience = int(request.form.get("years_experience", 0) or 0)

            # Insert into users
            execute_query(
                """
                INSERT INTO users (user_id, email, password_hash, role, full_name, phone)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (assigned_id, email, password_hash, "doctor", full_name, phone),
                commit=True
            )

            # Insert into doctor_profiles
            execute_query(
                """
                INSERT INTO doctor_profiles (user_id, doctor_id, specialization, license_number, hospital, years_experience)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (assigned_id, assigned_id, specialization, license_number, hospital, years_experience),
                commit=True
            )

        log_audit(assigned_id, role, "USER_REGISTER", f"Registered new {role}: {assigned_id}", request.remote_addr)

        # Auto login
        session.clear()
        session["user_id"] = assigned_id
        session["role"] = role
        session["full_name"] = full_name
        session["email"] = email
        session.permanent = True

        flash(f"Account successfully created! Welcome to MediChain. Your ID is {assigned_id}.", "success")
        if role == "patient":
            return redirect(url_for("patient.dashboard"))
        else:
            return redirect(url_for("doctor.dashboard"))

    return render_template("auth/register.html")

@auth_bp.route("/logout")
def logout():
    user_id = session.get("user_id")
    role = session.get("role")
    if user_id:
        log_audit(user_id, role, "USER_LOGOUT", "User logged out", request.remote_addr)
    session.clear()
    flash("You have been signed out safely. Have a wonderful day! 🌸", "info")
    return redirect(url_for("main.index"))
