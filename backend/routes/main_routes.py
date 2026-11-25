import os
from flask import Blueprint, render_template, jsonify, request, current_app
from blockchain_client import blockchain_client
from database.db import execute_query, log_audit
from crypto_utils import decrypt_document, compute_sha256

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def index():
    """Landing Page."""
    chain_status = blockchain_client.get_status_info()
    return render_template("landing.html", chain_status=chain_status)

@main_bp.route("/api/chain-status")
def api_chain_status():
    """API endpoint to get real-time blockchain node connectivity and block height."""
    status = blockchain_client.get_status_info()
    return jsonify(status)

@main_bp.route("/api/verify-record/<record_id>")
def api_verify_record(record_id):
    """
    Real-time verification endpoint:
    1. Fetches on-chain registered SHA-256 hash from Solidity smart contract.
    2. Reads encrypted file from disk, decrypts with AES-256-GCM.
    3. If ?tamper=true is passed, flips bytes to demonstrate tamper detection live.
    4. Computes SHA-256 of decrypted file and compares against blockchain hash.
    """
    test_tamper = request.args.get("tamper", "false").lower() == "true"

    # Query record from DB
    rec = execute_query(
        "SELECT * FROM medical_records WHERE record_id = %s",
        (record_id,),
        fetchone=True
    )
    if not rec:
        return jsonify({
            "success": False,
            "message": f"Medical record {record_id} not found in database."
        }), 404

    # Query smart contract on Ethereum
    on_chain_record = blockchain_client.get_record(record_id)
    if not on_chain_record:
        # Fallback to DB stored hash if local chain node is temporarily stopped
        blockchain_hash = rec["file_hash"]
        tx_hash = rec["blockchain_tx_hash"]
        block_num = rec["block_number"]
    else:
        blockchain_hash = on_chain_record["document_hash"]
        tx_hash = rec["blockchain_tx_hash"]
        block_num = rec["block_number"]

    # Read encrypted file
    enc_path = os.path.join(current_app.config["UPLOAD_FOLDER"], rec["encrypted_filename"])
    if not os.path.exists(enc_path):
        return jsonify({
            "success": False,
            "message": "Encrypted document file is missing from secure storage."
        }), 404

    with open(enc_path, "rb") as f:
        encrypted_bytes = f.read()

    try:
        decrypted_bytes = decrypt_document(
            encrypted_bytes,
            rec["encryption_iv"],
            rec["encryption_tag"]
        )

        # If tamper simulation requested, modify bytes
        if test_tamper:
            decrypted_bytes = decrypted_bytes + b" [ALTERED_TAMPERED_CONTENT]"

        calculated_hash = compute_sha256(decrypted_bytes)
        is_valid = (calculated_hash.lower() == blockchain_hash.lower())

        log_audit(
            user_id="GUEST_OR_USER",
            role="verifier",
            action="TAMPER_DETECTED" if (not is_valid and test_tamper) else ("INTEGRITY_VERIFIED" if is_valid else "VERIFICATION_FAILED"),
            details=f"Verification for {record_id}: Match={is_valid}. TamperSim={test_tamper}"
        )

        return jsonify({
            "success": True,
            "record_id": record_id,
            "category": rec["category"],
            "title": rec["title"],
            "blockchain_hash": blockchain_hash,
            "calculated_hash": calculated_hash,
            "is_valid": is_valid,
            "blockchain_tx_hash": tx_hash,
            "block_number": block_num,
            "is_tamper_simulation": test_tamper
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Decryption/verification error: {str(e)}"
        }), 500
