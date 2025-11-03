"""
Quick test of Hugging Face InferenceClient
"""
import os
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")

if not HF_TOKEN:
    print("❌ HF_TOKEN not found in .env")
    exit(1)

print(f"✅ Token found: {HF_TOKEN[:10]}...")
print("\n🧪 Testing Hugging Face InferenceClient...\n")

try:
    client = InferenceClient(
        provider="novita",
        api_key=HF_TOKEN,
    )
    
    print("📡 Sending test request...")
    
    completion = client.chat.completions.create(
        model="Qwen/Qwen3-Next-80B-A3B-Instruct",
        messages=[
            {
                "role": "user",
                "content": "What is the capital of France? Answer in one word only."
            }
        ],
        max_tokens=10,
    )
    
    print("✅ Response received!\n")
    print(f"💬 Answer: {completion.choices[0].message.content}")
    print("\n✅ Hugging Face API is working!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print(f"   Error type: {type(e).__name__}")