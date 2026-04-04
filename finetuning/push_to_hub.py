import os
from datasets import load_dataset
from huggingface_hub import login

def push_dataset_to_hub(
    jsonl_path="qwen_training_dataset.jsonl",
    dataset_repo="your-hf-username/deepagent-qwen-tools",
    private=True
):
    """
    Push a JSONL dataset to Hugging Face Hub so it can be easily accessed 
    from Google Colab.
    
    Requires HF_TOKEN environment variable.
    """
    token = os.getenv("HF_TOKEN")
    if not token:
        print("Error: HF_TOKEN environment variable not set.")
        return
        
    print("Logging into Hugging Face...")
    login(token=token)
    
    if not os.path.exists(jsonl_path):
        print(f"Error: Could not find {jsonl_path}")
        return

    print("Loading dataset via Hugging Face datasets library...")
    dataset = load_dataset("json", data_files=jsonl_path, split="train")

    print(f"Pushing dataset to {dataset_repo}...")
    dataset.push_to_hub(dataset_repo, private=private)
    
    print(f"✅ Successfully pushed to https://huggingface.co/datasets/{dataset_repo}")

if __name__ == "__main__":
    # Ensure you've run dataset_formatter.py first to generate the jsonl.
    # Set your specific repoid below:
    push_dataset_to_hub(dataset_repo="kanakjr/deepagent-qwen-tools")
