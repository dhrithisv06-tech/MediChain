import os
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, send_file, abort
from auth import login_required, role_required, get_current_user, generate_request_id
from database.db import execute_query, log_audit
from crypto_utils import decrypt_document
from blockchain_client import blockchain_client

doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")

def verify_doctor_authorization(patient_id: str, doctor_id: str) -> bool:
    """
    Dual-layer authorization check:
    1. Checks SQL database table `doctor_permissions`
    2. Checks Solidity smart contract `hasAccess(patient_id, doctor_id)`
    """
    db_perm = execute_query(
        "SELECT id FROM doctor_permissions WHERE patient_id = %s AND doctor_id = %s AND is_active = TRUE",
        (patient_id, doctor_id),
        fetchone=True
    )
    if not db_perm:
        return False

    # Check on-chain if connected
    if blockchain_client.is_connected():
        chain_perm = blockchain_client.has_access(patient_id, doctor_id)
        return chain_perm

    return True

@doctor_bp.route("/dashboard")
@login_required
@role_required("doctor")
def dashboard():
    doctor_id = session.get("user_id")
    current_user = get_current_user()

    # Calculate statistics
    authorized_patients_count = execute_query(
        """
        SELECT COUNT(DISTINCT patient_id) as count 
        FROM doctor_permissions 
        WHERE doctor_id = %s AND is_active = TRUE
        """,
        (doctor_id,),
        fetchone=True
    )["count"]

    pending_requests_count = execute_query(
        "SELECT COUNT(*) as count FROM access_requests WHERE doctor_id = %s AND status = 'pending'",
        (doctor_id,),
        fetchone=True
    )["count"]

    accessible_records_count = execute_query(
        """
        SELECT COUNT(mr.id) as count
        FROM medical_records mr
        JOIN doctor_permissions perm ON mr.patient_id = perm.patient_id
        WHERE perm.doctor_id = %s AND perm.is_active = TRUE
        """,
        (doctor_id,),
        fetchone=True
    )["count"]

    verified_records_count = accessible_records_count

    stats = {
        "authorized_patients": authorized_patients_count,
        "pending_requests": pending_requests_count,
        "accessible_records": accessible_records_count,
        "verified_records": verified_records_count
    }

    # Fetch authorized patients
    authorized_patients = execute_query(
        """
        SELECT pp.patient_id, u.full_name, pp.blood_group, perm.granted_at
        FROM doctor_permissions perm
        JOIN patient_profiles pp ON perm.patient_id = pp.patient_id
        JOIN users u ON pp.user_id = u.user_id
        WHERE perm.doctor_id = %s AND perm.is_active = TRUE
        ORDER BY perm.granted_at DESC
        LIMIT 5
        """,
        (doctor_id,),
        fetchall=True
    )

    doc_profile = execute_query(
        "SELECT * FROM doctor_profiles WHERE doctor_id = %s",
        (doctor_id,),
        fetchone=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "doctor/dashboard.html",
        current_user=current_user,
        doctor_profile=doc_profile,
        stats=stats,
        authorized_patients=authorized_patients,
        chain_status=chain_status,
        active_page="dashboard"
    )

@doctor_bp.route("/search")
@login_required
@role_required("doctor")
def search_patient():
    doctor_id = session.get("user_id")
    current_user = get_current_user()
    query_id = request.args.get("patient_id", "").strip().upper()

    searched = False
    patient = None
    is_authorized = False
    has_pending = False

    if query_id:
        searched = True
        patient = execute_query(
            """
            SELECT u.full_name, pp.*
            FROM patient_profiles pp
            JOIN users u ON pp.user_id = u.user_id
            WHERE pp.patient_id = %s
            """,
            (query_id,),
            fetchone=True
        )

        if patient:
            is_authorized = verify_doctor_authorization(query_id, doctor_id)
            pending_check = execute_query(
                "SELECT id FROM access_requests WHERE patient_id = %s AND doctor_id = %s AND status = 'pending'",
                (query_id, doctor_id),
                fetchone=True
            )
            has_pending = bool(pending_check)

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "doctor/search.html",
        current_user=current_user,
        query_id=query_id,
        searched=searched,
        patient=patient,
        is_authorized=is_authorized,
        has_pending=has_pending,
        chain_status=chain_status,
        active_page="search"
    )

@doctor_bp.route("/request-access", methods=["POST"])
@login_required
@role_required("doctor")
def send_access_request():
    doctor_id = session.get("user_id")
    patient_id = request.form.get("patient_id", "").strip().upper()
    purpose = request.form.get("purpose", "").strip()

    if not patient_id or not purpose:
        flash("Patient ID and clinical purpose are required.", "danger")
        return redirect(url_for("doctor.search_patient", patient_id=patient_id))

    # Check if patient exists
    patient = execute_query(
        "SELECT id FROM patient_profiles WHERE patient_id = %s",
        (patient_id,),
        fetchone=True
    )
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for("doctor.search_patient"))

    # Check if request already pending
    existing = execute_query(
        "SELECT id FROM access_requests WHERE patient_id = %s AND doctor_id = %s AND status = 'pending'",
        (patient_id, doctor_id),
        fetchone=True
    )
    if existing:
        flash("An access request for this patient is already pending.", "warning")
        return redirect(url_for("doctor.search_patient", patient_id=patient_id))

    request_id = generate_request_id()
    execute_query(
        """
        INSERT INTO access_requests (request_id, patient_id, doctor_id, purpose, status)
        VALUES (%s, %s, %s, %s, 'pending')
        """,
        (request_id, patient_id, doctor_id, purpose),
        commit=True
    )

    log_audit(doctor_id, "doctor", "ACCESS_REQUESTED", f"Requested access for {patient_id}. Purpose: {purpose}", request.remote_addr)
    flash(f"Access request successfully sent to patient {patient_id}!", "success")
    return redirect(url_for("doctor.search_patient", patient_id=patient_id))

@doctor_bp.route("/patients")
@login_required
@role_required("doctor")
def authorized_patients():
    doctor_id = session.get("user_id")
    current_user = get_current_user()

    patients_list = execute_query(
        """
        SELECT pp.*, u.full_name, u.phone, perm.granted_at
        FROM doctor_permissions perm
        JOIN patient_profiles pp ON perm.patient_id = pp.patient_id
        JOIN users u ON pp.user_id = u.user_id
        WHERE perm.doctor_id = %s AND perm.is_active = TRUE
        ORDER BY perm.granted_at DESC
        """,
        (doctor_id,),
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "doctor/patients.html",
        current_user=current_user,
        patients=patients_list,
        chain_status=chain_status,
        active_page="patients"
    )

@doctor_bp.route("/patient/<patient_id>/records")
@login_required
@role_required("doctor")
def view_patient_records(patient_id):
    doctor_id = session.get("user_id")
    current_user = get_current_user()

    # STRICT BACKEND AUTHORIZATION CHECK
    if not verify_doctor_authorization(patient_id, doctor_id):
        log_audit(doctor_id, "doctor", "UNAUTHORIZED_ACCESS_ATTEMPT", f"Attempted unauthorized access to {patient_id} records", request.remote_addr)
        flash("Access Denied: You do not have active smart contract authorization to view this patient's records.", "danger")
        return redirect(url_for("doctor.search_patient", patient_id=patient_id))

    patient = execute_query(
        """
        SELECT pp.*, u.full_name, u.phone, u.email
        FROM patient_profiles pp
        JOIN users u ON pp.user_id = u.user_id
        WHERE pp.patient_id = %s
        """,
        (patient_id,),
        fetchone=True
    )
    if not patient:
        abort(404, "Patient not found.")

    records_list = execute_query(
        """
        SELECT * FROM medical_records
        WHERE patient_id = %s
        ORDER BY created_at DESC
        """,
        (patient_id,),
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "doctor/patient_records.html",
        current_user=current_user,
        patient=patient,
        records=records_list,
        chain_status=chain_status,
        active_page="patients"
    )

@doctor_bp.route("/download/<record_id>")
@login_required
@role_required("doctor")
def download_record(record_id):
    doctor_id = session.get("user_id")

    rec = execute_query(
        "SELECT * FROM medical_records WHERE record_id = %s",
        (record_id,),
        fetchone=True
    )
    if not rec:
        abort(404, "Medical record not found.")

    patient_id = rec["patient_id"]

    # STRICT BACKEND AUTHORIZATION CHECK
    if not verify_doctor_authorization(patient_id, doctor_id):
        log_audit(doctor_id, "doctor", "UNAUTHORIZED_DOWNLOAD_ATTEMPT", f"Doctor attempted to download {record_id} without authorization", request.remote_addr)
        abort(403, "Access Denied: Doctor not authorized by patient on blockchain.")

    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], rec["encrypted_filename"])
    if not os.path.exists(enc_path):
        abort(404, "Encrypted file missing from disk.")

    with open(enc_path, "rb") as f:
        encrypted_bytes = f.read()

    try:
        decrypted_bytes = decrypt_document(
            encrypted_bytes,
            rec["encryption_iv"],
            rec["encryption_tag"]
        )

        log_audit(doctor_id, "doctor", "RECORD_DOWNLOAD", f"Doctor downloaded authorized record {record_id} (Patient {patient_id})", request.remote_addr)

        return send_file(
            io.BytesIO(decrypted_bytes),
            mimetype=rec["mime_type"],
            as_attachment=True,
            download_name=rec["original_filename"]
        )
    except Exception as e:
        flash(f"Decryption failed: {str(e)}", "danger")
        return redirect(url_for("doctor.view_patient_records", patient_id=patient_id))

@doctor_bp.route("/requests")
@login_required
@role_required("doctor")
def access_requests():
    doctor_id = session.get("user_id")
    current_user = get_current_user()

    requests_list = execute_query(
        """
        SELECT req.*, u.full_name as patient_name
        FROM access_requests req
        JOIN patient_profiles pp ON req.patient_id = pp.patient_id
        JOIN users u ON pp.user_id = u.user_id
        WHERE req.doctor_id = %s
        ORDER BY req.requested_at DESC
        """,
        (doctor_id,),
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "doctor/requests.html",
        current_user=current_user,
        requests=requests_list,
        chain_status=chain_status,
        active_page="requests"
    )

@doctor_bp.route("/verification")
@login_required
@role_required("doctor")
def verification_tool():
    current_user = get_current_user()
    preset_record_id = request.args.get("record_id", "")
    chain_status = blockchain_client.get_status_info()

    return render_template(
        "doctor/verification.html",
        current_user=current_user,
        preset_record_id=preset_record_id,
        chain_status=chain_status,
        active_page="verification"
    )

@doctor_bp.route("/blockchain")
@login_required
@role_required("doctor")
def blockchain_history():
    doctor_id = session.get("user_id")
    current_user = get_current_user()

    transactions = execute_query(
        """
        SELECT * FROM blockchain_transactions
        WHERE doctor_id = %s
        ORDER BY created_at DESC
        """,
        (doctor_id,),
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "patient/blockchain.html",
        current_user=current_user,
        transactions=transactions,
        chain_status=chain_status,
        active_page="blockchain"
    )

@doctor_bp.route("/profile", methods=["GET", "POST"])
@login_required
@role_required("doctor")
def profile():
    doctor_id = session.get("user_id")
    current_user = get_current_user()

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        specialization = request.form.get("specialization", "").strip()
        license_number = request.form.get("license_number", "").strip()
        hospital = request.form.get("hospital", "").strip()
        years_experience = int(request.form.get("years_experience", 0) or 0)
        bio = request.form.get("bio", "").strip()

        execute_query(
            "UPDATE users SET full_name = %s, phone = %s WHERE user_id = %s",
            (full_name, phone, doctor_id),
            commit=True
        )
        execute_query(
            """
            UPDATE doctor_profiles
            SET specialization = %s, license_number = %s, hospital = %s,
                years_experience = %s, bio = %s
            WHERE doctor_id = %s
            """,
            (specialization, license_number, hospital, years_experience, bio, doctor_id),
            commit=True
        )

        session["full_name"] = full_name
        log_audit(doctor_id, "doctor", "PROFILE_UPDATE", "Updated doctor profile", request.remote_addr)
        flash("Doctor profile updated successfully!", "success")
        return redirect(url_for("doctor.profile"))

    doc_profile = execute_query(
        "SELECT * FROM doctor_profiles WHERE doctor_id = %s",
        (doctor_id,),
        fetchone=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "doctor/profile.html",
        current_user=current_user,
        doctor_profile=doc_profile,
        chain_status=chain_status,
        active_page="profile"
    )
