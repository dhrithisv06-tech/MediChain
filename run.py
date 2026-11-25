#!/usr/bin/env python3
"""
MediChain – Medical Record Management System
Main Application Entry Point
"""
import os
import sys

# Ensure backend directory is in python module search path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    print("==================================================================")
    print("🌸 MediChain Medical Record Management System Starting...")
    print(f"👉 Web Application URL: http://127.0.0.1:{port}")
    print("👉 Theme: Cute Pastel Hospital / Healthcare Aesthetic")
    print("👉 Blockchain: Ethereum Localnet via Hardhat 3 (http://127.0.0.1:8545)")
    print("👉 Database: MySQL / MariaDB (medical_record_blockchain)")
    print("==================================================================")
    app.run(host="0.0.0.0", port=port, debug=True)
