-- MediChain MySQL Database Schema
-- Database: medical_record_blockchain

CREATE DATABASE IF NOT EXISTS medical_record_blockchain CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE medical_record_blockchain;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('patient', 'doctor', 'admin') NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(30) DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_email (email),
    INDEX idx_role (role)
) ENGINE=InnoDB;

-- 2. Patient Profiles
CREATE TABLE IF NOT EXISTS patient_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    patient_id VARCHAR(50) UNIQUE NOT NULL,
    date_of_birth DATE DEFAULT NULL,
    gender VARCHAR(20) DEFAULT NULL,
    blood_group VARCHAR(10) DEFAULT NULL,
    emergency_contact VARCHAR(50) DEFAULT NULL,
    allergies TEXT DEFAULT NULL,
    address TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_patient_id (patient_id)
) ENGINE=InnoDB;

-- 3. Doctor Profiles
CREATE TABLE IF NOT EXISTS doctor_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    doctor_id VARCHAR(50) UNIQUE NOT NULL,
    specialization VARCHAR(100) NOT NULL,
    license_number VARCHAR(100) NOT NULL,
    hospital VARCHAR(150) NOT NULL,
    years_experience INT DEFAULT 0,
    bio TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_doctor_id (doctor_id)
) ENGINE=InnoDB;

-- 4. Medical Records
CREATE TABLE IF NOT EXISTS medical_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    record_id VARCHAR(50) UNIQUE NOT NULL,
    patient_id VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    encrypted_filename VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    encryption_iv VARCHAR(64) NOT NULL,
    encryption_tag VARCHAR(64) NOT NULL,
    blockchain_tx_hash VARCHAR(80) DEFAULT NULL,
    block_number BIGINT DEFAULT NULL,
    description TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_rec_patient (patient_id),
    INDEX idx_rec_hash (file_hash),
    INDEX idx_rec_id (record_id)
) ENGINE=InnoDB;

-- 5. Access Requests
CREATE TABLE IF NOT EXISTS access_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    request_id VARCHAR(50) UNIQUE NOT NULL,
    patient_id VARCHAR(50) NOT NULL,
    doctor_id VARCHAR(50) NOT NULL,
    purpose TEXT NOT NULL,
    status ENUM('pending', 'approved', 'rejected', 'revoked') DEFAULT 'pending',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP NULL DEFAULT NULL,
    INDEX idx_req_patient (patient_id),
    INDEX idx_req_doctor (doctor_id),
    INDEX idx_req_status (status)
) ENGINE=InnoDB;

-- 6. Doctor Permissions
CREATE TABLE IF NOT EXISTS doctor_permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    doctor_id VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP NULL DEFAULT NULL,
    blockchain_tx_hash VARCHAR(80) DEFAULT NULL,
    UNIQUE KEY unique_patient_doctor (patient_id, doctor_id),
    INDEX idx_perm_active (is_active)
) ENGINE=InnoDB;

-- 7. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) DEFAULT NULL,
    user_role VARCHAR(20) DEFAULT NULL,
    action VARCHAR(100) NOT NULL,
    details TEXT DEFAULT NULL,
    ip_address VARCHAR(50) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_action (action),
    INDEX idx_audit_user (user_id),
    INDEX idx_audit_time (created_at)
) ENGINE=InnoDB;

-- 8. Blockchain Transactions
CREATE TABLE IF NOT EXISTS blockchain_transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tx_hash VARCHAR(80) UNIQUE NOT NULL,
    block_number BIGINT DEFAULT NULL,
    from_address VARCHAR(60) DEFAULT NULL,
    to_address VARCHAR(60) DEFAULT NULL,
    contract_function VARCHAR(100) NOT NULL,
    record_id VARCHAR(50) DEFAULT NULL,
    patient_id VARCHAR(50) DEFAULT NULL,
    doctor_id VARCHAR(50) DEFAULT NULL,
    status VARCHAR(20) DEFAULT 'success',
    gas_used BIGINT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_tx_hash (tx_hash),
    INDEX idx_tx_record (record_id)
) ENGINE=InnoDB;
