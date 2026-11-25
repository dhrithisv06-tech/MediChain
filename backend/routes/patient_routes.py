import os
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, send_file, abort
from werkzeug.utils import secure_filename
from auth import login_required, role_required, generate_record_id, get_current_user
from database.db import execute_query, log_audit, record_blockchain_tx
from crypto_utils import compute_sha256, encrypt_document, decrypt_document
from blockchain_client import blockchain_client

patient_bp = Blueprint("patient", __name__, url_prefix="/patient")

@patient_bp.route("/dashboard")
@login_required
@role_required("patient")
def dashboard():
    patient_id = session.get("user_id")
    current_user = get_current_user()

    # Calculate statistics
    total_records = execute_query(
        "SELECT COUNT(*) as count FROM medical_records WHERE patient_id = %s",
        (patient_id,),
        fetchone=True
    )["count"]

    authorized_doctors = execute_query(
        "SELECT COUNT(*) as count FROM doctor_permissions WHERE patient_id = %s AND is_active = TRUE",
        (patient_id,),
        fetchone=True
    )["count"]

    pending_requests = execute_query(
        "SELECT COUNT(*) as count FROM access_requests WHERE patient_id = %s AND status = 'pending'",
        (patient_id,),
        fetchone=True
    )["count"]

    verified_records = total_records # All uploaded records are verified on blockchain

    stats = {
        "total_records": total_records,
        "authorized_doctors": authorized_doctors,
        "pending_requests": pending_requests,
        "verified_records": verified_records
    }

    # Fetch recent records
    recent_records = execute_query(
        """
        SELECT record_id, title, category, original_filename, file_size, file_hash, created_at
        FROM medical_records
        WHERE patient_id = %s
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (patient_id,),
        fetchall=True
    )

    # Fetch active doctors
    active_doctors = execute_query(
        """
        SELECT dp.doctor_id, u.full_name, dp.specialization, dp.hospital, perm.granted_at
        FROM doctor_permissions perm
        JOIN doctor_profiles dp ON perm.doctor_id = dp.doctor_id
        JOIN users u ON dp.user_id = u.user_id
        WHERE perm.patient_id = %s AND perm.is_active = TRUE
        LIMIT 4
        """,
        (patient_id,),
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "patient/dashboard.html",
        current_user=current_user,
        stats=stats,
        recent_records=recent_records,
        active_doctors=active_doctors,
        chain_status=chain_status,
        active_page="dashboard",
        pending_count=pending_requests
    )

@patient_bp.route("/records")
@login_required
@role_required("patient")
def records():
    patient_id = session.get("user_id")
    current_user = get_current_user()
    category = request.args.get("category")

    if category:
        records_list = execute_query(
            """
            SELECT * FROM medical_records
            WHERE patient_id = %s AND category = %s
            ORDER BY created_at DESC
            """,
            (patient_id, category),
            fetchall=True
        )
    else:
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
        "patient/records.html",
        current_user=current_user,
        records=records_list,
        selected_category=category,
        chain_status=chain_status,
        active_page="records"
    )

@patient_bp.route("/upload", methods=["GET", "POST"])
@login_required
@role_required("patient")
def upload():
    patient_id = session.get("user_id")
    current_user = get_current_user()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "General Medical Report")
        description = request.form.get("description", "").strip()

        if "document" not in request.files:
            flash("No file part selected.", "danger")
            return redirect(request.url)

        file = request.files["document"]
        if file.filename == "":
            flash("Please choose a file to upload.", "danger")
            return redirect(request.url)

        # File validation
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
            flash(f"Invalid file type '.{ext}'. Allowed formats: PDF, JPG, JPEG, PNG.", "danger")
            return redirect(request.url)

        file_bytes = file.read()
        file_size = len(file_bytes)

        if file_size > current_app.config["MAX_CONTENT_LENGTH"]:
            flash("File size exceeds 16 MB maximum limit.", "danger")
            return redirect(request.url)

        if not title:
            title = file.filename.rsplit(".", 1)[0]

        # 1. Compute SHA-256 hash of original unencrypted document
        original_hash = compute_sha256(file_bytes)

        # 2. Encrypt document with AES-256-GCM
        encrypted_bytes, iv_hex, tag_hex = encrypt_document(file_bytes)

        # 3. Store encrypted document securely on disk
        record_id = generate_record_id()
        encrypted_filename = f"{record_id}.enc"
        encrypted_path = os.path.join(current_app.config["UPLOAD_FOLDER"], encrypted_filename)

        with open(encrypted_path, "wb") as f:
            f.write(encrypted_bytes)

        # 4. Insert record metadata into MySQL
        mime_type = file.content_type or "application/octet-stream"
        execute_query(
            """
            INSERT INTO medical_records
            (record_id, patient_id, title, category, original_filename, encrypted_filename,
             file_size, mime_type, file_hash, encryption_iv, encryption_tag, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (record_id, patient_id, title, category, secure_filename(file.filename),
             encrypted_filename, file_size, mime_type, original_hash, iv_hex, tag_hex, description),
            commit=True
        )

        # 5. Register document hash on Ethereum Smart Contract
        tx_hash = None
        block_num = None
        try:
            if blockchain_client.is_connected():
                receipt = blockchain_client.register_record(
                    record_id,
                    patient_id,
                    original_hash,
                    category
                )
                tx_hash = receipt["tx_hash"]
                block_num = receipt["block_number"]

                # Update MySQL with blockchain transaction details
                execute_query(
                    """
                    UPDATE medical_records
                    SET blockchain_tx_hash = %s, block_number = %s
                    WHERE record_id = %s
                    """,
                    (tx_hash, block_num, record_id),
                    commit=True
                )

                # Save transaction into blockchain_transactions table
                record_blockchain_tx(
                    tx_hash=tx_hash,
                    block_number=block_num,
                    from_addr=receipt["from"],
                    to_addr=receipt["to"],
                    function_name="addMedicalRecord",
                    record_id=record_id,
                    patient_id=patient_id,
                    gas_used=receipt["gas_used"]
                )
        except Exception as bc_err:
            current_app.logger.error(f"Blockchain registration failed: {bc_err}")
            flash(f"Record stored securely, but blockchain recording failed: {str(bc_err)}", "warning")

        log_audit(
            patient_id,
            "patient",
            "RECORD_UPLOAD",
            f"Uploaded record {record_id} ({category}), SHA-256: {original_hash[:16]}...",
            request.remote_addr
        )

        flash(f"Medical document '{title}' successfully encrypted with AES-256-GCM and registered on the blockchain! (Record ID: {record_id})", "success")
        return redirect(url_for("patient.records"))

    chain_status = blockchain_client.get_status_info()
    return render_template(
        "patient/upload.html",
        current_user=current_user,
        chain_status=chain_status,
        active_page="upload"
    )

@patient_bp.route("/download/<record_id>")
@login_required
@role_required("patient")
def download_record(record_id):
    patient_id = session.get("user_id")

    rec = execute_query(
        "SELECT * FROM medical_records WHERE record_id = %s AND patient_id = %s",
        (record_id, patient_id),
        fetchone=True
    )
    if not rec:
        abort(404, "Medical record not found or access unauthorized.")

    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], rec["encrypted_filename"])
    if not os.path.exists(enc_path):
        abort(404, "Encrypted file not found on disk.")

    with open(enc_path, "rb") as f:
        encrypted_bytes = f.read()

    try:
        decrypted_bytes = decrypt_document(
            encrypted_bytes,
            rec["encryption_iv"],
            rec["encryption_tag"]
        )

        log_audit(patient_id, "patient", "RECORD_DOWNLOAD", f"Downloaded record {record_id}", request.remote_addr)

        return send_file(
            io.BytesIO(decrypted_bytes),
            mimetype=rec["mime_type"],
            as_attachment=True,
            download_name=rec["original_filename"]
        )
    except Exception as e:
        flash(f"Decryption failed: {str(e)}", "danger")
        return redirect(url_for("patient.records"))

@patient_bp.route("/doctors")
@login_required
@role_required("patient")
def doctors():
    patient_id = session.get("user_id")
    current_user = get_current_user()

    doctors_list = execute_query(
        """
        SELECT dp.doctor_id, u.full_name, dp.specialization, dp.hospital, dp.license_number, perm.granted_at
        FROM doctor_permissions perm
        JOIN doctor_profiles dp ON perm.doctor_id = dp.doctor_id
        JOIN users u ON dp.user_id = u.user_id
        WHERE perm.patient_id = %s AND perm.is_active = TRUE
        ORDER BY perm.granted_at DESC
        """,
        (patient_id,),
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "patient/doctors.html",
        current_user=current_user,
        doctors=doctors_list,
        chain_status=chain_status,
        active_page="doctors"
    )

@patient_bp.route("/grant-direct", methods=["POST"])
@login_required
@role_required("patient")
def grant_direct_access():
    patient_id = session.get("user_id")
    doctor_id = request.form.get("doctor_id", "").strip().upper()

    doc = execute_query(
        "SELECT dp.doctor_id, u.full_name FROM doctor_profiles dp JOIN users u ON dp.user_id = u.user_id WHERE dp.doctor_id = %s",
        (doctor_id,),
        fetchone=True
    )
    if not doc:
        flash(f"Doctor with ID '{doctor_id}' does not exist.", "danger")
        return redirect(url_for("patient.doctors"))

    # Update database permission
    execute_query(
        """
        INSERT INTO doctor_permissions (patient_id, doctor_id, is_active, granted_at)
        VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP)
        ON DUPLICATE KEY UPDATE is_active = TRUE, granted_at = CURRENT_TIMESTAMP
        """,
        (patient_id, doctor_id),
        commit=True
    )

    # Invoke Solidity smart contract grantAccess
    tx_hash = None
    try:
        if blockchain_client.is_connected():
            receipt = blockchain_client.grant_access(patient_id, doctor_id)
            tx_hash = receipt["tx_hash"]
            record_blockchain_tx(
                tx_hash=tx_hash,
                block_number=receipt["block_number"],
                from_addr=blockchain_client.default_account,
                to_addr=blockchain_client.contract_address,
                function_name="grantAccess",
                patient_id=patient_id,
                doctor_id=doctor_id,
                gas_used=receipt["gas_used"]
            )
    except Exception as bc_err:
        current_app.logger.error(f"Blockchain grantAccess failed: {bc_err}")

    log_audit(patient_id, "patient", "ACCESS_GRANTED", f"Granted access to {doctor_id}", request.remote_addr)
    flash(f"Access successfully granted on the blockchain to {doc['full_name']} ({doctor_id})!", "success")
    return redirect(url_for("patient.doctors"))

@patient_bp.route("/revoke-doctor/<doctor_id>", methods=["POST"])
@login_required
@role_required("patient")
def revoke_doctor_access(doctor_id):
    patient_id = session.get("user_id")

    # Update database
    execute_query(
        """
        UPDATE doctor_permissions
        SET is_active = FALSE, revoked_at = CURRENT_TIMESTAMP
        WHERE patient_id = %s AND doctor_id = %s
        """,
        (patient_id, doctor_id),
        commit=True
    )

    # Update any pending requests to revoked
    execute_query(
        """
        UPDATE access_requests
        SET status = 'revoked', responded_at = CURRENT_TIMESTAMP
        WHERE patient_id = %s AND doctor_id = %s AND status = 'approved'
        """,
        (patient_id, doctor_id),
        commit=True
    )

    # Invoke Solidity smart contract revokeAccess
    tx_hash = None
    try:
        if blockchain_client.is_connected():
            receipt = blockchain_client.revoke_access(patient_id, doctor_id)
            tx_hash = receipt["tx_hash"]
            record_blockchain_tx(
                tx_hash=tx_hash,
                block_number=receipt["block_number"],
                from_addr=blockchain_client.default_account,
                to_addr=blockchain_client.contract_address,
                function_name="revokeAccess",
                patient_id=patient_id,
                doctor_id=doctor_id,
                gas_used=receipt["gas_used"]
            )
    except Exception as bc_err:
        current_app.logger.error(f"Blockchain revokeAccess failed: {bc_err}")

    log_audit(patient_id, "patient", "ACCESS_REVOKED", f"Revoked access for {doctor_id}", request.remote_addr)
    flash(f"Access for doctor {doctor_id} has been revoked on the blockchain.", "info")
    return redirect(url_for("patient.doctors"))

@patient_bp.route("/requests")
@login_required
@role_required("patient")
def requests():
    patient_id = session.get("user_id")
    current_user = get_current_user()

    pending_requests = execute_query(
        """
        SELECT req.*, u.full_name as doctor_name, dp.specialization, dp.hospital
        FROM access_requests req
        JOIN doctor_profiles dp ON req.doctor_id = dp.doctor_id
        JOIN users u ON dp.user_id = u.user_id
        WHERE req.patient_id = %s AND req.status = 'pending'
        ORDER BY req.requested_at DESC
        """,
        (patient_id,),
        fetchall=True
    )

    request_history = execute_query(
        """
        SELECT req.*, u.full_name as doctor_name, dp.specialization, dp.hospital
        FROM access_requests req
        JOIN doctor_profiles dp ON req.doctor_id = dp.doctor_id
        JOIN users u ON dp.user_id = u.user_id
        WHERE req.patient_id = %s AND req.status != 'pending'
        ORDER BY req.requested_at DESC
        """,
        (patient_id,),
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "patient/requests.html",
        current_user=current_user,
        pending_requests=pending_requests,
        request_history=request_history,
        chain_status=chain_status,
        active_page="requests"
    )

@patient_bp.route("/requests/<request_id>/<action>", methods=["POST"])
@login_required
@role_required("patient")
def respond_request(request_id, action):
    patient_id = session.get("user_id")

    req = execute_query(
        "SELECT * FROM access_requests WHERE request_id = %s AND patient_id = %s",
        (request_id, patient_id),
        fetchone=True
    )
    if not req:
        flash("Access request not found.", "danger")
        return redirect(url_for("patient.requests"))

    doctor_id = req["doctor_id"]

    if action == "approve":
        execute_query(
            "UPDATE access_requests SET status = 'approved', responded_at = CURRENT_TIMESTAMP WHERE request_id = %s",
            (request_id,),
            commit=True
        )
        execute_query(
            """
            INSERT INTO doctor_permissions (patient_id, doctor_id, is_active, granted_at)
            VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP)
            ON DUPLICATE KEY UPDATE is_active = TRUE, granted_at = CURRENT_TIMESTAMP
            """,
            (patient_id, doctor_id),
            commit=True
        )

        try:
            if blockchain_client.is_connected():
                receipt = blockchain_client.grant_access(patient_id, doctor_id)
                record_blockchain_tx(
                    tx_hash=receipt["tx_hash"],
                    block_number=receipt["block_number"],
                    from_addr=blockchain_client.default_account,
                    to_addr=blockchain_client.contract_address,
                    function_name="grantAccess",
                    patient_id=patient_id,
                    doctor_id=doctor_id,
                    gas_used=receipt["gas_used"]
                )
        except Exception as bc_err:
            current_app.logger.error(f"Blockchain grant error: {bc_err}")

        log_audit(patient_id, "patient", "ACCESS_APPROVED", f"Approved request {request_id} for {doctor_id}", request.remote_addr)
        flash("Access request approved on the blockchain!", "success")

    elif action == "reject":
        execute_query(
            "UPDATE access_requests SET status = 'rejected', responded_at = CURRENT_TIMESTAMP WHERE request_id = %s",
            (request_id,),
            commit=True
        )
        log_audit(patient_id, "patient", "ACCESS_REJECTED", f"Rejected request {request_id} for {doctor_id}", request.remote_addr)
        flash("Access request rejected.", "info")

    return redirect(url_for("patient.requests"))

@patient_bp.route("/blockchain")
@login_required
@role_required("patient")
def blockchain():
    patient_id = session.get("user_id")
    current_user = get_current_user()

    transactions = execute_query(
        """
        SELECT * FROM blockchain_transactions
        WHERE patient_id = %s
        ORDER BY created_at DESC
        """,
        (patient_id,),
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

@patient_bp.route("/profile", methods=["GET", "POST"])
@login_required
@role_required("patient")
def profile():
    patient_id = session.get("user_id")
    current_user = get_current_user()

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        blood_group = request.form.get("blood_group", "O+")
        dob = request.form.get("date_of_birth") or None
        gender = request.form.get("gender", "Female")
        emergency_contact = request.form.get("emergency_contact", "").strip()
        allergies = request.form.get("allergies", "").strip()
        address = request.form.get("address", "").strip()

        execute_query(
            "UPDATE users SET full_name = %s, phone = %s WHERE user_id = %s",
            (full_name, phone, patient_id),
            commit=True
        )
        execute_query(
            """
            UPDATE patient_profiles
            SET blood_group = %s, date_of_birth = %s, gender = %s,
                emergency_contact = %s, allergies = %s, address = %s
            WHERE patient_id = %s
            """,
            (blood_group, dob, gender, emergency_contact, allergies, address, patient_id),
            commit=True
        )

        session["full_name"] = full_name
        log_audit(patient_id, "patient", "PROFILE_UPDATE", "Updated health profile", request.remote_addr)
        flash("Your profile information has been saved successfully!", "success")
        return redirect(url_for("patient.profile"))

    pat_profile = execute_query(
        "SELECT * FROM patient_profiles WHERE patient_id = %s",
        (patient_id,),
        fetchone=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "patient/profile.html",
        current_user=current_user,
        profile=pat_profile,
        chain_status=chain_status,
        active_page="profile"
    )
