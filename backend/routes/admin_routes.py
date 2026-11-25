from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from auth import login_required, role_required, get_current_user
from database.db import execute_query, log_audit
from blockchain_client import blockchain_client

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
    current_user = get_current_user()

    total_patients = execute_query(
        "SELECT COUNT(*) as count FROM users WHERE role = 'patient'",
        fetchone=True
    )["count"]

    total_doctors = execute_query(
        "SELECT COUNT(*) as count FROM users WHERE role = 'doctor'",
        fetchone=True
    )["count"]

    total_records = execute_query(
        "SELECT COUNT(*) as count FROM medical_records",
        fetchone=True
    )["count"]

    total_transactions = execute_query(
        "SELECT COUNT(*) as count FROM blockchain_transactions",
        fetchone=True
    )["count"]

    stats = {
        "total_patients": total_patients,
        "total_doctors": total_doctors,
        "total_records": total_records,
        "total_transactions": total_transactions
    }

    # Category counts for Chart.js
    category_rows = execute_query(
        "SELECT category, COUNT(*) as count FROM medical_records GROUP BY category",
        fetchall=True
    )
    category_counts = {row["category"]: row["count"] for row in category_rows}

    # Recent audit logs
    recent_logs = execute_query(
        "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 6",
        fetchall=True
    )

    # Recent blockchain transactions
    recent_txs = execute_query(
        "SELECT * FROM blockchain_transactions ORDER BY created_at DESC LIMIT 6",
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "admin/dashboard.html",
        current_user=current_user,
        stats=stats,
        category_counts=category_counts,
        recent_logs=recent_logs,
        recent_txs=recent_txs,
        chain_status=chain_status,
        active_page="dashboard"
    )

@admin_bp.route("/users")
@login_required
@role_required("admin")
def users():
    current_user = get_current_user()
    role_filter = request.args.get("role")

    if role_filter:
        users_list = execute_query(
            "SELECT * FROM users WHERE role = %s ORDER BY created_at DESC",
            (role_filter,),
            fetchall=True
        )
    else:
        users_list = execute_query(
            "SELECT * FROM users ORDER BY created_at DESC",
            fetchall=True
        )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "admin/users.html",
        current_user=current_user,
        users=users_list,
        role_filter=role_filter,
        chain_status=chain_status,
        active_page="users"
    )

@admin_bp.route("/users/<user_id>/toggle-status", methods=["POST"])
@login_required
@role_required("admin")
def toggle_user_status(user_id):
    admin_id = session.get("user_id")

    user = execute_query(
        "SELECT * FROM users WHERE user_id = %s",
        (user_id,),
        fetchone=True
    )
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin.users"))

    if user["role"] == "admin":
        flash("Cannot deactivate system administrator account.", "danger")
        return redirect(url_for("admin.users"))

    new_status = not user.get("is_active", True)
    execute_query(
        "UPDATE users SET is_active = %s WHERE user_id = %s",
        (new_status, user_id),
        commit=True
    )

    status_str = "activated" if new_status else "deactivated"
    log_audit(admin_id, "admin", "USER_STATUS_CHANGE", f"Admin {status_str} account {user_id}", request.remote_addr)
    flash(f"Account for {user['full_name']} has been {status_str}.", "info")
    return redirect(url_for("admin.users"))

@admin_bp.route("/records")
@login_required
@role_required("admin")
def records():
    current_user = get_current_user()

    records_list = execute_query(
        """
        SELECT mr.*, u.full_name as patient_name
        FROM medical_records mr
        JOIN users u ON mr.patient_id = u.user_id
        ORDER BY mr.created_at DESC
        """,
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "admin/records.html",
        current_user=current_user,
        records=records_list,
        chain_status=chain_status,
        active_page="records"
    )

@admin_bp.route("/blockchain")
@login_required
@role_required("admin")
def blockchain():
    current_user = get_current_user()

    transactions = execute_query(
        "SELECT * FROM blockchain_transactions ORDER BY created_at DESC",
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "admin/blockchain.html",
        current_user=current_user,
        transactions=transactions,
        chain_status=chain_status,
        active_page="blockchain"
    )

@admin_bp.route("/audit-logs")
@login_required
@role_required("admin")
def audit_logs():
    current_user = get_current_user()

    logs = execute_query(
        "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 100",
        fetchall=True
    )

    chain_status = blockchain_client.get_status_info()

    return render_template(
        "admin/audit_logs.html",
        current_user=current_user,
        logs=logs,
        chain_status=chain_status,
        active_page="audit"
    )
