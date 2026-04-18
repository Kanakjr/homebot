#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "[SETUP] Creating a clean virtual environment in finetuning/.venv ..."
    ../.venv/bin/python -m venv .venv
    echo "[SETUP] Installing required dependencies..."
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
    echo "[SETUP] Virtual environment successfully configured!"
    echo "----------------------------------------------------"
fi

source .venv/bin/activate

COMMAND=$1

case "$COMMAND" in
    "generate")
        echo "[RUNNING] Dataset Generator (clustered per skill)..."
        python dataset_generator.py
        ;;
    "simulate")
        shift
        echo "[RUNNING] DeepAgent Simulator..."
        python run_deepagent_simulation.py "$@"
        ;;
    "extract")
        shift
        echo "[RUNNING] LangSmith Extractor (synthetic traces)..."
        python langsmith_client.py "$@"
        ;;
    "format")
        echo "[RUNNING] Dataset Formatter (multi-turn ChatML)..."
        python dataset_formatter.py
        ;;
    "real")
        shift
        echo "[RUNNING] Real Telegram Dataset Extractor..."
        python extract_telegram_dataset.py "$@"
        ;;
    "merge")
        shift
        echo "[RUNNING] Merge & train/val split..."
        python merge_datasets.py "$@"
        ;;
    "push")
        shift
        echo "[RUNNING] Push to HuggingFace Hub..."
        python push_to_hub.py "$@"
        ;;
    "all")
        echo "[RUNNING] Full pipeline: generate -> simulate -> extract -> format -> real -> merge -> push"
        python dataset_generator.py
        python run_deepagent_simulation.py
        python langsmith_client.py
        python dataset_formatter.py
        python extract_telegram_dataset.py
        python merge_datasets.py
        python push_to_hub.py
        ;;
    *)
        echo "DeepAgent Distillation + Qwen3.5-4B Fine-tune Pipeline"
        echo "Usage: ./run_pipeline.sh [command] [args...]"
        echo ""
        echo "Commands:"
        echo "  generate     Generate synthetic user queries with Gemini (clustered by skill)"
        echo "  simulate     Feed synthetic queries to the live DeepAgent (--limit N)"
        echo "  extract      Download the synthetic simulation traces from LangSmith"
        echo "  format       Transform synthetic traces -> multi-turn Qwen ChatML JSONL"
        echo "  real         Extract real Telegram conversations from LangSmith -> JSONL"
        echo "  merge        Merge real + synthetic, dedup, 90/10 train/val split"
        echo "  push         Push merged dataset to HuggingFace Hub"
        echo "  all          Run generate -> simulate -> extract -> format -> real -> merge -> push"
        echo ""
        echo "Typical flow:"
        echo "  ./run_pipeline.sh generate"
        echo "  ./run_pipeline.sh simulate --limit 50"
        echo "  ./run_pipeline.sh extract"
        echo "  ./run_pipeline.sh format"
        echo "  ./run_pipeline.sh real"
        echo "  ./run_pipeline.sh merge"
        echo "  ./run_pipeline.sh push"
        exit 1
        ;;
esac
