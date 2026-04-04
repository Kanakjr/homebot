#!/usr/bin/env bash
set -e

# Always run from the finetuning directory
cd "$(dirname "$0")"

# 1. Create venv and install dependencies if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "[SETUP] Creating a clean virtual environment in finetuning/.venv ..."
    # Using the parent venv's python to ensure we meet the >=3.11 requirement for deepagents
    ../.venv/bin/python -m venv .venv
    echo "[SETUP] Installing required dependencies..."
    # Upgrade pip to avoid warnings
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
    echo "[SETUP] Virtual environment successfully configured!"
    echo "----------------------------------------------------"
fi

# Activate the local virtual environment for this session
source .venv/bin/activate

COMMAND=$1

case "$COMMAND" in
    "generate")
        echo "[RUNNING] Dataset Generator..."
        python dataset_generator.py
        ;;
    "simulate")
        # Shift pops 'simulate' out of the args, passing any limits/flags straight to the python script
        shift
        echo "[RUNNING] DeepAgent Simulator..."
        python run_deepagent_simulation.py "$@"
        ;;
    "extract")
        shift
        echo "[RUNNING] LangSmith Extractor..."
        python langsmith_client.py "$@"
        ;;
    "format")
        echo "[RUNNING] Dataset Formatter..."
        python dataset_formatter.py
        ;;
    *)
        echo "DeepAgent Distillation Tool"
        echo "Usage: ./run_pipeline.sh [command] [args...]"
        echo ""
        echo "Commands:"
        echo "  generate     Generates the synthetic questions using Gemini"
        echo "  simulate     Feeds generated questions to DeepAgent (accepts --limit N)"
        echo "  extract      Downloads the traces from LangSmith"
        echo "  format       Transforms traces into Qwen ChatML JSONL for Unsloth"
        echo ""
        echo "Example: ./run_pipeline.sh simulate --limit 1"
        exit 1
        ;;
esac
