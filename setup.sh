#!/bin/bash

# Setup script for AskMama Telegram Bot

echo "=================================="
echo "AskMama Bot - Setup Script"
echo "=================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Dependencies installed successfully!"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file and add your credentials:"
    echo "   - TELEGRAM_BOT_TOKEN"
    echo "   - GEMINI_API_KEY"
    echo "   - GOOGLE_SHEET_NAME"
    echo ""
fi

# Check if credentials.json exists
if [ ! -f credentials.json ]; then
    echo "⚠️  credentials.json not found!"
    echo "   Please download your Google service account key"
    echo "   and save it as credentials.json in this directory."
    echo ""
fi

echo "=================================="
echo "Setup Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials"
echo "2. Add credentials.json file"
echo "3. Run: python test_setup.py (to verify setup)"
echo "4. Run: python run.py (to start the bot)"
echo ""
