# Qwen 3.5 DeepAgent Tool-Calling Finetuning (Distillation Pipeline)

This folder contains the complete pipeline to fine-tune a **Qwen 3.5 (0.8B/2B)** model to flawlessly execute the `deepagent` skills using an automated **Teacher-Student Distillation Loop**.

Instead of guessing synthetic JSON structures, this pipeline forces a massive Teacher model (e.g. Gemini 2.5) to actively drive your **live `deepagent` core**. It hooks directly into your production Docker container via HTTP, extracting perfect tool-calling traces from LangSmith to act as the golden dataset for the Student model.

## 📁 Architecture

1. **`dataset_generator.py` (The Grounder)**: Crawls your real `SKILL.md` entities to provide exact context to Gemini 2.5 Pro, generating 50-100+ highly realistic, colloquial string inputs.
2. **`run_deepagent_simulation.py` (The HTTP Teacher)**: Rather than wrestling with Python dependencies in an isolated virtual environment, this script acts as an API Client. It fires `POST` payload requests strictly to your **live `deepagent` FastAPI backend**, dynamically intercepting SSE chunks.
    *   **Auto-Repair**: Extremely powerful zero-shot models often hallucinate text instead of emitting JSON tools. If the live SSE stream misses the `tool_calls` event, the simulator natively loops and generates a multi-turn repair prompt (`You did not use a tool...`) to guarantee the Teacher perfectly completes the task.
3. **`langsmith_client.py` (The Extractor)**: Native tracing integration! Connects to LangSmith and pulls all runs securely tagged with `distillation_simulation`.
4. **`dataset_formatter.py` (The Packager) - *Pending***: Strips out the multi-turn repair hallucinatory turns and stitches the golden tool calls directly against the zero-shot user queries, converting them into Qwen ChatML JSONL.

## 🚀 Execution Guide

This pipeline is fully containerized inside its own `.venv` environment to avoid modifying your main homebot core. Everything runs seamlessly via the `./run_pipeline.sh` orchestrator.

### 1. Initial Setup
The `run_pipeline.sh` bash script automatically creates the `finetuning/.venv` and installs standard requirements (`python-dotenv`, `requests`, `langchain`, `google-genai`).

**Keys and Configs**: 
Because we proxy all simulation requests through HTTP directly to the deployed native bot, the simulation script smartly reaches into `../deepagent/.env` to read `API_KEY` and `LANGSMITH_PROJECT`. No painful environment variable duplication required! Just make sure your API keys are correct inside the `deepagent` folder.

### 2. Run the Pipeline

You can kick off the entire distillation workflow step-by-step:

#### A. Generate Synthetic Queries
Parses your `SKILL.md` instructions and builds `data/synthetic_queries.json`:
```bash
./run_pipeline.sh generate
```

#### B. Simulate the Teacher (Live Run)
Fires the queries over HTTP (`http://localhost:8322/api/chat/stream`) against your live dashboard backend.
*⚠️ WARNING: Because this hits your live bot, it WILL turn on actual lights and ping actual services.*
```bash
# Test with only 1 query:
./run_pipeline.sh simulate --limit 1

# Or run the full production batch!
./run_pipeline.sh simulate
```

#### C. Extract the Golden Traces
Downloads the perfectly tagged traces from LangSmith into `data/langsmith_export.jsonl`:
```bash
./run_pipeline.sh extract
```

#### D. Format for Qwen
Converts the traces into the strict Unsloth ChatML schema:
```bash
./run_pipeline.sh format
```

### 3. Native Model Training

Upload the generated `.jsonl` dataset to Google Colab.

Attach a standard T4 GPU, open `unsloth_qwen_tool_lora.ipynb`, and run all blocks. It natively fine-tunes the lightweight Qwen model using 4-bit quantization, exporting the `.gguf` architecture so you can mount it directly back into `homebot` using Ollama!
