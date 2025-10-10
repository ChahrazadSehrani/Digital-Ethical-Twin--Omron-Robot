"""
Ethical reasoning using Qwen model via Hugging Face InferenceClient
"""
import os
import json
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
import requests

# Fix import path - add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Import context_builder from same directory
import context_builder

# Load environment variables
load_dotenv()

# Configuration
HF_TOKEN = os.getenv("HF_TOKEN")
FIWARE_URL = "http://localhost:1026/ngsi-ld/v1"

# Initialize Hugging Face InferenceClient
client = InferenceClient(
    provider="novita",
    api_key=HF_TOKEN,
)

# Model selection
MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"

def call_llm(prompt, max_tokens=800):
    """
    Call Hugging Face LLM via InferenceClient
    
    Args:
        prompt (str): The ethical reasoning prompt
        max_tokens (int): Maximum response length
    
    Returns:
        str: LLM response text
    """
    try:
        print(f"🤖 Calling LLM: {MODEL.split('/')[-1]}...")
        print("   (This may take 10-30 seconds...)")
        
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are an ethical decision system for autonomous robots. You analyze situations and make decisions prioritizing human safety. Always respond with valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=max_tokens,
            temperature=0.3,  # Low temperature for consistent decisions
        )
        
        response_text = completion.choices[0].message.content
        print("✅ LLM response received")
        
        return response_text
        
    except Exception as e:
        print(f"❌ Error calling LLM: {e}")
        print(f"   Error type: {type(e).__name__}")
        return None

def parse_llm_response(response_text):
    """
    Parse and validate LLM response
    Extracts JSON from response even if there's extra text
    
    Returns:
        dict: Parsed decision or None if invalid
    """
    if not response_text:
        return None
    
    try:
        # Try direct JSON parse first
        decision = json.loads(response_text)
        return validate_decision(decision)
    except json.JSONDecodeError:
        # If direct parse fails, try to extract JSON from text
        print("⚠️  Response not pure JSON, attempting to extract...")
        
        # Find JSON object in text (handle nested braces)
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
        
        if json_match:
            try:
                decision = json.loads(json_match.group())
                return validate_decision(decision)
            except Exception as e:
                print(f"⚠️  JSON extraction failed: {e}")
                pass
        
        print("❌ Could not parse LLM response as JSON")
        print(f"Response was: {response_text[:300]}...")
        return None

def validate_decision(decision):
    """Validate that decision has all required fields"""
    required_fields = ["chosen_path", "confidence", "reasoning", "safety_score"]
    
    for field in required_fields:
        if field not in decision:
            print(f"❌ Missing required field: {field}")
            return None
    
    # Validate values
    if decision["chosen_path"] not in ["A", "B"]:
        print(f"❌ Invalid path choice: {decision['chosen_path']}")
        return None
    
    # Normalize confidence to 0-1 range
    if decision["confidence"] > 1:
        decision["confidence"] = decision["confidence"] / 100
    
    if not (0 <= decision["confidence"] <= 1):
        print(f"⚠️  Confidence out of range: {decision['confidence']}, clamping to [0,1]")
        decision["confidence"] = max(0, min(1, decision["confidence"]))
    
    if not (0 <= decision["safety_score"] <= 100):
        print(f"⚠️  Safety score out of range: {decision['safety_score']}, clamping to [0,100]")
        decision["safety_score"] = max(0, min(100, decision["safety_score"]))
    
    return decision

def execute_decision(decision, context):
    """
    Execute the LLM's decision by updating robot in FIWARE
    
    Args:
        decision (dict): Parsed LLM decision
        context (dict): Original context used for decision
    """
    chosen_path = decision["chosen_path"]
    path_key = f"path_{'a' if chosen_path == 'A' else 'b'}"
    path_info = context[path_key]
    
    print(f"\n🎯 EXECUTING DECISION: Path {chosen_path}")
    print(f"   Reasoning: {decision['reasoning']}")
    print(f"   Confidence: {decision['confidence']*100:.0f}%")
    print(f"   Safety Score: {decision['safety_score']}/100")
    
    # Update robot with chosen path decision
    update_data = {
        "status": {
            "type": "Property",
            "value": "path_chosen"
        },
        "chosenPath": {
            "type": "Property",
            "value": chosen_path
        },
        "ethicalReasoning": {
            "type": "Property",
            "value": decision["reasoning"]
        },
        "decisionConfidence": {
            "type": "Property",
            "value": decision["confidence"]
        }
    }
    
    try:
        response = requests.patch(
            f"{FIWARE_URL}/entities/urn:ngsi-ld:Robot:omron_01/attrs",
            headers={"Content-Type": "application/json"},
            json=update_data
        )
        
        if response.status_code == 204:
            print("✅ Decision recorded in FIWARE Digital Twin")
            return True
        else:
            print(f"⚠️  Failed to update FIWARE: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error updating FIWARE: {e}")
        return False

def make_ethical_decision():
    """
    Complete ethical reasoning pipeline:
    1. Build context from FIWARE
    2. Format prompt for LLM
    3. Call LLM
    4. Parse response
    5. Execute decision
    """
    print("\n🧠 ETHICAL REASONING SYSTEM")
    print("="*70)
    print()
    
    # Step 1: Build context
    print("📊 Building context from FIWARE...")
    context = context_builder.build_context()
    if not context:
        print("❌ Failed to build context")
        return None
    
    # Step 2: Format prompt
    prompt = context_builder.format_context_for_llm(context)
    
    print("\n📋 CONTEXT FOR LLM:")
    print("-"*70)
    print(f"Robot Battery: {context['robot']['battery']}%")
    print(f"Path A: {context['path_a']['distance']}m, {len(context['path_a']['detected_humans'])} humans")
    print(f"Path B: {context['path_b']['distance']}m, {len(context['path_b']['detected_humans'])} humans")
    print("-"*70)
    
    # Step 3: Call LLM
    print("\n📡 Sending to LLM for ethical reasoning...")
    llm_response = call_llm(prompt)
    
    if not llm_response:
        print("❌ No response from LLM")
        return None
    
    print(f"\n💬 LLM Response:")
    print("-"*70)
    print(llm_response)
    print("-"*70)
    
    # Step 4: Parse response
    decision = parse_llm_response(llm_response)
    
    if not decision:
        print("❌ Failed to parse LLM decision")
        return None
    
    # Step 5: Display and execute
    print("\n" + "="*70)
    print("🎯 ETHICAL DECISION")
    print("="*70)
    print(f"Chosen Path: {decision['chosen_path']}")
    print(f"Confidence: {decision['confidence']*100:.0f}%")
    print(f"Safety Score: {decision['safety_score']}/100")
    print(f"Reasoning: {decision['reasoning']}")
    if 'primary_concern' in decision:
        print(f"Primary Concern: {decision['primary_concern']}")
    print("="*70)
    print()
    
    # Execute decision
    execute_decision(decision, context)
    
    return decision

if __name__ == "__main__":
    # Check token
    if not HF_TOKEN:
        print("❌ HF_TOKEN not found in .env file")
        print("\n   Please add your Hugging Face token to .env:")
        print("   HF_TOKEN=hf_xxxxxxxxxxxxxxxxx")
        print("\n   Get your token at: https://huggingface.co/settings/tokens")
        exit(1)
    
    print(f"✅ Using model: {MODEL}")
    print(f"✅ HF Token configured: {HF_TOKEN[:10]}...")
    print()
    
    # Make decision
    decision = make_ethical_decision()
    
    if decision:
        print("\n✅ Ethical reasoning complete!")
        print("\n💡 Next steps:")
        print("   - Check FIWARE: python src/digital_twin/inspect_dt.py")
        print("   - Simulate movement: python src/digital_twin/simulate_robot_path.py")
    else:
        print("\n❌ Ethical reasoning failed")
        print("   Check the errors above for details")