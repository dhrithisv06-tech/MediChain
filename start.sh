#!/bin/bash
# ==============================================================================
# MediChain - Single-Script Startup & Diagnostic Utility
# Starts MySQL (MariaDB), Hardhat Ethereum node, deploys smart contract,
# and starts the Flask Web Application.
# ==============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

export PATH="/Users/deekshitha/.local/bin:$PATH"

echo "🌸 =================================================================="
echo "🌸 Starting MediChain – Medical Record Management System"
echo "🌸 =================================================================="

# 1. Check / Start MySQL
echo "🔍 Checking MySQL database..."
if /Applications/XAMPP/xamppfiles/bin/mysqladmin --socket=/tmp/medichain_mysql.sock ping >/dev/null 2>&1 || lsof -i :3306 >/dev/null 2>&1; then
    echo "✅ MySQL server is already running."
else
    echo "🚀 Starting local MariaDB instance..."
    /Applications/XAMPP/xamppfiles/sbin/mysqld --no-defaults --datadir="$PROJECT_DIR/mysql_data" --socket=/tmp/medichain_mysql.sock --port=3306 >/dev/null 2>&1 &
    sleep 3
    echo "✅ MariaDB started on port 3306."
fi

# 2. Check / Start Hardhat Local Blockchain
echo "🔍 Checking Hardhat local Ethereum blockchain node..."
if curl -s -X POST --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' -H "Content-Type: application/json" http://127.0.0.1:8545 >/dev/null 2>&1; then
    echo "✅ Hardhat blockchain node is already active on http://127.0.0.1:8545."
else
    echo "🚀 Starting Hardhat Ethereum node in background..."
    cd "$PROJECT_DIR/blockchain"
    npx hardhat node --hostname 127.0.0.1 --port 8545 > "$PROJECT_DIR/hardhat_node.log" 2>&1 &
    sleep 4
    echo "✅ Hardhat node started."

    # Deploy contract
    echo "📜 Deploying MedicalRecord.sol smart contract..."
    node scripts/deploy.js
    cd "$PROJECT_DIR"
fi

# 3. Start Flask Web Server
echo "🚀 Starting MediChain Flask application on http://127.0.0.1:5001..."
"$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/run.py"
