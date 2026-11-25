import { expect } from "chai";
import { ethers } from "hardhat";

describe("MediChain MedicalRecord Contract", function () {
  let medicalRecord;
  let owner;
  let doctor;
  let patient;

  beforeEach(async function () {
    [owner, doctor, patient] = await ethers.getSigners();
    const MedicalRecordFactory = await ethers.getContractFactory("MedicalRecord");
    medicalRecord = await MedicalRecordFactory.deploy();
    await medicalRecord.waitForDeployment();
  });

  it("should set the deployer as owner", async function () {
    expect(await medicalRecord.owner()).to.equal(owner.address);
  });

  it("should successfully add a medical record hash", async function () {
    const tx = await medicalRecord.addMedicalRecord(
      "REC-001",
      "PAT-101",
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "Blood Test"
    );
    await tx.wait();

    const record = await medicalRecord.getRecord("REC-001");
    expect(record.recordId).to.equal("REC-001");
    expect(record.patientId).to.equal("PAT-101");
    expect(record.documentHash).to.equal("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    expect(record.recordType).to.equal("Blood Test");
    expect(record.addedBy).to.equal(owner.address);
  });

  it("should revert if duplicate record ID is registered", async function () {
    await medicalRecord.addMedicalRecord(
      "REC-DUP",
      "PAT-101",
      "hash123",
      "MRI Scan"
    );

    await expect(
      medicalRecord.addMedicalRecord(
        "REC-DUP",
        "PAT-102",
        "hash456",
        "X-Ray"
      )
    ).to.be.revertedWith("Record ID already exists on blockchain");
  });

  it("should manage patient-controlled doctor access correctly", async function () {
    // Initially false
    expect(await medicalRecord.hasAccess("PAT-101", "DOC-201")).to.be.false;

    // Grant access
    await medicalRecord.grantAccess("PAT-101", "DOC-201");
    expect(await medicalRecord.hasAccess("PAT-101", "DOC-201")).to.be.true;

    // Revoke access
    await medicalRecord.revokeAccess("PAT-101", "DOC-201");
    expect(await medicalRecord.hasAccess("PAT-101", "DOC-201")).to.be.false;
  });

  it("should verify matching document hashes and detect tampered hashes", async function () {
    const originalHash = "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0";
    const tamperedHash = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff";

    await medicalRecord.addMedicalRecord("REC-VERIFY", "PAT-101", originalHash, "Prescription");

    // Test valid verification
    const validResult = await medicalRecord.verifyRecord.staticCall("REC-VERIFY", originalHash);
    expect(validResult[0]).to.be.true;
    expect(validResult[1]).to.equal(originalHash);

    // Test tampered verification
    const tamperedResult = await medicalRecord.verifyRecord.staticCall("REC-VERIFY", tamperedHash);
    expect(tamperedResult[0]).to.be.false;
    expect(tamperedResult[1]).to.equal(originalHash);
  });
});
