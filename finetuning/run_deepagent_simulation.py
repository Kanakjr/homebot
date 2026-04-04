#!/usr/bin/env python3
"""
DeepAgent Simulation Runner (HTTP Mode)
Sends synthetic queries to the live DeepAgent FastAPI server as if from a user chat input.
This guarantees exact environment matches and allows the live server to record traces exactly as it does for real users.
"""

import os
import sys
import json
import time
import requests
import argparse
from dotenv import load_dotenv

# Load the backend's .env so we get the correct API_KEY
backend_env = os.path.join(os.path.dirname(__file__), "..", "deepagent", ".env")
load_dotenv(backend_env)
# Load local .env to override any specific keys (like MODEL)
load_dotenv(override=True)

def run_simulation(limit=None, base_url="http://localhost:8322", model="google_genai:gemini-3-flash-preview", run_id=None):
    queries_file = os.path.join(os.path.dirname(__file__), "data", "synthetic_queries.json")
    if not os.path.exists(queries_file):
        print(f"Error: {queries_file} not found. Please run dataset generator first.")
        sys.exit(1)
        
    with open(queries_file, "r") as f:
        queries = json.load(f)
        
    if limit is not None:
        queries = queries[:limit]
        print(f"Limiting execution to {limit} queries for testing.")
    
    # Generate run_id if not provided
    run_prefix = run_id if run_id else f"run_{int(time.time())}"
    
    print(f"Ready to run {len(queries)} simulation queries against {base_url}.")
    print(f"Teacher Model: {model}")
    print(f"Run ID: {run_prefix}")
    print("-" * 50)
    
    for i, q in enumerate(queries):
        print(f"[{i+1}/{len(queries)}] Executing: '{q}'")
        
        # Construct exact payload that the Telegram/Web UI uses
        payload = {
            "message": q,
            "thread_id": f"distill_sim_{run_prefix}_{i}",
            "model": model
        }
        
        try:
            url = f"{base_url}/api/chat/stream"
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": os.getenv("API_KEY", "")
            }
            
            def attempt_query(message_text, is_retry=False):
                payload = {
                    "message": message_text,
                    "thread_id": f"{run_prefix}_{i}",
                    "model": model,
                    "tags": ["distillation_simulation", run_prefix]
                }
                
                # Wait up to 30s for connection, and read stream indefinitely but fail if absolutely locked
                response = requests.post(url, json=payload, headers=headers, stream=True, timeout=120)
                response.raise_for_status()
                
                tool_called = False
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith("event: error"):
                            print(f"  -> WARNING: Server emitted an error event!")
                        elif decoded_line.startswith("event: tool_call"):
                            tool_called = True
                return tool_called

            # First attempt
            tool_used = attempt_query(q)
            
            if tool_used:
                print(f"  -> Successfully generated zero-shot trace. (Thread ID: distill_sim_{run_prefix}_{i})")
            else:
                print(f"  -> Model hallucinated text instead of using tools. Retrying via multi-turn repair...")
                # Second attempt to force the tool call via multi-turn memory
                repair_prompt = "You did not actually perform the action using the tool. Please do not reply with text only. Use the appropriate tool to fulfill my previous request."
                tool_used_retry = attempt_query(repair_prompt, is_retry=True)
                if tool_used_retry:
                    print(f"  -> Successfully repaired trace! (Thread ID: distill_sim_{run_prefix}_{i})")
                else:
                    print(f"  -> ERROR: Model refused to use tools even after repair.")
            
        except requests.exceptions.RequestException as e:
            print(f"  -> FAILED: Could not reach target {url} - {e}")
            print("  Is your homebot live backend running via PM2 or docker?")
            sys.exit(1)
            
        time.sleep(1) # Minor pause to prevent API rate limiting

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeepAgent HTTP Simulator")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of queries.")
    parser.add_argument("--host", type=str, default="http://localhost:8322", help="FastAPI host URL")
    parser.add_argument("--model", type=str, default="google_genai:gemini-3-flash-preview", help="Model to inject into DeepAgent")
    parser.add_argument("--run-id", type=str, default=None, help="Custom Run ID to tag the batch.")
    args = parser.parse_args()
    
    run_simulation(limit=args.limit, base_url=args.host, model=args.model, run_id=args.run_id)
