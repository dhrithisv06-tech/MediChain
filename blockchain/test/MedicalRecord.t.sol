// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../contracts/MedicalRecord.sol";

contract MedicalRecordTest {
    MedicalRecord recordContract;

    function setUp() public {
        recordContract = new MedicalRecord();
    }

    function testOwnerIsDeployer() public view {
        require(recordContract.owner() == address(this), "Owner should be deployer");
    }

    function testAddRecord() public {
        bool success = recordContract.addMedicalRecord(
            "REC-001",
            "PAT-101",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "Blood Test"
        );
        require(success, "Adding record failed");

        (
            string memory recId,
            string memory patId,
            string memory docHash,
            string memory recType,
            ,
        ) = recordContract.getRecord("REC-001");

        require(keccak256(bytes(recId)) == keccak256(bytes("REC-001")), "Record ID mismatch");
        require(keccak256(bytes(patId)) == keccak256(bytes("PAT-101")), "Patient ID mismatch");
        require(keccak256(bytes(recType)) == keccak256(bytes("Blood Test")), "Record type mismatch");
        require(bytes(docHash).length > 0, "Document hash empty");
    }

    function testDoctorAccessWorkflow() public {
        require(!recordContract.hasAccess("PAT-101", "DOC-201"), "Should be unauthorized initially");

        // Grant access
        recordContract.grantAccess("PAT-101", "DOC-201");
        require(recordContract.hasAccess("PAT-101", "DOC-201"), "Access should be granted");

        // Revoke access
        recordContract.revokeAccess("PAT-101", "DOC-201");
        require(!recordContract.hasAccess("PAT-101", "DOC-201"), "Access should be revoked");
    }

    function testIntegrityVerificationAndTamperDetection() public {
        string memory originalHash = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918";
        string memory tamperedHash = "badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbad1";

        recordContract.addMedicalRecord("REC-VERIFY", "PAT-101", originalHash, "Prescription");

        // Valid hash verification
        (bool isValid, string memory storedHash) = recordContract.verifyRecord("REC-VERIFY", originalHash);
        require(isValid, "Original hash should verify as valid");
        require(keccak256(bytes(storedHash)) == keccak256(bytes(originalHash)), "Stored hash mismatch");

        // Tampered hash detection
        (bool isTamperedValid, ) = recordContract.verifyRecord("REC-VERIFY", tamperedHash);
        require(!isTamperedValid, "Tampered hash must fail verification");
    }
}
