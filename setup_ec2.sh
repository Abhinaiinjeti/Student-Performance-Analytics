#!/bin/bash
# EduPulse Analytics - AWS EC2 Automated Deployment Script (Ubuntu)
set -e

echo "======================================================="
echo "  Setting up EduPulse Analytics on AWS EC2 Server"
echo "======================================================="

# 1. Update system packages and install prerequisites
echo "[1/4] Detecting operating system & installing dependencies..."

if command -v apt-get &> /dev/null; then
    echo "Detected Ubuntu / Debian (apt)"
    sudo apt update -y
    sudo apt install -y python3 python3-pip python3-venv git default-jre
elif command -v dnf &> /dev/null; then
    echo "Detected Amazon Linux / Fedora (dnf)"
    sudo dnf update -y
    sudo dnf install -y python3 python3-pip git java-17-amazon-corretto
elif command -v yum &> /dev/null; then
    echo "Detected Amazon Linux / CentOS (yum)"
    sudo yum update -y
    sudo yum install -y python3 python3-pip git java-17-amazon-corretto
else
    echo "Unknown package manager. Please ensure python3, git, and java are installed."
fi

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
