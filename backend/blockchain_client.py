import os
import json
import logging
from web3 import Web3
from web3.exceptions import Web3Exception

logger = logging.getLogger(__name__)

class BlockchainClient:
    def __init__(self, rpc_url: str = None, contract_json_path: str = None):
        self.rpc_url = rpc_url or os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
        self.contract_json_path = contract_json_path or os.path.join(
            os.path.dirname(__file__), "contract_deployment.json"
        )
        self.w3 = None
        self.contract = None
        self.contract_address = None
        self.abi = None
        self.default_account = None
        self._init_connection()

    def _init_connection(self):
        """Initialize Web3 and contract instance if node is reachable."""
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={'timeout': 10}))
            if not self.w3.is_connected():
                logger.warning(f"Unable to connect to blockchain node at {self.rpc_url}")
                return

            # Default to account[0] from Hardhat node
            accounts = self.w3.eth.accounts
            if accounts:
                self.default_account = accounts[0]
                self.w3.eth.default_account = self.default_account

            if os.path.exists(self.contract_json_path):
                with open(self.contract_json_path, "r") as f:
                    data = json.load(f)
                    self.contract_address = Web3.to_checksum_address(data.get("address"))
                    self.abi = data.get("abi")
                    if self.contract_address and self.abi:
                        self.contract = self.w3.eth.contract(
                            address=self.contract_address,
                            abi=self.abi
                        )
                        logger.info(f"Connected to contract at {self.contract_address}")
            else:
                logger.warning(f"Contract deployment file not found at {self.contract_json_path}")
        except Exception as e:
            logger.error(f"Error initializing blockchain client: {e}")

    def is_connected(self) -> bool:
        """Check if connected to local blockchain RPC and contract is loaded."""
        try:
            if self.w3 and self.w3.is_connected():
                return self.contract is not None
        except Exception:
            pass
        return False

    def get_status_info(self) -> dict:
        """Return connectivity details for UI diagnostic banners and badges."""
        connected = False
        block_number = None
        accounts_count = 0
        error_msg = None

        try:
            if not self.w3:
                self._init_connection()
            if self.w3 and self.w3.is_connected():
                connected = True
                block_number = self.w3.eth.block_number
                accounts_count = len(self.w3.eth.accounts)
            else:
                error_msg = f"Cannot reach Hardhat node at {self.rpc_url}. Please ensure 'npx hardhat node' is running."
        except Exception as e:
            error_msg = str(e)

        return {
            "connected": connected,
            "contract_loaded": self.contract is not None,
            "contract_address": self.contract_address,
            "rpc_url": self.rpc_url,
            "block_number": block_number,
            "accounts_count": accounts_count,
            "error_message": error_msg
        }

    def register_record(self, record_id: str, patient_id: str, document_hash: str, record_type: str) -> dict:
        """
        Invoke addMedicalRecord on the Solidity smart contract.
        Returns dict with transaction details.
        """
        if not self.is_connected():
            raise RuntimeError(
                "Blockchain network is currently unavailable. Please start the Hardhat local node."
            )

        try:
            tx_hash = self.contract.functions.addMedicalRecord(
                record_id,
                patient_id,
                document_hash,
                record_type
            ).transact({'from': self.default_account})

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

            tx_hex = Web3.to_hex(receipt.transactionHash)
            return {
                "success": receipt.status == 1,
                "tx_hash": tx_hex,
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed,
                "from": receipt["from"],
                "to": receipt["to"]
            }
        except Exception as e:
            logger.error(f"Failed to register record on chain: {e}")
            raise RuntimeError(f"Blockchain record registration failed: {str(e)}")

    def grant_access(self, patient_id: str, doctor_id: str) -> dict:
        """
        Invoke grantAccess on the Solidity smart contract.
        """
        if not self.is_connected():
            raise RuntimeError("Blockchain network is currently unavailable.")

        try:
            tx_hash = self.contract.functions.grantAccess(
                patient_id,
                doctor_id
            ).transact({'from': self.default_account})

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

            return {
                "success": receipt.status == 1,
                "tx_hash": Web3.to_hex(receipt.transactionHash),
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed
            }
        except Exception as e:
            logger.error(f"Failed to grant access on chain: {e}")
            raise RuntimeError(f"Blockchain access grant failed: {str(e)}")

    def revoke_access(self, patient_id: str, doctor_id: str) -> dict:
        """
        Invoke revokeAccess on the Solidity smart contract.
        """
        if not self.is_connected():
            raise RuntimeError("Blockchain network is currently unavailable.")

        try:
            tx_hash = self.contract.functions.revokeAccess(
                patient_id,
                doctor_id
            ).transact({'from': self.default_account})

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

            return {
                "success": receipt.status == 1,
                "tx_hash": Web3.to_hex(receipt.transactionHash),
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed
            }
        except Exception as e:
            logger.error(f"Failed to revoke access on chain: {e}")
            raise RuntimeError(f"Blockchain access revocation failed: {str(e)}")

    def has_access(self, patient_id: str, doctor_id: str) -> bool:
        """
        Read doctor authorization state directly from the smart contract.
        """
        if not self.is_connected():
            logger.warning("Blockchain unavailable; falling back to DB permissions")
            return False

        try:
            return self.contract.functions.hasAccess(patient_id, doctor_id).call()
        except Exception as e:
            logger.error(f"Error querying hasAccess on blockchain: {e}")
            return False

    def verify_record(self, record_id: str, candidate_hash: str) -> dict:
        """
        Verify candidate hash against registered hash on blockchain.
        """
        if not self.is_connected():
            raise RuntimeError("Blockchain is unavailable for verification.")

        try:
            on_chain_record = self.contract.functions.getRecord(record_id).call()
            # Returns (recordId, patientId, documentHash, recordType, timestamp, addedBy)
            stored_hash = on_chain_record[2]
            is_valid = (candidate_hash.lower() == stored_hash.lower())

            return {
                "is_valid": is_valid,
                "stored_hash": stored_hash,
                "candidate_hash": candidate_hash,
                "patient_id": on_chain_record[1],
                "record_type": on_chain_record[3],
                "timestamp": on_chain_record[4],
                "added_by": on_chain_record[5]
            }
        except Exception as e:
            logger.error(f"Error verifying record on blockchain: {e}")
            raise RuntimeError(f"Blockchain verification failed: {str(e)}")

    def get_record(self, record_id: str) -> dict:
        """Retrieve record details stored in contract."""
        if not self.is_connected():
            return None
        try:
            r = self.contract.functions.getRecord(record_id).call()
            return {
                "record_id": r[0],
                "patient_id": r[1],
                "document_hash": r[2],
                "record_type": r[3],
                "timestamp": r[4],
                "added_by": r[5]
            }
        except Exception:
            return None

# Singleton client instance
blockchain_client = BlockchainClient()
