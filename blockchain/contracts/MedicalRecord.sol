// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title MedicalRecord
 * @dev MediChain Smart Contract for tamper-proof medical record hash registry
 * and patient-controlled doctor access management.
 * Designed for college B.Tech Information Science mini-project.
 */
contract MedicalRecord {
    address public owner;

    struct Record {
        string recordId;
        string patientId;
        string documentHash; // SHA-256 hex string
        string recordType;   // Category (e.g. Blood Test, X-Ray)
        uint256 timestamp;
        address addedBy;
        bool exists;
    }

    // Mapping from recordId -> Record
    mapping(string => Record) private records;

    // List of all record IDs for audit/enumeration
    string[] private recordIds;

    // Mapping from patientId => mapping(doctorId => bool)
    mapping(string => mapping(string => bool)) private doctorPermissions;

    // Mapping from patientId => array of record IDs
    mapping(string => string[]) private patientRecords;

    // Events (no private patient health details exposed)
    event RecordAdded(
        string indexed recordId,
        string indexed patientId,
        string documentHash,
        string recordType,
        uint256 timestamp
    );

    event AccessGranted(
        string indexed patientId,
        string indexed doctorId,
        uint256 timestamp
    );

    event AccessRevoked(
        string indexed patientId,
        string indexed doctorId,
        uint256 timestamp
    );

    event RecordVerified(
        string indexed recordId,
        bool isValid,
        uint256 timestamp
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Only contract owner can execute this");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @dev Register a new medical record hash on the blockchain.
     * Records the SHA-256 digest, record ID, patient ID and category.
     */
    function addMedicalRecord(
        string memory _recordId,
        string memory _patientId,
        string memory _documentHash,
        string memory _recordType
    ) external returns (bool) {
        require(bytes(_recordId).length > 0, "Record ID cannot be empty");
        require(bytes(_patientId).length > 0, "Patient ID cannot be empty");
        require(bytes(_documentHash).length > 0, "Document hash cannot be empty");
        require(!records[_recordId].exists, "Record ID already exists on blockchain");

        Record memory newRecord = Record({
            recordId: _recordId,
            patientId: _patientId,
            documentHash: _documentHash,
            recordType: _recordType,
            timestamp: block.timestamp,
            addedBy: msg.sender,
            exists: true
        });

        records[_recordId] = newRecord;
        recordIds.push(_recordId);
        patientRecords[_patientId].push(_recordId);

        emit RecordAdded(_recordId, _patientId, _documentHash, _recordType, block.timestamp);
        return true;
    }

    /**
     * @dev Grant doctor access to a patient's medical records.
     */
    function grantAccess(string memory _patientId, string memory _doctorId) external returns (bool) {
        require(bytes(_patientId).length > 0, "Patient ID cannot be empty");
        require(bytes(_doctorId).length > 0, "Doctor ID cannot be empty");

        doctorPermissions[_patientId][_doctorId] = true;

        emit AccessGranted(_patientId, _doctorId, block.timestamp);
        return true;
    }

    /**
     * @dev Revoke doctor access to a patient's medical records.
     */
    function revokeAccess(string memory _patientId, string memory _doctorId) external returns (bool) {
        require(bytes(_patientId).length > 0, "Patient ID cannot be empty");
        require(bytes(_doctorId).length > 0, "Doctor ID cannot be empty");

        doctorPermissions[_patientId][_doctorId] = false;

        emit AccessRevoked(_patientId, _doctorId, block.timestamp);
        return true;
    }

    /**
     * @dev Check if a doctor has authorized access to a patient's records.
     */
    function hasAccess(string memory _patientId, string memory _doctorId) external view returns (bool) {
        return doctorPermissions[_patientId][_doctorId];
    }

    /**
     * @dev Verify if a candidate document SHA-256 hash matches the blockchain registered hash.
     */
    function verifyRecord(
        string memory _recordId,
        string memory _candidateHash
    ) external returns (bool isValid, string memory storedHash) {
        require(records[_recordId].exists, "Record not found on blockchain");
        storedHash = records[_recordId].documentHash;
        isValid = (keccak256(bytes(_candidateHash)) == keccak256(bytes(storedHash)));

        emit RecordVerified(_recordId, isValid, block.timestamp);
        return (isValid, storedHash);
    }

    /**
     * @dev Retrieve record metadata and registered hash by recordId.
     */
    function getRecord(string memory _recordId) external view returns (
        string memory recordId,
        string memory patientId,
        string memory documentHash,
        string memory recordType,
        uint256 timestamp,
        address addedBy
    ) {
        require(records[_recordId].exists, "Record does not exist");
        Record memory r = records[_recordId];
        return (
            r.recordId,
            r.patientId,
            r.documentHash,
            r.recordType,
            r.timestamp,
            r.addedBy
        );
    }

    /**
     * @dev Get total number of registered records on blockchain.
     */
    function getRecordCount() external view returns (uint256) {
        return recordIds.length;
    }

    /**
     * @dev Get record ID by index.
     */
    function getRecordIdByIndex(uint256 _index) external view returns (string memory) {
        require(_index < recordIds.length, "Index out of bounds");
        return recordIds[_index];
    }

    /**
     * @dev Get all record IDs for a specific patient.
     */
    function getPatientRecordIds(string memory _patientId) external view returns (string[] memory) {
        return patientRecords[_patientId];
    }
}
