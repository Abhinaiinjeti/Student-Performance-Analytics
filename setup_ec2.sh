#!/bin/bash
# EduPulse Analytics - AWS EC2 Automated Deployment Script (Ubuntu)
set -e

echo "======================================================="
echo "  Setting up EduPulse Analytics on AWS EC2 Server"
echo "======================================================="

# 1. Update system packages
echo "[1/5] Updating system packages..."
sudo apt update -y

# 2. Install Python3, venv, git, and Java Runtime (for PySpark)
echo "[2/5] Installing Python, venv, git, and Java Runtime (JRE)..."
sudo apt install -y python3 python3-pip python3-venv git default-jre

# 3. Create virtual environment
echo "[3/5] Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 4. Install dependencies
echo "[4/5] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Initialize directories and launch
echo "[5/5] Initializing storage and launching EduPulse Analytics..."
python3 -c "from config.settings import get_config; get_config().storage.ensure_directories()"

echo ""
echo "======================================================="
echo "  Setup Complete! Server running on http://0.0.0.0:5000"
echo "======================================================="
echo ""
python3 app.py
