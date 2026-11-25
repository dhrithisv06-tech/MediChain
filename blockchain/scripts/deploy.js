import { ethers } from "ethers";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function main() {
  const rpcUrl = "http://127.0.0.1:8545";
  const provider = new ethers.JsonRpcProvider(rpcUrl);
  
  // Get deployer (account #0 from local Hardhat node)
  const signer = await provider.getSigner(0);
  const deployerAddress = await signer.getAddress();
  console.log("Deploying MediChain MedicalRecord contract with account:", deployerAddress);

  const balance = await provider.getBalance(deployerAddress);
  console.log("Account balance:", ethers.formatEther(balance), "ETH");

  const artifactPath = path.join(
    __dirname,
    "..",
    "artifacts",
    "contracts",
    "MedicalRecord.sol",
    "MedicalRecord.json"
  );

  if (!fs.existsSync(artifactPath)) {
    throw new Error(`Artifact not found at ${artifactPath}. Please run 'npx hardhat compile' first.`);
  }

  const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));
  const factory = new ethers.ContractFactory(artifact.abi, artifact.bytecode, signer);
  
  console.log("Sending deployment transaction...");
  const contract = await factory.deploy();
  await contract.waitForDeployment();

  const contractAddress = await contract.getAddress();
  console.log("==================================================");
  console.log("✅ MediChain MedicalRecord Contract Deployed Successfully!");
  console.log("   Contract Address:", contractAddress);
  console.log("   Deployer Address:", deployerAddress);
  console.log("   RPC URL:         ", rpcUrl);
  console.log("==================================================");

  const deploymentInfo = {
    address: contractAddress,
    deployer: deployerAddress,
    network: "localhost",
    rpcUrl: rpcUrl,
    chainId: 31337,
    deployedAt: new Date().toISOString(),
    abi: artifact.abi
  };

  const outputPath = path.join(__dirname, "..", "deployment.json");
  fs.writeFileSync(outputPath, JSON.stringify(deploymentInfo, null, 2));
  console.log("Saved deployment info to:", outputPath);

  // Copy to backend
  const backendConfigDir = path.join(__dirname, "..", "..", "backend");
  if (!fs.existsSync(backendConfigDir)) {
    fs.mkdirSync(backendConfigDir, { recursive: true });
  }
  const backendOutputPath = path.join(backendConfigDir, "contract_deployment.json");
  fs.writeFileSync(backendOutputPath, JSON.stringify(deploymentInfo, null, 2));
  console.log("Saved deployment info to backend at:", backendOutputPath);
}

main().catch((err) => {
  console.error("Deployment failed:", err);
  process.exit(1);
});
