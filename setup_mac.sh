#!/bin/bash

# Standardize macOS Setup for PantryPilot
echo "🚀 Starting macOS Environment Setup..."

# 1. Create virtual environment using python3
echo "📦 Creating virtual environment..."
python3 -m venv venv

# 2. Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# 3. Upgrade pip using pip3
echo "🔝 Upgrading pip..."
pip3 install --upgrade pip

# 4. Install requirements
echo "📥 Installing pinned dependencies from requirements.txt..."
pip3 install -r requirements.txt

echo "✅ Environment setup complete! Run 'source venv/bin/activate' to start developing."
