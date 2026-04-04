import os
import json
import glob
from dotenv import load_dotenv

# Use standard Langchain wrapper which we know is installed
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

load_dotenv()

MODEL_ID = "gemini-2.5-pro"

def get_skill_contexts():
    """
    Reads all SKILL.md files from the deepagent/skills directory
    to provide the exact environment context (entities, devices, rules) 
    to Gemini.
    """
    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deepagent", "skills"))
    skill_files = glob.glob(os.path.join(app_dir, "*", "SKILL.md"))
    
    contexts = []
    for sf in skill_files:
        with open(sf, "r") as f:
            contexts.append(f.read())
            
    return "\n\n---\n\n".join(contexts)

def generate_queries(api_key: str, num_queries: int = 50):
    llm = ChatGoogleGenerativeAI(
        model=MODEL_ID,
        google_api_key=api_key,
        temperature=1.0,
    )
    
    print("Reading DeepAgent SKILL.md contexts...")
    skill_context = get_skill_contexts()
    
    print(f"Generating {num_queries} highly realistic user questions...")
    
    prompt = f"""
You are simulating a user living in a smart home texting their personal Telegram assistant.
Below are the exact skills, devices, entities, and capabilities the assistant currently has access to.

<SKILL_CONTEXT>
{skill_context}
</SKILL_CONTEXT>

Generate {num_queries} highly diverse, conversational user queries that would trigger these skills. 
RULES:
1. Use real entity names and capabilities from the context (e.g., "turn off the air purifier", "download the latest episode of Severance", "is anyone home?", "how much power is the workstation using?").
2. Make them sound conversational, sometimes terse, sometimes complex via Telegram messages.
3. Include typos, slang, and variations in how people text.
4. ONLY return a valid JSON array of strings. Format exactly like this: ["query 1", "query 2"]. Do not use markdown wrapping.
"""

    response = llm.invoke([HumanMessage(content=prompt)])
    
    # Strip potential markdown block syntax if the LLM ignores instructions
    raw_text = response.content.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    raw_text = raw_text.strip()
    
    try:
        queries = json.loads(raw_text)
        return queries
    except Exception as e:
        print(f"Failed to parse JSON response. Error: {e}")
        
        # Attempt to salvage the generated text using regex
        import re
        # Find all strings inside double quotes
        salvaged = re.findall(r'"([^"]*)"', raw_text)
        # Keep only reasonably sized sentences (filter out JSON keys if any)
        salvaged = [s.strip() for s in salvaged if len(s) > 10 and not s.startswith("http")]
        
        if salvaged:
            print(f"Salvaged {len(salvaged)} queries automatically via regex fallback!")
            return salvaged
            
        print("Raw response:", raw_text)
        return []

if __name__ == "__main__":
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not gemini_key:
        print("Error: GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set in .env")
        exit(1)
        
    queries = generate_queries(gemini_key, num_queries=50)
    
    if queries:
        out_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, "synthetic_queries.json")
        
        with open(out_file, "w") as f:
            json.dump(queries, f, indent=2)
            
        print(f"Successfully generated {len(queries)} realistic queries and saved to {out_file}")
