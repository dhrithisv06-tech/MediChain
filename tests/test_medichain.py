import os
import sys
import io
import uuid
import pytest
from unittest.mock import patch

# Add backend directory to sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import create_app
from crypto_utils import compute_sha256, encrypt_document, decrypt_document, verify_document_integrity
from blockchain_client import BlockchainClient, blockchain_client
from database.db import execute_query

@pytest.fixture
def app():
    os.environ["SECRET_KEY"] = "test-secret-key-12345"
    app = create_app()
    app.config["TESTING"] = True
    yield app

@pytest.fixture
def client(app):
    return app.test_client()

# ==============================================================================
# TEST 1: Patient Registration
# ==============================================================================
def test_01_patient_registration(client):
    email = "test_patient_auto@example.com"
    # Cleanup previous test run if any
    execute_query("DELETE FROM users WHERE email = %s", (email,), commit=True)

    response = client.post("/register", data={
        "role": "patient",
        "full_name": "Test Patient",
        "email": email,
        "phone": "+1-555-010-0001",
        "password": "Password@123",
        "confirm_password": "Password@123",
        "blood_group": "A+",
        "gender": "Female",
        "emergency_contact": "Emergency Friend (+1-555-010-0002)",
        "allergies": "None"
    }, follow_redirects=True)

    assert response.status_code == 200
    user = execute_query("SELECT * FROM users WHERE email = %s", (email,), fetchone=True)
    assert user is not None
    assert user["role"] == "patient"
    assert user["user_id"].startswith("PAT-")

    profile = execute_query("SELECT * FROM patient_profiles WHERE user_id = %s", (user["user_id"],), fetchone=True)
    assert profile is not None
    assert profile["blood_group"] == "A+"

# ==============================================================================
# TEST 2: Doctor Registration
# ==============================================================================
def test_02_doctor_registration(client):
    email = "test_doctor_auto@example.com"
    execute_query("DELETE FROM users WHERE email = %s", (email,), commit=True)

    response = client.post("/register", data={
        "role": "doctor",
        "full_name": "Dr. Alan Grant",
        "email": email,
        "phone": "+1-555-020-0001",
        "password": "Password@123",
        "confirm_password": "Password@123",
        "specialization": "Paleo-Diagnostics & Oncology",
        "license_number": "LIC-TEST-9901",
        "hospital": "Central Health Institute",
        "years_experience": "10"
    }, follow_redirects=True)

    assert response.status_code == 200
    user = execute_query("SELECT * FROM users WHERE email = %s", (email,), fetchone=True)
    assert user is not None
    assert user["role"] == "doctor"
    assert user["user_id"].startswith("DOC-")

    doc_prof = execute_query("SELECT * FROM doctor_profiles WHERE doctor_id = %s", (user["user_id"],), fetchone=True)
    assert doc_prof is not None
    assert doc_prof["specialization"] == "Paleo-Diagnostics & Oncology"

# ==============================================================================
# TEST 3: Login and Logout
# ==============================================================================
def test_03_login_and_logout(client):
    # 1. Login with demo patient
    res_login = client.post("/login", data={
        "email": "emily@example.com",
        "password": "Patient@123"
    }, follow_redirects=True)
    assert res_login.status_code == 200
    assert b"Emily Rose" in res_login.data

    with client.session_transaction() as sess:
        assert sess.get("user_id") == "PAT-2026-1001"
        assert sess.get("role") == "patient"

    # 2. Logout
    res_logout = client.get("/logout", follow_redirects=True)
    assert res_logout.status_code == 200
    with client.session_transaction() as sess:
        assert "user_id" not in sess

# ==============================================================================
# TEST 4: Medical Record Upload
# ==============================================================================
def test_04_medical_record_upload(client):
    # Login as patient
    client.post("/login", data={"email": "emily@example.com", "password": "Patient@123"})

    dummy_content = b"PDF-1.4 Diagnostic Test Results: All metabolic panels normal."
    data = {
        "title": "Comprehensive Metabolic Panel 2026",
        "category": "Blood Test",
        "description": "Routine annual health screening",
        "document": (io.BytesIO(dummy_content), "metabolic_panel.pdf")
    }

    res_upload = client.post("/patient/upload", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert res_upload.status_code == 200
    assert b"Comprehensive Metabolic Panel 2026" in res_upload.data

    # Check database
    rec = execute_query(
        "SELECT * FROM medical_records WHERE title = 'Comprehensive Metabolic Panel 2026' ORDER BY id DESC LIMIT 1",
        fetchone=True
    )
    assert rec is not None
    assert rec["category"] == "Blood Test"
    assert rec["patient_id"] == "PAT-2026-1001"
    assert len(rec["file_hash"]) == 64

# ==============================================================================
# TEST 5: File Encryption (AES-256-GCM)
# ==============================================================================
def test_05_file_encryption_aes_256_gcm():
    plaintext = b"CONFIDENTIAL HEALTH RECORD: Patient has hypertension."
    encrypted, iv_hex, tag_hex = encrypt_document(plaintext)

    assert encrypted != plaintext
    assert len(bytes.fromhex(iv_hex)) == 12  # Standard 96-bit nonce
    assert len(bytes.fromhex(tag_hex)) == 16 # 128-bit authentication tag

    decrypted = decrypt_document(encrypted, iv_hex, tag_hex)
    assert decrypted == plaintext

# ==============================================================================
# TEST 6: Hash Generation (SHA-256)
# ==============================================================================
def test_06_sha256_hash_generation():
    test_data = b"MediChain Immutable Health Ledger 2026"
    hash1 = compute_sha256(test_data)
    assert len(hash1) == 64
    assert hash1.islower()

    # Determinism
    hash2 = compute_sha256(test_data)
    assert hash1 == hash2

    # Avalanche effect
    hash_modified = compute_sha256(test_data + b"!")
    assert hash1 != hash_modified

# ==============================================================================
# TEST 7: Blockchain Record Registration
# ==============================================================================
def test_07_blockchain_record_registration():
    if not blockchain_client.is_connected():
        pytest.skip("Local Hardhat node is not running for live test.")

    record_id = f"REC-CHAIN-{uuid.uuid4().hex[:6].upper()}"
    patient_id = "PAT-2026-1001"
    doc_hash = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"

    receipt = blockchain_client.register_record(
        record_id=record_id,
        patient_id=patient_id,
        document_hash=doc_hash,
        record_type="MRI Scan"
    )

    assert receipt["success"] is True
    assert receipt["tx_hash"].startswith("0x")
    assert receipt["block_number"] >= 1

    # Verify retrieval from contract
    on_chain = blockchain_client.get_record(record_id)
    assert on_chain["record_id"] == record_id
    assert on_chain["patient_id"] == patient_id
    assert on_chain["document_hash"] == doc_hash

# ==============================================================================
# TEST 8: Doctor Access Request
# ==============================================================================
def test_08_doctor_access_request(client):
    # Login as doctor
    client.post("/login", data={"email": "dr.sarah@example.com", "password": "Doctor@123"})

    # Send request for PAT-2026-1001
    res = client.post("/doctor/request-access", data={
        "patient_id": "PAT-2026-1001",
        "purpose": "Evaluating cardiac diagnostic history for medication titration"
    }, follow_redirects=True)

    assert res.status_code == 200
    req = execute_query(
        "SELECT * FROM access_requests WHERE doctor_id = 'DOC-2026-2001' AND patient_id = 'PAT-2026-1001' ORDER BY id DESC LIMIT 1",
        fetchone=True
    )
    assert req is not None
    assert req["status"] == "pending"
    assert "medication titration" in req["purpose"]

# ==============================================================================
# TEST 9: Patient Approval
# ==============================================================================
def test_09_patient_approval(client):
    # Fetch latest pending request
    req = execute_query(
        "SELECT * FROM access_requests WHERE patient_id = 'PAT-2026-1001' AND status = 'pending' ORDER BY id DESC LIMIT 1",
        fetchone=True
    )
    assert req is not None

    # Login as patient
    client.post("/login", data={"email": "emily@example.com", "password": "Patient@123"})

    # Approve request
    res = client.post(f"/patient/requests/{req['request_id']}/approve", follow_redirects=True)
    assert res.status_code == 200

    updated_req = execute_query("SELECT status FROM access_requests WHERE request_id = %s", (req["request_id"],), fetchone=True)
    assert updated_req["status"] == "approved"

    perm = execute_query(
        "SELECT is_active FROM doctor_permissions WHERE patient_id = 'PAT-2026-1001' AND doctor_id = %s",
        (req["doctor_id"],),
        fetchone=True
    )
    assert perm is not None
    assert perm["is_active"] == 1

# ==============================================================================
# TEST 10: Patient Rejection
# ==============================================================================
def test_10_patient_rejection(client):
    # Insert dummy pending request
    dummy_req_id = "REQ-TEST-REJECT-01"
    execute_query("DELETE FROM access_requests WHERE request_id = %s", (dummy_req_id,), commit=True)
    execute_query(
        """
        INSERT INTO access_requests (request_id, patient_id, doctor_id, purpose, status)
        VALUES (%s, 'PAT-2026-1001', 'DOC-2026-2001', 'Request to be rejected test', 'pending')
        """,
        (dummy_req_id,),
        commit=True
    )

    # Login as patient
    client.post("/login", data={"email": "emily@example.com", "password": "Patient@123"})

    res = client.post(f"/patient/requests/{dummy_req_id}/reject", follow_redirects=True)
    assert res.status_code == 200

    rej_req = execute_query("SELECT status FROM access_requests WHERE request_id = %s", (dummy_req_id,), fetchone=True)
    assert rej_req["status"] == "rejected"

# ==============================================================================
# TEST 11: Access Revocation
# ==============================================================================
def test_11_access_revocation(client):
    # Ensure permission exists first
    execute_query(
        """
        INSERT INTO doctor_permissions (patient_id, doctor_id, is_active)
        VALUES ('PAT-2026-1001', 'DOC-2026-2001', TRUE)
        ON DUPLICATE KEY UPDATE is_active = TRUE
        """,
        commit=True
    )

    # Login as patient
    client.post("/login", data={"email": "emily@example.com", "password": "Patient@123"})

    res = client.post("/patient/revoke-doctor/DOC-2026-2001", follow_redirects=True)
    assert res.status_code == 200

    perm = execute_query(
        "SELECT is_active FROM doctor_permissions WHERE patient_id = 'PAT-2026-1001' AND doctor_id = 'DOC-2026-2001'",
        fetchone=True
    )
    assert perm["is_active"] == 0

# ==============================================================================
# TEST 12: Unauthorized Document Access (Blocked)
# ==============================================================================
def test_12_unauthorized_document_access(client):
    # Ensure doctor has NO permission for PAT-2026-1001
    execute_query(
        "UPDATE doctor_permissions SET is_active = FALSE WHERE patient_id = 'PAT-2026-1001' AND doctor_id = 'DOC-2026-2001'",
        commit=True
    )

    # Login as doctor
    client.post("/login", data={"email": "dr.sarah@example.com", "password": "Doctor@123"})

    # Attempt to view patient records
    res = client.get("/doctor/patient/PAT-2026-1001/records", follow_redirects=True)
    assert res.status_code == 200
    assert b"Access Denied" in res.data or b"do not have active smart contract authorization" in res.data

# ==============================================================================
# TEST 13: Medical Record Integrity Verification
# ==============================================================================
def test_13_medical_record_integrity_verification(client):
    # Ensure a record exists
    rec = execute_query("SELECT record_id, file_hash FROM medical_records LIMIT 1", fetchone=True)
    assert rec is not None

    res = client.get(f"/api/verify-record/{rec['record_id']}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["is_valid"] is True
    assert data["calculated_hash"].lower() == data["blockchain_hash"].lower()

# ==============================================================================
# TEST 14: Tampered Document Detection
# ==============================================================================
def test_14_tampered_document_detection(client):
    rec = execute_query("SELECT record_id, file_hash FROM medical_records LIMIT 1", fetchone=True)
    assert rec is not None

    # Call with tamper=true simulation
    res = client.get(f"/api/verify-record/{rec['record_id']}?tamper=true")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["is_valid"] is False  # Must detect tampering!
    assert data["calculated_hash"] != data["blockchain_hash"]

# ==============================================================================
# TEST 15: Blockchain Connection Failure Handling
# ==============================================================================
def test_15_blockchain_connection_failure():
    # Instantiate client targeting non-existent port
    offline_client = BlockchainClient(rpc_url="http://127.0.0.1:9999")
    status = offline_client.get_status_info()

    assert status["connected"] is False
    assert status["contract_loaded"] is False
    assert status["error_message"] is not None

    # Ensure calling contract function gracefully raises descriptive error
    with pytest.raises(RuntimeError) as exc_info:
        offline_client.register_record("REC-FAIL", "PAT-FAIL", "hash", "X-Ray")
    assert "Blockchain network is currently unavailable" in str(exc_info.value)
