import json
import os

def build_system_prompt(files):
    """
    Construct the DeepAgent system prompt dynamically from the captured SKILL.md contexts.
    """
    base_prompt = "You are a helpful home automation assistant communicating with the user via Telegram. You have access to various tools and integrations built into the HomeBot ecosystem.\n\n"
    
    contexts = []
    for filepath, filedata in files.items():
        if "content" in filedata:
            # content is typically a list of strings
            text = "\n".join(filedata["content"]) if isinstance(filedata["content"], list) else filedata["content"]
            contexts.append(text)
            
    if contexts:
        base_prompt += "<SKILL_CONTEXT>\n" + "\n\n---\n\n".join(contexts) + "\n</SKILL_CONTEXT>\n"
        
    return base_prompt

def format_to_qwen_chatml(system_prompt, user_query, assistant_content, tool_calls):
    """
    Formats the interaction into HuggingFace dataset conversations compatible with Qwen Chat templates.
    """
    
    formatted_tool_calls = []
    for tc in tool_calls:
        # LangSmith emits "args", but Qwen expects standard "arguments" dict structure or JSON string
        formatted_tool_calls.append({
            "type": "function",
            "function": {
                "name": tc.get("name"),
                "arguments": json.dumps(tc.get("args", {})) # strict JSON string expected by SFTTrainer for Qwen
            }
        })
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]
    
    # If there's a tool call, we add it to the assistant role
    if formatted_tool_calls:
        messages.append({
            "role": "assistant", 
            "content": assistant_content if assistant_content else "",
            "tool_calls": formatted_tool_calls
        })
    else:
        messages.append({
            "role": "assistant",
            "content": assistant_content if assistant_content else ""
        })
        
    return {"messages": messages}

def process_langsmith_traces(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"File {input_file} not found. Run LangSmith extractor first.")
        return

    formatted_dataset = []
    seen_hashes = set()
    
    with open(input_file, "r") as f:
        for line_index, line in enumerate(f):
            if not line.strip():
                continue
                
            try:
                trace = json.loads(line)
            except json.JSONDecodeError:
                print(f"Failed to parse JSON on line {line_index}.")
                continue
            
            inputs = trace.get("inputs", {})
            messages = inputs.get("messages", [])
            files = trace.get("files", {})
            
            # Find the original Human query and the FIRST AI response (which holds the zero-shot tool call)
            user_query = None
            ai_tool_calls = []
            ai_content = ""
            
            for msg in messages:
                if msg.get("type") == "human" and not user_query:
                    user_query = msg.get("content")
                elif msg.get("type") == "ai" and not ai_tool_calls:
                    # Capture the first AI response
                    ai_content_raw = msg.get("content")
                    ai_content = ai_content_raw if isinstance(ai_content_raw, str) else ""
                    ai_tool_calls = msg.get("tool_calls", [])
                    
                    if ai_tool_calls:
                        break # Found what we need!
            
            if not user_query or not ai_tool_calls:
                # If there's no tool call, it might be a hallucination failure, skip it for training
                print(f"Skipping trace {trace.get('id')} - No valid tool calls found.")
                continue
                
            system_prompt = build_system_prompt(files)
            
            row = format_to_qwen_chatml(
                system_prompt=system_prompt,
                user_query=user_query,
                assistant_content=ai_content,
                tool_calls=ai_tool_calls
            )
            
            # LangSmith logs the same payloads multiple times per node. Deduplicate them.
            row_hash = json.dumps(row, sort_keys=True)
            if row_hash not in seen_hashes:
                seen_hashes.add(row_hash)
                formatted_dataset.append(row)
            
    # Guarantee target directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
    with open(output_file, "w") as f:
        for row in formatted_dataset:
            f.write(json.dumps(row) + "\n")
            
    print(f"✅ Formatted {len(formatted_dataset)} records to Qwen ChatML format in {output_file}")

if __name__ == "__main__":
    input_path = os.path.join(os.path.dirname(__file__), "data", "langsmith_export.jsonl")
    output_path = os.path.join(os.path.dirname(__file__), "data", "qwen_training_dataset.jsonl")
    
    process_langsmith_traces(input_path, output_path)
