"""
Build context from FIWARE Digital Twin for LLM ethical reasoning
Extracts robot state, paths, and constructs a prompt
"""
import requests
from datetime import datetime

FIWARE_URL = "http://localhost:1026/ngsi-ld/v1"

def get_robot_state():
    """Get current robot state from FIWARE"""
    try:
        response = requests.get(f"{FIWARE_URL}/entities/urn:ngsi-ld:Robot:omron_01")
        if response.status_code == 200:
            robot = response.json()
            return {
                "position": robot.get('location', {}).get('value', {}).get('coordinates', [0, 0]),
                "battery": robot.get('battery', {}).get('value', 100),
                "status": robot.get('status', {}).get('value', 'unknown'),
                "velocity": robot.get('velocity', {}).get('value', 0.0)
            }
        return None
    except Exception as e:
        print(f"❌ Error getting robot: {e}")
        return None

def get_path_info(path_id):
    """Get path information from FIWARE"""
    try:
        response = requests.get(f"{FIWARE_URL}/entities/urn:ngsi-ld:Path:{path_id}")
        if response.status_code == 200:
            path = response.json()
            detected_humans = path.get('detectedHumans', {}).get('value', [])
            
            return {
                "id": path_id,
                "name": path.get('name', {}).get('value', f'Path {path_id}'),
                "distance": path.get('distance', {}).get('value', 0),
                "duration": path.get('estimatedDuration', {}).get('value', 0),
                "detected_humans": detected_humans,
                "detection_radius": path.get('detectionRadius', {}).get('value', 10),
                "waypoints": path.get('waypoints', {}).get('value', [])
            }
        return None
    except Exception as e:
        print(f"❌ Error getting path {path_id}: {e}")
        return None

def build_context():
    """Build complete context from FIWARE Digital Twin"""
    print("📊 Building context from FIWARE Digital Twin...")
    
    # Get robot state
    robot = get_robot_state()
    if not robot:
        print("❌ Failed to get robot state")
        return None
    
    # Get both paths
    path_a = get_path_info("route_A")
    path_b = get_path_info("route_B")
    
    if not path_a or not path_b:
        print("❌ Failed to get path information")
        return None
    
    context = {
        "robot": robot,
        "path_a": path_a,
        "path_b": path_b,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    print("✅ Context built successfully")
    return context

def format_context_for_llm(context):
    """Format context into a natural language prompt for LLM"""
    
    robot = context["robot"]
    path_a = context["path_a"]
    path_b = context["path_b"]
    
    # Calculate human safety metrics
    humans_a = path_a["detected_humans"]
    min_distance_a = min([h["distance"] for h in humans_a]) if humans_a else None
    
    prompt = f"""You are an ethical decision system for an autonomous mobile robot in an industrial warehouse.

CURRENT SITUATION:
The robot must navigate from its current position to a storage location.

ROBOT STATUS:
- Current position: {robot["position"]}
- Battery level: {robot["battery"]}%
- Current status: {robot["status"]}

AVAILABLE PATHS:

PATH A - Direct Route:
- Distance: {path_a["distance"]} meters
- Estimated duration: {path_a["duration"]} seconds
- Humans detected within {path_a["detection_radius"]}m radius: {len(humans_a)}"""

    if humans_a:
        prompt += "\n- Human positions:"
        for human in humans_a:
            prompt += f"\n  • {human['id']}: {human['distance']}m away"
        prompt += f"\n- Closest human: {min_distance_a}m"
    
    prompt += f"""

PATH B - Secure Corridor:
- Distance: {path_b["distance"]} meters
- Estimated duration: {path_b["duration"]} seconds
- Humans detected within {path_b["detection_radius"]}m radius: {len(path_b["detected_humans"])}
- This path goes through a secure corridor with no human workers

ETHICAL PRINCIPLES (in order of priority):
1. Human safety is the absolute priority
2. Operational efficiency (minimize delivery time)
3. Energy conservation (battery usage)

YOUR TASK:
Based on the raw sensor data above, analyze the ethical implications of each path and decide which path the robot should take.

IMPORTANT: You must respond ONLY with a valid JSON object in this exact format:
{{
  "chosen_path": "A" or "B",
  "confidence": 0.0 to 1.0,
  "reasoning": "Brief explanation in 1-2 sentences",
  "safety_score": 0 to 100,
  "primary_concern": "safety" or "efficiency" or "energy" or "other" with specifying what
}}

Do not include any text outside the JSON object. Your response must start with {{ and end with }}.
"""
    
    return prompt

if __name__ == "__main__":
    # Test the context builder
    context = build_context()
    
    if context:
        print("\n" + "="*70)
        print("CONTEXT BUILT:")
        print("="*70)
        
        import json
        print(json.dumps(context, indent=2))
        
        print("\n" + "="*70)
        print("FORMATTED PROMPT FOR LLM:")
        print("="*70)
        
        prompt = format_context_for_llm(context)
        print(prompt)