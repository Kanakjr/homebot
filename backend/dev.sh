#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

echo "Activating venv and installing dependencies..."
source "$VENV_DIR/bin/activate"
pip install -q -r requirements.txt

mkdir -p data

if [ ! -f .env ] || grep -q "your-telegram-bot-token" .env; then
    echo ""
    echo "!! Fill in your actual tokens/keys in Apps/homebot/.env before running."
    echo "!! At minimum you need: TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, HA_TOKEN"
    echo ""
    exit 1
fi

echo "Starting HomeBotAI in dev mode..."
python main.py
