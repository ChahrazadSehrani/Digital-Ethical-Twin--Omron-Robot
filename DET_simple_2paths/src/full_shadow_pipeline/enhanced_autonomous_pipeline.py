"""
ULTIMATE ETHICAL NAVIGATION SYSTEM - CORPUS STRUCTURE
======================================================
Complete code structure with function signatures and descriptions
"""

import os
import json
import re
import time
import requests
import random
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
from threading import Thread
from dotenv import load_dotenv
import pickle

try:
    from huggingface_hub import InferenceClient
except:
    InferenceClient = None

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

FIWARE_URL = "http://localhost:1026/ngsi-ld/v1"
HF_TOKEN = os.getenv("HF_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"
CUSTOM_MODES_FILE = "custom_ethical_modes.pkl"

try:
    if InferenceClient and HF_TOKEN:
        client = InferenceClient(provider="novita", api_key=HF_TOKEN)
    else:
        client = None
except:
    client = None


# ============================================================================
# FIWARE DATA RETRIEVAL FUNCTIONS
# ============================================================================

def get_all_robots():
    """
    Retrieve all robots from FIWARE Context Broker.
    
    Returns:
        list: List of robot dictionaries with complete data
    """
    try:
        # Try both common robot entity types
        for robot_type in ["MobileRobot", "Robot"]:
            response = requests.get(
                f"{FIWARE_URL}/entities?type={robot_type}",
                timeout=3
            )
            
            if response.status_code == 200:
                robots = response.json()
                
                if robots:  # If we found robots, process and return them
                    result = []
                    
                    for r in robots:
                        # Extract robot ID
                        robot_id = r.get("id", "Unknown")
                        robot_name = robot_id.split(":")[-1] if ":" in robot_id else robot_id
                        
                        # Extract position (handle different formats)
                        position = [0.0, 0.0]
                        if 'location' in r:
                            loc = r['location'].get('value', {})
                            if isinstance(loc, dict):
                                position = loc.get('coordinates', [0.0, 0.0])
                            elif isinstance(loc, list):
                                position = loc
                        
                        # Build robot dictionary
                        robot_data = {
                            "id": robot_id,
                            "name": r.get('name', {}).get('value', robot_name),
                            "short_name": robot_name,
                            "position": position[:],  # Current position
                            "initial_position": position[:],  # Copy for origin tracking
                            "battery": r.get('battery', {}).get('value', 100),
                            "status": r.get('status', {}).get('value', 'unknown'),
                            "type": r.get('type', robot_type)
                        }
                        
                        result.append(robot_data)
                    
                    return result
        
        # No robots found in either type
        return []
    
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to FIWARE at {FIWARE_URL}")
        return []
    except requests.exceptions.Timeout:
        print(f"⏱️  FIWARE request timeout")
        return []
    except Exception as e:
        print(f"❌ Error getting robots: {e}")
        return []


def get_all_paths():
    """
    Retrieve all navigation paths from FIWARE Context Broker.
    
    Returns:
        list: List of path dictionaries with complete data
    """
    try:
        # Try both common path entity types
        for path_type in ["NavigationPath", "Path"]:
            response = requests.get(
                f"{FIWARE_URL}/entities?type={path_type}",
                timeout=3
            )
            
            if response.status_code == 200:
                paths = response.json()
                
                if paths:  # If we found paths, process and return them
                    result = []
                    
                    for p in paths:
                        # Extract path ID
                        path_id = p.get("id", "Unknown")
                        path_name = path_id.split(":")[-1] if ":" in path_id else path_id
                        
                        # Extract waypoints (handle different formats)
                        waypoints = []
                        if 'waypoints' in p:
                            wp_value = p['waypoints'].get('value', [])
                            if isinstance(wp_value, list):
                                waypoints = wp_value
                        
                        # Extract detected humans
                        detected_humans = []
                        if 'detectedHumans' in p:
                            humans_value = p['detectedHumans'].get('value', [])
                            if isinstance(humans_value, list):
                                detected_humans = humans_value
                        
                        # Build path dictionary
                        path_data = {
                            "id": path_id,
                            "name": p.get('name', {}).get('value', path_name),
                            "distance": p.get('distance', {}).get('value', 0.0),
                            "duration": p.get('estimatedDuration', {}).get('value', 0.0),
                            "detected_humans": detected_humans,
                            "waypoints": waypoints,
                            "type": p.get('type', path_type)
                        }
                        
                        result.append(path_data)
                    
                    return result
        
        # No paths found in either type
        return []
    
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to FIWARE at {FIWARE_URL}")
        return []
    except requests.exceptions.Timeout:
        print(f"⏱️  FIWARE request timeout")
        return []
    except Exception as e:
        print(f"❌ Error getting paths: {e}")
        return []


def update_robot_position(robot_id, x, y):
    """
    Update robot position in FIWARE Context Broker.
    
    Args:
        robot_id (str): Unique robot identifier
        x (float): X coordinate
        y (float): Y coordinate
    
    Returns:
        bool: True if update successful, False otherwise
    """
    try:
        # Prepare NGSI-LD update payload
        update_payload = {
            "location": {
                "type": "GeoProperty",
                "value": {
                    "type": "Point",
                    "coordinates": [float(x), float(y)]
                }
            }
        }
        
        # Send PATCH request to update entity
        response = requests.patch(
            f"{FIWARE_URL}/entities/{robot_id}/attrs",
            headers={"Content-Type": "application/json"},
            json=update_payload,
            timeout=2
        )
        
        # FIWARE returns 204 No Content on success
        if response.status_code == 204:
            return True
        else:
            print(f"⚠️  FIWARE position update failed: {response.status_code}")
            return False
    
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to FIWARE")
        return False
    except requests.exceptions.Timeout:
        print(f"⏱️  FIWARE request timeout")
        return False
    except Exception as e:
        print(f"❌ Error updating position: {e}")
        return False


def update_robot_status(robot_id, status):
    """
    Update robot status in FIWARE Context Broker.
    
    Args:
        robot_id (str): Unique robot identifier
        status (str): New status (e.g., 'idle', 'moving', 'arrived', 'path_chosen')
    
    Returns:
        bool: True if update successful, False otherwise
    """
    try:
        # Prepare NGSI-LD update payload with timestamp
        update_payload = {
            "status": {
                "type": "Property",
                "value": status,
                "observedAt": datetime.utcnow().isoformat() + "Z"
            }
        }
        
        # Send PATCH request to update entity
        response = requests.patch(
            f"{FIWARE_URL}/entities/{robot_id}/attrs",
            headers={"Content-Type": "application/json"},
            json=update_payload,
            timeout=2
        )
        
        # FIWARE returns 204 No Content on success
        if response.status_code == 204:
            return True
        else:
            print(f"⚠️  FIWARE status update failed: {response.status_code}")
            return False
    
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to FIWARE")
        return False
    except requests.exceptions.Timeout:
        print(f"⏱️  FIWARE request timeout")
        return False
    except Exception as e:
        print(f"❌ Error updating status: {e}")
        return False


def record_decision_in_fiware(robot_id, decision):
    """
    Record LLM decision in FIWARE Digital Twin.
    
    Args:
        robot_id (str): Unique robot identifier
        decision (dict): Decision dictionary containing:
            - chosen_path (str): Selected path identifier
            - reasoning (str): Ethical reasoning explanation
            - confidence (float): Decision confidence (0-1)
            - safety_score (int): Safety score (0-100)
            - primary_concern (str): Main decision factor (optional)
    
    Returns:
        bool: True if recording successful, False otherwise
    """
    try:
        # Prepare comprehensive decision payload
        update_payload = {
            "chosenPath": {
                "type": "Property",
                "value": decision.get("chosen_path", "Unknown")
            },
            "ethicalReasoning": {
                "type": "Property",
                "value": decision.get("reasoning", "No reasoning provided")
            },
            "decisionConfidence": {
                "type": "Property",
                "value": float(decision.get("confidence", 0.0))
            },
            "safetyScore": {
                "type": "Property",
                "value": int(decision.get("safety_score", 0))
            },
            "decisionTimestamp": {
                "type": "Property",
                "value": datetime.utcnow().isoformat() + "Z"
            }
        }
        
        # Add optional primary_concern if present
        if "primary_concern" in decision:
            update_payload["primaryConcern"] = {
                "type": "Property",
                "value": decision["primary_concern"]
            }
        
        # Send PATCH request to update entity
        response = requests.patch(
            f"{FIWARE_URL}/entities/{robot_id}/attrs",
            headers={"Content-Type": "application/json"},
            json=update_payload,
            timeout=2
        )
        
        # FIWARE returns 204 No Content on success
        if response.status_code == 204:
            return True
        else:
            print(f"⚠️  FIWARE decision recording failed: {response.status_code}")
            return False
    
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to FIWARE")
        return False
    except requests.exceptions.Timeout:
        print(f"⏱️  FIWARE request timeout")
        return False
    except Exception as e:
        print(f"❌ Error recording decision: {e}")
        return False


def test_fiware_connection():
    """
    Test FIWARE connection and return diagnostic information.
    
    Returns:
        dict: Diagnostic information with keys:
            - connected (bool): Whether FIWARE is accessible
            - version_info (dict): FIWARE version if available
            - entities_count (dict): Count of robots and paths found
            - error (str): Error message if connection failed
    """
    diagnostic = {
        "connected": False,
        "version_info": None,
        "entities_count": {"robots": 0, "paths": 0},
        "error": None
    }
    
    try:
        # Test basic connectivity
        response = requests.get(
            f"{FIWARE_URL.replace('/ngsi-ld/v1', '')}/version",
            timeout=2
        )
        
        if response.status_code == 200:
            diagnostic["connected"] = True
            try:
                diagnostic["version_info"] = response.json()
            except:
                diagnostic["version_info"] = {"status": "running"}
        
        # Count entities
        robots = get_all_robots()
        paths = get_all_paths()
        diagnostic["entities_count"]["robots"] = len(robots)
        diagnostic["entities_count"]["paths"] = len(paths)
        
        return diagnostic
    
    except requests.exceptions.ConnectionError:
        diagnostic["error"] = f"Cannot connect to {FIWARE_URL}"
        return diagnostic
    except requests.exceptions.Timeout:
        diagnostic["error"] = "Connection timeout"
        return diagnostic
    except Exception as e:
        diagnostic["error"] = str(e)
        return diagnostic


# ============================================================================
# LLM REASONING FUNCTIONS
# ============================================================================

def build_custom_prompt(robot, paths, ethical_mode, custom_instructions="", modes_manager=None):
    """
    Build customized prompt for LLM ethical reasoning.
    
    Args:
        robot (dict): Robot data with keys:
            - name (str): Robot name
            - position (list): [x, y] coordinates
            - battery (int): Battery percentage
            - status (str): Current status
        paths (list): List of path dictionaries with keys:
            - name (str): Path name
            - distance (float): Path distance in meters
            - duration (float): Estimated duration in seconds
            - detected_humans (list): List of human detection objects
            - waypoints (list): List of [x, y] waypoints
        ethical_mode (str): Selected ethical mode name
        custom_instructions (str): User-provided additional instructions
        modes_manager (CustomModesManager): Manager for ethical modes
    
    Returns:
        str: Complete formatted prompt for LLM
    
    Description:
        Constructs a detailed prompt including robot status, available paths
        with human proximity data, ethical principles, and output format.
    """
    
    # Get ethical mode configuration
    if modes_manager:
        all_modes = modes_manager.get_all_modes()
        mode_config = all_modes.get(ethical_mode, all_modes.get("safety", {}))
        priorities = mode_config.get("priorities", [
            "1. Human safety is the ABSOLUTE PRIORITY",
            "2. Operational efficiency",
            "3. Energy conservation"
        ])
    else:
        # Default priorities if no manager provided
        priorities = [
            "1. Human safety is the ABSOLUTE PRIORITY - never compromise safety",
            "2. Operational efficiency (minimize delivery time)",
            "3. Energy conservation (battery usage)"
        ]
    
    # Build prompt header
    prompt = f"""You are an ethical decision system for an autonomous mobile robot in an industrial warehouse.

CURRENT SITUATION:
The robot must navigate from its current position to a destination and needs to choose the best path.

ROBOT STATUS:
- ID: {robot['name']}
- Current position: {robot['position']}
- Battery level: {robot['battery']}%
- Current status: {robot['status']}

AVAILABLE PATHS:
"""
    
    # Add each path with detailed information
    for i, path in enumerate(paths):
        humans = path.get('detected_humans', [])
        
        # Calculate minimum distance to humans
        min_dist = None
        if humans:
            distances = [h.get('distance', float('inf')) for h in humans]
            min_dist = min(distances) if distances else None
        
        # Path header
        prompt += f"""
PATH {chr(65+i)} - {path['name']}:
- Distance: {path['distance']} meters
- Estimated duration: {path['duration']} seconds
- Humans detected: {len(humans)}"""
        
        # Add human proximity details if any humans detected
        if humans:
            prompt += f"\n- Human positions:"
            for human in humans:
                human_id = human.get('id', 'Unknown')
                human_dist = human.get('distance', 'Unknown')
                prompt += f"\n  • {human_id}: {human_dist}m away"
            
            if min_dist is not None:
                prompt += f"\n- Closest human: {min_dist}m"
        else:
            prompt += "\n- No humans detected on this path"
    
    # Add ethical principles
    prompt += f"""

ETHICAL PRINCIPLES (PRIORITY MODE: {ethical_mode.upper()}):
{chr(10).join(priorities)}
"""
    
    # Add custom instructions if provided
    if custom_instructions and custom_instructions.strip():
        prompt += f"""
CUSTOM INSTRUCTIONS:
{custom_instructions.strip()}
"""
    
    # Add output format specification
    prompt += """
YOUR TASK:
Analyze the ethical implications of each path considering:
1. Human safety (proximity to humans, risk assessment)
2. Operational efficiency (time, distance)
3. Energy consumption (battery usage)

Then decide which path the robot should take based on the ethical priorities above.

IMPORTANT: Respond ONLY with a valid JSON object in this EXACT format:
{
  "chosen_path": "A",
  "confidence": 0.95,
  "reasoning": "Brief explanation of the decision in 1-2 sentences",
  "safety_score": 85,
  "primary_concern": "safety"
}

Rules for the JSON response:
- chosen_path: Must be "A", "B", "C", etc. (single letter matching a path)
- confidence: Float between 0.0 and 1.0 (e.g., 0.95 for 95% confidence)
- reasoning: String with brief explanation (max 2 sentences)
- safety_score: Integer between 0 and 100
- primary_concern: Must be one of: "safety", "efficiency", "energy", or "balanced"

Do not include any text outside the JSON object. No markdown, no explanations, just the JSON.
"""
    
    return prompt


def call_llm_with_prompt(prompt):
    """
    Call LLM API and measure inference time.
    
    Args:
        prompt (str): Complete prompt text
    
    Returns:
        tuple: (response_text, inference_time)
            - response_text (str): LLM response content
            - inference_time (float): Time taken in seconds
    
    Description:
        Attempts to call HuggingFace Inference API if configured.
        Falls back to mock decision with simulated delay if API unavailable.
        Measures and returns exact inference time for performance tracking.
    """
    
    # Add cache buster to avoid cached responses
    cache_buster = random.randint(1000, 9999)
    
    # Start timing
    start_time = time.time()
    
    # Try HuggingFace API if client is available
    if client and HF_TOKEN:
        try:
            print(f"🤖 Calling HuggingFace API with model: {MODEL}")
            
            completion = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are an ethical decision system for autonomous robots. Always respond with valid JSON only. No explanations, no markdown, just pure JSON. Request ID: {cache_buster}"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=800,
                temperature=0.7,
                stream=False
            )
            
            # Extract response
            response_text = completion.choices[0].message.content
            inference_time = time.time() - start_time
            
            print(f"✅ HuggingFace API responded in {inference_time:.2f}s")
            return response_text, inference_time
            
        except Exception as e:
            print(f"❌ HuggingFace API error: {e}")
            print("   Falling back to mock decision...")
    
    # Fallback: Generate mock decision
    print("🎭 Using mock decision (no LLM API available)")
    
    # Simulate inference time
    time.sleep(1.5)
    inference_time = time.time() - start_time
    
    # Create realistic mock decision
    mock_decision = {
        "chosen_path": "B",  # Usually middle path is safest
        "confidence": 0.85,
        "reasoning": "Mock decision: Choosing path with better balance of safety and efficiency based on rule-based logic.",
        "safety_score": 90,
        "primary_concern": "safety"
    }
    
    response_text = json.dumps(mock_decision, indent=2)
    
    print(f"✅ Mock decision generated in {inference_time:.2f}s")
    return response_text, inference_time


def parse_llm_response(response_text):
    """
    Parse and validate LLM response JSON.
    
    Args:
        response_text (str): Raw LLM response text
    
    Returns:
        dict or None: Parsed decision dictionary with keys:
            - chosen_path (str): Selected path letter (A, B, C, etc.)
            - confidence (float): Normalized to 0-1 range
            - reasoning (str): Explanation text
            - safety_score (int): Clamped to 0-100 range
            - primary_concern (str): Main decision factor
        Returns None if parsing fails or required fields missing.
    
    Description:
        Attempts direct JSON parsing first, then regex extraction if needed.
        Validates all required fields are present.
        Normalizes confidence and safety_score to proper ranges.
        Handles common LLM response issues (markdown, explanations, etc.).
    """
    
    if not response_text:
        print("❌ Empty response text")
        return None
    
    # Try direct JSON parsing first
    try:
        decision = json.loads(response_text)
        print("✅ Direct JSON parsing successful")
    except json.JSONDecodeError:
        print("⚠️  Direct JSON parsing failed, attempting regex extraction...")
        
        # Try to extract JSON from response using regex
        # Handles cases where LLM adds markdown or explanations
        json_match = re.search(
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
            response_text,
            re.DOTALL
        )
        
        if json_match:
            try:
                decision = json.loads(json_match.group())
                print("✅ Regex extraction successful")
            except json.JSONDecodeError:
                print("❌ Regex extraction failed")
                return None
        else:
            print("❌ No JSON object found in response")
            return None
    
    # Validate required fields
    required_fields = ["chosen_path", "confidence", "reasoning", "safety_score"]
    missing_fields = [field for field in required_fields if field not in decision]
    
    if missing_fields:
        print(f"❌ Missing required fields: {missing_fields}")
        return None
    
    # Normalize and validate confidence (handle percentage format)
    try:
        confidence = float(decision["confidence"])
        if confidence > 1.0:
            # Assume it's a percentage (e.g., 95 instead of 0.95)
            confidence = confidence / 100.0
        # Clamp to [0, 1] range
        decision["confidence"] = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        print(f"⚠️  Invalid confidence value: {decision.get('confidence')}")
        decision["confidence"] = 0.5  # Default
    
    # Normalize and validate safety_score
    try:
        safety_score = int(decision["safety_score"])
        # Clamp to [0, 100] range
        decision["safety_score"] = max(0, min(100, safety_score))
    except (ValueError, TypeError):
        print(f"⚠️  Invalid safety_score value: {decision.get('safety_score')}")
        decision["safety_score"] = 50  # Default
    
    # Validate chosen_path format (should be single letter)
    chosen_path = str(decision["chosen_path"]).strip().upper()
    if len(chosen_path) != 1 or not chosen_path.isalpha():
        print(f"⚠️  Invalid chosen_path format: {decision.get('chosen_path')}")
        decision["chosen_path"] = "A"  # Default to first path
    else:
        decision["chosen_path"] = chosen_path
    
    # Validate primary_concern (optional field)
    if "primary_concern" in decision:
        valid_concerns = ["safety", "efficiency", "energy", "balanced"]
        if decision["primary_concern"] not in valid_concerns:
            print(f"⚠️  Invalid primary_concern: {decision['primary_concern']}")
            decision["primary_concern"] = "safety"  # Default
    else:
        # Add default if missing
        decision["primary_concern"] = "safety"
    
    # Ensure reasoning is a string
    decision["reasoning"] = str(decision.get("reasoning", "No reasoning provided"))
    
    print("✅ Decision validation successful")
    print(f"   Path: {decision['chosen_path']}")
    print(f"   Confidence: {decision['confidence']*100:.1f}%")
    print(f"   Safety Score: {decision['safety_score']}/100")
    
    return decision


# ============================================================================
# CUSTOM ETHICAL MODES MANAGEMENT
# ============================================================================

class CustomModesManager:
    """
    Manager for custom ethical decision modes.
    
    Handles creation, storage, retrieval, and deletion of custom ethical modes.
    Persists modes to disk using pickle for session persistence.
    
    Attributes:
        custom_modes (dict): Dictionary of user-defined ethical modes
            Format: {
                "mode_name": {
                    "priorities": ["1. ...", "2. ...", "3. ..."],
                    "description": "Mode description",
                    "created": "ISO timestamp"
                }
            }
    """
    
    # File for persisting custom modes
    STORAGE_FILE = "custom_ethical_modes.pkl"
    
    def __init__(self):
        """
        Initialize the custom modes manager.
        Automatically loads previously saved modes from disk.
        """
        self.custom_modes = self.load_custom_modes()
        print(f"🎨 CustomModesManager initialized with {len(self.custom_modes)} custom mode(s)")
    
    def load_custom_modes(self):
        """
        Load custom modes from pickle file.
        
        Returns:
            dict: Dictionary of custom modes, empty dict if file not found or error
        
        Description:
            Safely loads the pickle file. Returns empty dict on any error
            to ensure the application starts even if the file is corrupted.
        """
        try:
            if os.path.exists(self.STORAGE_FILE):
                with open(self.STORAGE_FILE, 'rb') as f:
                    loaded_modes = pickle.load(f)
                    
                    # Validate it's a dictionary
                    if isinstance(loaded_modes, dict):
                        print(f"✅ Loaded {len(loaded_modes)} custom mode(s) from disk")
                        return loaded_modes
                    else:
                        print(f"⚠️  Invalid format in {self.STORAGE_FILE}, starting fresh")
                        return {}
            else:
                print(f"ℹ️  No existing custom modes file found")
                return {}
        
        except Exception as e:
            print(f"⚠️  Error loading custom modes: {e}")
            print(f"   Starting with empty custom modes")
            return {}
    
    def save_custom_modes(self):
        """
        Save custom modes to pickle file.
        
        Returns:
            bool: True if save successful, False otherwise
        
        Description:
            Persists current custom_modes dictionary to disk.
            Creates file if it doesn't exist. Atomic write for safety.
        """
        try:
            # Write to temporary file first (atomic write pattern)
            temp_file = self.STORAGE_FILE + ".tmp"
            
            with open(temp_file, 'wb') as f:
                pickle.dump(self.custom_modes, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            # Rename temp file to actual file (atomic on most systems)
            if os.path.exists(self.STORAGE_FILE):
                os.remove(self.STORAGE_FILE)
            os.rename(temp_file, self.STORAGE_FILE)
            
            print(f"💾 Saved {len(self.custom_modes)} custom mode(s) to disk")
            return True
        
        except Exception as e:
            print(f"❌ Error saving custom modes: {e}")
            return False
    
    def add_mode(self, name, priorities, description=""):
        """
        Add a new custom ethical mode.
        
        Args:
            name (str): Unique mode name (will be converted to lowercase with underscores)
            priorities (list): List of priority strings (e.g., ["1. Safety first", "2. ..."])
            description (str): Human-readable mode description
        
        Returns:
            bool: True if mode added successfully, False if validation failed
        
        Description:
            Creates new mode with priorities and metadata.
            Automatically saves to disk after adding.
            Validates that name doesn't conflict with built-in modes.
        """
        # Sanitize name: lowercase, replace spaces with underscores
        sanitized_name = name.lower().strip().replace(' ', '_')
        
        # Validate name is not empty
        if not sanitized_name:
            print("❌ Mode name cannot be empty")
            return False
        
        # Check if it conflicts with built-in modes
        built_in_modes = ["safety", "efficiency", "energy", "balanced"]
        if sanitized_name in built_in_modes:
            print(f"❌ Cannot use built-in mode name: {sanitized_name}")
            return False
        
        # Validate priorities is a non-empty list
        if not isinstance(priorities, list) or not priorities:
            print("❌ Priorities must be a non-empty list")
            return False
        
        # Create mode entry
        self.custom_modes[sanitized_name] = {
            "priorities": priorities,
            "description": description.strip(),
            "created": datetime.now().isoformat()
        }
        
        # Save to disk
        success = self.save_custom_modes()
        
        if success:
            print(f"✅ Added custom mode: {sanitized_name}")
        
        return success
    
    def delete_mode(self, name):
        """
        Delete a custom ethical mode.
        
        Args:
            name (str): Mode name to delete
        
        Returns:
            bool: True if deleted successfully, False if not found or error
        
        Description:
            Removes mode from dictionary and saves changes to disk.
            Cannot delete built-in modes (safety, efficiency, energy, balanced).
            Safe to call even if mode doesn't exist.
        """
        # Sanitize name
        sanitized_name = name.lower().strip().replace(' ', '_')
        
        # Check if it's a built-in mode
        built_in_modes = ["safety", "efficiency", "energy", "balanced"]
        if sanitized_name in built_in_modes:
            print(f"❌ Cannot delete built-in mode: {sanitized_name}")
            return False
        
        # Check if mode exists
        if sanitized_name not in self.custom_modes:
            print(f"⚠️  Mode not found: {sanitized_name}")
            return False
        
        # Delete mode
        del self.custom_modes[sanitized_name]
        
        # Save to disk
        success = self.save_custom_modes()
        
        if success:
            print(f"🗑️  Deleted custom mode: {sanitized_name}")
        
        return success
    
    def get_mode(self, name):
        """
        Get a specific mode (built-in or custom).
        
        Args:
            name (str): Mode name
        
        Returns:
            dict or None: Mode data or None if not found
        """
        all_modes = self.get_all_modes()
        return all_modes.get(name.lower())
    
    def get_all_modes(self):
        """
        Get all available modes (built-in + custom).
        
        Returns:
            dict: Dictionary mapping mode names to mode data:
                {
                    "mode_name": {
                        "priorities": ["1. ...", "2. ...", "3. ..."],
                        "description": "Mode description",
                        "icon": "🎨"
                    },
                    ...
                }
        
        Description:
            Combines built-in modes (safety, efficiency, energy, balanced)
            with user-created custom modes.
            Custom modes get 🎨 icon, built-in modes get specific icons.
        """
        # Define built-in modes
        built_in_modes = {
            "safety": {
                "priorities": [
                    "1. Human safety is the ABSOLUTE PRIORITY - never compromise safety",
                    "2. Operational efficiency (minimize delivery time)",
                    "3. Energy conservation (battery usage)"
                ],
                "description": "Prioritizes human safety above all other concerns",
                "icon": "🛡️"
            },
            "efficiency": {
                "priorities": [
                    "1. Operational efficiency (minimize delivery time) is the PRIMARY goal",
                    "2. Human safety (maintain reasonable safe distance)",
                    "3. Energy conservation (battery usage)"
                ],
                "description": "Prioritizes speed and operational efficiency",
                "icon": "⚡"
            },
            "energy": {
                "priorities": [
                    "1. Energy conservation (maximize battery life) is CRITICAL",
                    "2. Operational efficiency (minimize delivery time)",
                    "3. Human safety (maintain minimum safe distance)"
                ],
                "description": "Prioritizes battery conservation and energy efficiency",
                "icon": "🔋"
            },
            "balanced": {
                "priorities": [
                    "1. Balance human safety with operational needs",
                    "2. Optimize for efficiency when safety permits",
                    "3. Consider energy conservation as a secondary factor"
                ],
                "description": "Balanced approach considering all factors equally",
                "icon": "⚖️"
            }
        }
        
        # Add custom modes with 🎨 icon
        all_modes = built_in_modes.copy()
        
        for mode_name, mode_data in self.custom_modes.items():
            all_modes[mode_name] = {
                "priorities": mode_data.get("priorities", []),
                "description": mode_data.get("description", "Custom ethical mode"),
                "icon": "🎨",
                "created": mode_data.get("created", "Unknown")
            }
        
        return all_modes
    
    def get_custom_modes_only(self):
        """
        Get only custom modes (excluding built-in).
        
        Returns:
            dict: Dictionary of custom modes only
        """
        return self.custom_modes.copy()
    
    def get_mode_names(self):
        """
        Get list of all mode names.
        
        Returns:
            list: List of mode names (built-in + custom)
        """
        return list(self.get_all_modes().keys())
    
    def get_custom_mode_names(self):
        """
        Get list of custom mode names only.
        
        Returns:
            list: List of custom mode names
        """
        return list(self.custom_modes.keys())
    
    def clear_all_custom_modes(self):
        """
        Clear all custom modes (keeps built-in modes).
        
        Returns:
            bool: True if cleared successfully
        
        Description:
            Removes all custom modes and saves empty state to disk.
            Built-in modes are never affected.
        """
        self.custom_modes = {}
        success = self.save_custom_modes()
        
        if success:
            print("🗑️  Cleared all custom modes")
        
        return success
    
    def export_to_json(self, filepath):
        """
        Export custom modes to JSON file.
        
        Args:
            filepath (str): Path to export file
        
        Returns:
            bool: True if export successful
        
        Description:
            Exports custom modes to human-readable JSON format.
            Useful for sharing modes or backup.
        """
        try:
            import json
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.custom_modes, f, indent=2, ensure_ascii=False)
            
            print(f"📤 Exported custom modes to {filepath}")
            return True
        
        except Exception as e:
            print(f"❌ Error exporting modes: {e}")
            return False
    
    def import_from_json(self, filepath):
        """
        Import custom modes from JSON file.
        
        Args:
            filepath (str): Path to import file
        
        Returns:
            bool: True if import successful
        
        Description:
            Imports custom modes from JSON file.
            Merges with existing custom modes (doesn't replace).
            Validates format before importing.
        """
        try:
            import json
            
            with open(filepath, 'r', encoding='utf-8') as f:
                imported_modes = json.load(f)
            
            # Validate format
            if not isinstance(imported_modes, dict):
                print("❌ Invalid JSON format")
                return False
            
            # Merge imported modes
            for name, data in imported_modes.items():
                if "priorities" in data and isinstance(data["priorities"], list):
                    self.custom_modes[name] = data
            
            # Save merged modes
            success = self.save_custom_modes()
            
            if success:
                print(f"📥 Imported {len(imported_modes)} mode(s) from {filepath}")
            
            return success
        
        except Exception as e:
            print(f"❌ Error importing modes: {e}")
            return False


# ============================================================================
# MAIN GUI CLASS
# ============================================================================
"""
ULTIMATE ETHICAL NAVIGATION GUI - PART 1
=========================================
Initialization and UI Setup Methods
Complete and ready to integrate
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from threading import Thread
import time


class UltimateEthicalNavigationGUI:
    """
    Main GUI application for Ultimate Ethical Navigation System.
    
    PART 1: Initialization and UI Setup
    """
    
    # ========================================================================
    # COLOR PALETTE - PREMIUM DARK THEME
    # ========================================================================
    
    COLORS = {
        # === BACKGROUNDS ===
        'app_bg': '#0d1117',           # Noir GitHub (très élégant)
        'panel_bg': '#161b22',         # Gris ardoise foncé
        'container_bg': '#1f2937',     # Gris charbon
        'input_bg': '#0d1117',         # Noir pour inputs
        'canvas_bg': '#0a0e13',        # Noir profond pour canvas
        
        # === HEADERS (Dégradés visuels) ===
        'header_config': '#6366f1',    # Indigo moderne
        'header_reasoning': '#8b5cf6',  # Violet premium
        'header_prompt': '#f59e0b',    # Ambre doré
        'header_simulation': '#10b981', # Émeraude vif
        
        # === TEXT COLORS ===
        'text_primary': '#f8fafc',     # Blanc cassé (parfait contraste)
        'text_secondary': '#94a3b8',   # Gris bleuté clair
        'text_muted': '#64748b',       # Gris moyen
        'text_accent': '#60a5fa',      # Bleu clair lumineux
        
        # === STATUS COLORS ===
        'success': '#10b981',          # Vert émeraude
        'success_bg': '#064e3b',       # Fond vert foncé
        'error': '#ef4444',            # Rouge vif
        'error_bg': '#7f1d1d',         # Fond rouge foncé
        'warning': '#f59e0b',          # Ambre
        'warning_bg': '#78350f',       # Fond ambre foncé
        'info': '#3b82f6',             # Bleu royal
        'info_bg': '#1e3a8a',          # Fond bleu foncé
        
        # === BUTTONS ===
        'btn_primary': '#6366f1',      # Indigo
        'btn_primary_hover': '#4f46e5',
        'btn_primary_text': '#ffffff',
        
        'btn_success': '#10b981',      # Émeraude
        'btn_success_hover': '#059669',
        'btn_success_text': '#ffffff',
        
        'btn_danger': '#ef4444',       # Rouge
        'btn_danger_hover': '#dc2626',
        'btn_danger_text': '#ffffff',
        
        'btn_warning': '#f59e0b',      # Ambre
        'btn_warning_hover': '#d97706',
        'btn_warning_text': '#000000',  # Noir pour contraste sur jaune
        
        'btn_secondary': '#475569',    # Gris ardoise
        'btn_secondary_hover': '#334155',
        'btn_secondary_text': '#ffffff',
        
        # === BORDERS ===
        'border_light': '#374151',     # Gris moyen pour bordures
        'border_accent': '#6366f1',    # Indigo pour focus
        'border_success': '#10b981',   # Vert pour succès
        
        # === SIMULATION COLORS ===
        'sim_completed': '#10b981',    # Vert émeraude (segments faits)
        'sim_current': '#f59e0b',      # Ambre (segment actuel)
        'sim_future': '#475569',       # Gris ardoise (segments futurs)
        'sim_robot': '#ef4444',        # Rouge vif (robot)
        'sim_robot_glow': '#fca5a5',   # Rose clair (glow robot)
        'sim_path_a': '#3b82f6',       # Bleu
        'sim_path_b': '#8b5cf6',       # Violet
        'sim_path_c': '#f59e0b',       # Ambre
        'sim_path_d': '#10b981',       # Émeraude
        'sim_path_e': '#ec4899',       # Rose
        'sim_path_f': '#14b8a6',       # Sarcelle
        
        # === SPECIAL EFFECTS ===
        'glow_green': '#34d399',       # Vert néon
        'glow_blue': '#60a5fa',        # Bleu néon
        'glow_purple': '#a78bfa',      # Violet néon
        'highlight': '#fbbf24',        # Or pour highlights
        
        # === GRID & CANVAS ===
        'grid': '#1f2937',             # Gris pour grille
        'grid_accent': '#374151',      # Gris plus clair pour axes
    }
    
    # ========================================================================
    # FONTS
    # ========================================================================
    
    FONTS = {
        'title': ('Segoe UI', 22, 'bold'),
        'subtitle': ('Segoe UI', 10, 'italic'),
        'header': ('Segoe UI', 13, 'bold'),
        'section': ('Segoe UI', 11, 'bold'),
        'body': ('Segoe UI', 10),
        'button': ('Segoe UI', 10, 'bold'),
        'button_large': ('Segoe UI', 12, 'bold'),
        'code': ('Consolas', 9),
        'code_large': ('Consolas', 10),
    }


    def __init__(self, root, modes_manager, get_robots_func, get_paths_func):
        """
        Initialize the GUI application.
        
        Args:
            root (tk.Tk): Main tkinter window
            modes_manager (CustomModesManager): Ethical modes manager
            get_robots_func (callable): Function to get robots from FIWARE
            get_paths_func (callable): Function to get paths from FIWARE
        """
        self.root = root
        self.modes_manager = modes_manager
        self.get_robots_func = get_robots_func
        self.get_paths_func = get_paths_func
        
        # Window setup
        self.root.title("🚀 Ultimate Ethical Navigation System")
        self.root.geometry("1600x950")
        self.root.configure(bg=self.COLORS['app_bg'])
        
        # State variables - Data
        self.robots = []
        self.paths = []
        self.selected_robot = None
        self.selected_paths = []
        self.decision = None
        
        # State variables - Simulation
        self.simulation_running = False
        self.paused = False
        self.current_waypoint_idx = 0
        self.current_display_pos = None
        self.chosen_path = None
        self.waypoints = []
        
        # State variables - LLM
        self.inference_time = 0
        self.llm_response_raw = ""
        self.current_prompt = ""
        
        # UI variables
        self.robot_var = tk.StringVar()
        self.path_vars = {}
        self.robot_info_labels = {}
        self.ethical_mode = tk.StringVar(value="safety")
        self.prompt_tab_var = tk.StringVar(value="prompt")
        
        # Load initial data
        self.load_fiware_data()
        
        # Setup UI
        self.setup_ui()
        
        # Initial canvas draw
        self.root.after(100, self.draw_canvas)
        
        print("✅ GUI initialized successfully")
    
    def load_fiware_data(self):
        """Load robots and paths from FIWARE."""
        print("\n🔄 Loading FIWARE data...")
        self.robots = self.get_robots_func()
        self.paths = self.get_paths_func()
        
        print(f"   Found {len(self.robots)} robot(s)")
        print(f"   Found {len(self.paths)} path(s)")
        
        if not self.robots:
            print("   ⚠️  No robots found - check FIWARE connection")
        if not self.paths:
            print("   ⚠️  No paths found - check FIWARE entities")
    
    def setup_ui(self):
        """Setup the complete user interface with resizable panels."""
        
        # ====================================================================
        # TITLE BAR
        # ====================================================================
        title_frame = tk.Frame(self.root, bg=self.COLORS['app_bg'], height=80)
        title_frame.pack(fill=tk.X, side=tk.TOP)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="🚀 ULTIMATE ETHICAL NAVIGATION SYSTEM",
            font=self.FONTS['title'],
            bg=self.COLORS['app_bg'],
            fg=self.COLORS['glow_blue']  # ← Bleu néon brillant
        )
        title_label.pack(side=tk.LEFT, padx=30, pady=20)
        
        subtitle = tk.Label(
            title_frame,
            text="AI-Powered Autonomous Decision Making",
            font=self.FONTS['subtitle'],
            bg=self.COLORS['app_bg'],
            fg=self.COLORS['text_secondary']  # ← Gris bleuté
        )
        subtitle.pack(side=tk.LEFT, padx=5, pady=20)
        
        # Status indicator - Style moderne
        self.connection_status = tk.Label(
            title_frame,
            text="⚡ LIVE",
            font=('Segoe UI', 11, 'bold'),
            bg=self.COLORS['success'],      # ← Vert émeraude
            fg=self.COLORS['text_primary'], # ← Blanc cassé
            padx=15,
            pady=8,
            relief=tk.FLAT
        )
        self.connection_status.pack(side=tk.RIGHT, padx=30, pady=20)
        # ====================================================================
        # MAIN CONTAINER WITH PANEDWINDOW
        # ====================================================================
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # LEFT: Configuration Panel
        left_frame = tk.Frame(main_paned, bg="#1e1e1e", relief=tk.RAISED, bd=2)
        main_paned.add(left_frame, weight=1)
        self.setup_configuration_panel(left_frame)
        
        # CENTER: Vertical PanedWindow for Reasoning & Prompt
        center_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
        main_paned.add(center_paned, weight=2)
        
        # Reasoning panel
        reasoning_frame = tk.Frame(center_paned, bg="#1e1e1e", relief=tk.RAISED, bd=2)
        center_paned.add(reasoning_frame, weight=1)
        self.setup_reasoning_panel(reasoning_frame)
        
        # Prompt panel
        prompt_frame = tk.Frame(center_paned, bg="#1e1e1e", relief=tk.RAISED, bd=2)
        center_paned.add(prompt_frame, weight=1)
        self.setup_prompt_panel(prompt_frame)
        
        # RIGHT: Simulation Panel
        right_frame = tk.Frame(main_paned, bg="#1e1e1e", relief=tk.RAISED, bd=2)
        main_paned.add(right_frame, weight=2)
        self.setup_simulation_panel(right_frame)
    
    def setup_configuration_panel(self, parent):
        """Setup left configuration panel."""
        
        # Header
        header = tk.Frame(parent, bg=self.COLORS['header_config'], height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="⚙️ CONFIGURATION",
            font=self.FONTS['header'],
            bg=self.COLORS['header_config'],
            fg=self.COLORS['text_primary']  # ← Blanc cassé
        ).pack(pady=15)
        
        # Scrollable content
        canvas_container = tk.Frame(parent, bg=self.COLORS['panel_bg'])
        canvas_container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(
            canvas_container, 
            bg=self.COLORS['panel_bg'],
            highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(canvas_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.COLORS['panel_bg'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        content = scrollable_frame
        
        
        # ================================================================
        # 1. ROBOT SELECTION
        # ================================================================
        
        tk.Label(
            content, 
            text="1️⃣ SELECT ROBOT", 
            font=self.FONTS['section'],
            bg=self.COLORS['panel_bg'],
            fg=self.COLORS['text_accent']  # ← Bleu lumineux
        ).pack(anchor=tk.W, pady=(15,8), padx=15)
        self.robot_info_labels = {}
        robot_container = tk.Frame(
            content, 
            bg=self.COLORS['container_bg'],
            relief=tk.FLAT,
            bd=0
        )
        robot_container.pack(fill=tk.X, pady=8, padx=15)
        if self.robots:
            for robot in self.robots:
                rb_frame = tk.Frame(robot_container, bg=self.COLORS['container_bg'])
                rb_frame.pack(fill=tk.X, padx=10, pady=6)
                
                rb = tk.Radiobutton(
                    rb_frame,
                    text=f"🤖 {robot['name']}",
                    variable=self.robot_var,
                    value=robot['id'],
                    bg=self.COLORS['container_bg'],
                    fg=self.COLORS['text_primary'],  # ← Blanc cassé
                    font=self.FONTS['body'],
                    activebackground=self.COLORS['container_bg'],
                    activeforeground=self.COLORS['text_accent'],
                    selectcolor=self.COLORS['border_accent'],  # ← Indigo
                    command=self.on_robot_changed
                )
                rb.pack(anchor=tk.W)
                
                info_label = tk.Label(
                    rb_frame,
                    text=f"   🔋 {robot['battery']}% | 📍 [{robot['position'][0]:.1f}, {robot['position'][1]:.1f}]",
                    font=self.FONTS['code'],
                    bg=self.COLORS['container_bg'],
                    fg=self.COLORS['text_secondary']  # ← Gris bleuté
                )
                info_label.pack(anchor=tk.W, padx=25)
                
                self.robot_info_labels[robot['id']] = info_label
        else:
            tk.Label(
                robot_container,
                text="⚠️ No robots found",
                bg="#2a2a2a",
                fg="#ff6b6b",
                font=("Arial", 10)
            ).pack(pady=15)
        
        # ================================================================
        # 2. PATH SELECTION
        # ================================================================
        tk.Label(
            content, 
            text="2️⃣ SELECT PATHS (2+)", 
            font=self.FONTS['section'],
            bg=self.COLORS['panel_bg'],
            fg=self.COLORS['text_accent']
        ).pack(anchor=tk.W, pady=(25,8), padx=15)
        
        path_container = tk.Frame(
            content, 
            bg=self.COLORS['container_bg'],
            relief=tk.FLAT
        )
        path_container.pack(fill=tk.X, pady=8, padx=15)

        if self.paths:
            for path in self.paths:
                self.path_vars[path['id']] = tk.BooleanVar()
                
                cb_frame = tk.Frame(path_container, bg=self.COLORS['container_bg'])
                cb_frame.pack(fill=tk.X, padx=10, pady=6)
                
                cb = tk.Checkbutton(
                    cb_frame,
                    text=f"🛣️ {path['name']}",
                    variable=self.path_vars[path['id']],
                    bg=self.COLORS['container_bg'],
                    fg=self.COLORS['text_primary'],
                    font=self.FONTS['body'],
                    activebackground=self.COLORS['container_bg'],
                    selectcolor=self.COLORS['btn_danger'],  # ← Rouge vif
                    command=self.on_path_changed
                )
                cb.pack(anchor=tk.W)
                
                info_label = tk.Label(
                    cb_frame,
                    text=f"   📏 {path['distance']}m | ⏱️ {path['duration']}s | 👥 {len(path['detected_humans'])} humans",
                    font=self.FONTS['code'],
                    bg=self.COLORS['container_bg'],
                    fg=self.COLORS['text_secondary']
                )
                info_label.pack(anchor=tk.W, padx=25)
        else:
            tk.Label(
                path_container,
                text="⚠️ No paths found",
                bg="#2a2a2a",
                fg="#ff6b6b",
                font=("Arial", 10)
            ).pack(pady=15)
        
        # Selected paths indicator
        self.selected_paths_label = tk.Label(
            content,
            text="Selected: None",
            font=self.FONTS['body'],
            bg=self.COLORS['warning_bg'],    # ← Fond ambre foncé
            fg=self.COLORS['warning'],        # ← Texte ambre
            relief=tk.FLAT,
            padx=10,
            pady=8
        )
        self.selected_paths_label.pack(fill=tk.X, pady=(8,0), padx=15)
        
        # ================================================================
        # 3. ETHICAL MODE SELECTION
        # ================================================================
        tk.Label(
            content, 
            text="3️⃣ ETHICAL MODE", 
            font=self.FONTS['section'],
            bg=self.COLORS['panel_bg'],
            fg=self.COLORS['text_accent']
        ).pack(anchor=tk.W, pady=(25,8), padx=15)
        
        mode_frame = tk.Frame(content, bg=self.COLORS['container_bg'], relief=tk.FLAT)
        mode_frame.pack(fill=tk.X, pady=8, padx=15)
        
        self.ethical_mode = tk.StringVar(value="safety")
        
        modes = [
            ("🛡️ Safety First", "safety", self.COLORS['success']),
            ("⚡ Efficiency First", "efficiency", self.COLORS['info']),
            ("🔋 Energy First", "energy", self.COLORS['warning']),
            ("⚖️ Balanced", "balanced", self.COLORS['glow_purple'])
        ]

        for text, mode, color in modes:
            rb = tk.Radiobutton(
                mode_frame,
                text=text,
                variable=self.ethical_mode,
                value=mode,
                bg=self.COLORS['container_bg'],
                fg=self.COLORS['text_primary'],
                font=self.FONTS['body'],
                activebackground=self.COLORS['container_bg'],
                selectcolor=color,
                indicatoron=True,
                command=self.on_mode_changed
            )
            rb.pack(anchor=tk.W, padx=15, pady=8)    
            
        
        # Custom mode management buttons
        custom_btn_frame = tk.Frame(mode_frame, bg="#2a2a2a")
        custom_btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(
            custom_btn_frame,
            text="➕ Create Custom",
            command=self.create_custom_mode,
            bg="#00cc66",
            fg="white",
            font=("Arial", 9, "bold"),
            relief=tk.RAISED,
            bd=2,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        
        tk.Button(
            custom_btn_frame,
            text="🗑️ Delete Custom",
            command=self.delete_custom_mode,
            bg="#ff6b6b",
            fg="white",
            font=("Arial", 9, "bold"),
            relief=tk.RAISED,
            bd=2,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        
        # ================================================================
        # 4. CUSTOM INSTRUCTIONS
        # ================================================================
        tk.Label(
            content, 
            text="4️⃣ CUSTOM INSTRUCTIONS", 
            font=self.FONTS['section'],
            bg=self.COLORS['panel_bg'],
            fg=self.COLORS['text_accent']
        ).pack(anchor=tk.W, pady=(25,8), padx=15)
        
        instr_frame = tk.Frame(content, relief=tk.FLAT, bg=self.COLORS['container_bg'])
        instr_frame.pack(fill=tk.X, pady=8, padx=15)
        
        self.custom_instructions = scrolledtext.ScrolledText(
            instr_frame,
            height=4,
            wrap=tk.WORD,
            font=self.FONTS['code'],
            bg=self.COLORS['input_bg'],      # ← Noir pour input
            fg=self.COLORS['text_primary'],  # ← Blanc cassé
            insertbackground=self.COLORS['text_accent'],  # ← Curseur bleu
            relief=tk.FLAT,
            padx=10,
            pady=8
        )
        self.custom_instructions.pack(fill=tk.X, padx=5, pady=5)
        self.custom_instructions.insert(1.0, "Add specific requirements here...")
        
        tk.Button(
            content,
            text="🗑️ Clear",
            command=lambda: self.custom_instructions.delete(1.0, tk.END),
            bg=self.COLORS['btn_secondary'],
            fg=self.COLORS['btn_secondary_text'],
            font=self.FONTS['body'],
            relief=tk.FLAT,
            cursor="hand2",
            activebackground=self.COLORS['btn_secondary_hover'],
            pady=8
        ).pack(fill=tk.X, pady=(5,0), padx=15)
        
        # ================================================================
        # ACTION BUTTONS
        # ================================================================
        action_frame = tk.Frame(content, bg=self.COLORS['panel_bg'])
        action_frame.pack(fill=tk.X, pady=25, padx=15)
        
        # ONE-CLICK: Decide & Execute - Style premium
        self.quick_execute_btn = tk.Button(
            action_frame,
            text="⚡ DECIDE & EXECUTE",
            command=self.quick_decide_and_execute,
            font=self.FONTS['button_large'],
            bg=self.COLORS['btn_danger'],      # ← Rouge vif
            fg=self.COLORS['btn_danger_text'], # ← Blanc
            activebackground=self.COLORS['btn_danger_hover'],
            activeforeground=self.COLORS['btn_danger_text'],
            relief=tk.FLAT,
            cursor="hand2",
            height=2,
            state=tk.DISABLED
        )
        self.quick_execute_btn.pack(fill=tk.X, pady=(0, 10))
        
        # Regular: Just decide
        self.start_btn = tk.Button(
            action_frame,
            text="🧠 ANALYZE & DECIDE",
            command=self.start_reasoning,
            font=self.FONTS['button_large'],
            bg=self.COLORS['btn_success'],      # ← Vert émeraude
            fg=self.COLORS['btn_success_text'], # ← Blanc
            activebackground=self.COLORS['btn_success_hover'],
            activeforeground=self.COLORS['btn_success_text'],
            relief=tk.FLAT,
            cursor="hand2",
            height=2,
            state=tk.DISABLED
        )
        self.start_btn.pack(fill=tk.X, pady=(0, 15))
        
        # ================================================================
        # UTILITY BUTTONS
        # ================================================================
        util_frame = tk.Frame(content, bg=self.COLORS['panel_bg'])
        util_frame.pack(fill=tk.X, padx=15)
        
        tk.Button(
            util_frame,
            text="🔄 Refresh Data",
            command=self.refresh_fiware_data,
            bg=self.COLORS['btn_primary'],
            fg=self.COLORS['btn_primary_text'],
            font=self.FONTS['body'],
            relief=tk.FLAT,
            cursor="hand2",
            pady=10
        ).pack(fill=tk.X, pady=5)
        
        tk.Button(
            util_frame,
            text="🔍 Test Connection",
            command=self.test_fiware_connection,
            bg=self.COLORS['btn_secondary'],
            fg=self.COLORS['btn_secondary_text'],
            font=self.FONTS['body'],
            relief=tk.FLAT,
            cursor="hand2",
            pady=10
        ).pack(fill=tk.X, pady=5)
        
        # Status indicator
        self.config_status = tk.Label(
            content,
            text="⚠️ Select robot and at least 2 paths",
            font=self.FONTS['body'],
            bg=self.COLORS['warning_bg'],
            fg=self.COLORS['warning'],
            relief=tk.FLAT,
            padx=12,
            pady=12
        )
        self.config_status.pack(fill=tk.X, pady=(20,15), padx=15)
    
    
    def _create_section_header(self, parent, text):
        """Create a styled section header."""
        tk.Label(
            parent,
            text=text,
            font=("Arial", 11, "bold"),
            bg="#1e1e1e",
            fg="#00ff00",
            anchor=tk.W
        ).pack(anchor=tk.W, pady=(15,5), padx=10)
    
    def setup_reasoning_panel(self, parent):
        """Setup center reasoning panel."""
        
        # Header
        header = tk.Frame(parent, bg="#cc0066", height=45)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="🧠 ETHICAL REASONING",
            font=("Arial", 13, "bold"),
            bg="#cc0066",
            fg="white"
        ).pack(pady=12)
        
        content = tk.Frame(parent, bg="#1e1e1e")
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Status with metrics
        status_frame = tk.Frame(content, bg="#2a2a2a", relief=tk.GROOVE, bd=2)
        status_frame.pack(fill=tk.X, pady=(0,10))
        
        status_container = tk.Frame(status_frame, bg="#2a2a2a")
        status_container.pack(fill=tk.X, padx=10, pady=10)
        
        self.status_label = tk.Label(
            status_container,
            text="⏳ Waiting for configuration...",
            font=("Arial", 10, "bold"),
            bg="#2a2a2a",
            fg="white",
            anchor=tk.W
        )
        self.status_label.pack(fill=tk.X)
        
        self.metrics_label = tk.Label(
            status_container,
            text="",
            font=("Courier", 9),
            bg="#2a2a2a",
            fg="#00ff00",
            anchor=tk.W
        )
        self.metrics_label.pack(fill=tk.X, pady=(5,0))
        
        # Reasoning Log
        tk.Label(
            content,
            text="📋 Reasoning Process:",
            font=("Arial", 10, "bold"),
            bg="#1e1e1e",
            fg="white"
        ).pack(anchor=tk.W, pady=(5,2))
        
        self.reasoning_log = scrolledtext.ScrolledText(
            content,
            height=10,
            wrap=tk.WORD,
            font=("Courier", 9),
            bg="#0a0a0a",
            fg="#00ff00",
            insertbackground="white"
        )
        self.reasoning_log.pack(fill=tk.BOTH, expand=True, pady=5)
        self.reasoning_log.config(state=tk.DISABLED)
        
        # Decision Display
        tk.Label(
            content,
            text="🎯 LLM Decision:",
            font=("Arial", 10, "bold"),
            bg="#1e1e1e",
            fg="white"
        ).pack(anchor=tk.W, pady=(10,2))
        
        decision_frame = tk.Frame(content, bg="#00332a", relief=tk.GROOVE, bd=3)
        decision_frame.pack(fill=tk.X, pady=5)
        
        self.decision_text = tk.Text(
            decision_frame,
            height=6,
            wrap=tk.WORD,
            font=("Arial", 10),
            bg="#00332a",
            fg="#00ff88",
            relief=tk.FLAT
        )
        self.decision_text.pack(fill=tk.X, padx=10, pady=10)
        self.decision_text.config(state=tk.DISABLED)
        
        # Action Buttons
        button_frame = tk.Frame(content, bg="#1e1e1e")
        button_frame.pack(fill=tk.X, pady=10)
        
        self.apply_btn = tk.Button(
            button_frame,
            text="✅ APPLY & SIMULATE",
            command=self.apply_decision,
            bg="#00cc66",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.RAISED,
            bd=3,
            state=tk.DISABLED,
            cursor="hand2"
        )
        self.apply_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        tk.Button(
            button_frame,
            text="💾 Save to FIWARE",
            command=self.save_decision_to_fiware,
            bg="#3498db",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.RAISED,
            bd=3,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
    
    def setup_prompt_panel(self, parent):
        """Setup prompt viewer panel."""
        
        # Header
        header = tk.Frame(parent, bg="#ff9800", height=45)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="📝 PROMPT VIEWER & EDITOR",
            font=("Arial", 13, "bold"),
            bg="#ff9800",
            fg="white"
        ).pack(pady=12)
        
        content = tk.Frame(parent, bg="#1e1e1e")
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tabs
        tab_frame = tk.Frame(content, bg="#1e1e1e")
        tab_frame.pack(fill=tk.X, pady=(0,5))
        
        tk.Radiobutton(
            tab_frame,
            text="📝 Current Prompt",
            variable=self.prompt_tab_var,
            value="prompt",
            bg="#1e1e1e",
            fg="white",
            font=("Arial", 10, "bold"),
            activebackground="#1e1e1e",
            selectcolor="#ff9800",
            command=self.switch_prompt_tab
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Radiobutton(
            tab_frame,
            text="💬 LLM Response",
            variable=self.prompt_tab_var,
            value="response",
            bg="#1e1e1e",
            fg="white",
            font=("Arial", 10, "bold"),
            activebackground="#1e1e1e",
            selectcolor="#ff9800",
            command=self.switch_prompt_tab
        ).pack(side=tk.LEFT, padx=5)
        
        # Text display
        self.prompt_text = scrolledtext.ScrolledText(
            content,
            wrap=tk.WORD,
            font=("Courier", 9),
            bg="#0a0a0a",
            fg="#ffaa00",
            insertbackground="white"
        )
        self.prompt_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Buttons
        btn_frame = tk.Frame(content, bg="#1e1e1e")
        btn_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(
            btn_frame,
            text="🔄 Update Prompt",
            command=self.update_current_prompt,
            bg="#00cc66",
            fg="white",
            font=("Arial", 9, "bold"),
            relief=tk.RAISED,
            bd=2,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        
        tk.Button(
            btn_frame,
            text="📋 Copy",
            command=self.copy_prompt,
            bg="#3498db",
            fg="white",
            font=("Arial", 9, "bold"),
            relief=tk.RAISED,
            bd=2,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
    
    def setup_simulation_panel(self, parent):
        """Setup simulation panel."""
        
        # Header
        header = tk.Frame(parent, bg="#00cc66", height=45)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="📍 LIVE SIMULATION",
            font=("Arial", 13, "bold"),
            bg="#00cc66",
            fg="white"
        ).pack(pady=12)
        
        content = tk.Frame(parent, bg="#1e1e1e")
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Robot Status
        status_frame = tk.Frame(content, bg="#2a2a2a", relief=tk.GROOVE, bd=2)
        status_frame.pack(fill=tk.X, pady=(0,10))
        
        tk.Label(
            status_frame,
            text="🤖 Robot Status:",
            font=("Arial", 10, "bold"),
            bg="#2a2a2a",
            fg="white"
        ).pack(anchor=tk.W, padx=8, pady=(8,2))
        
        self.robot_status_label = tk.Label(
            status_frame,
            text="No robot selected",
            font=("Courier", 9),
            bg="#2a2a2a",
            fg="#00ff00",
            anchor=tk.W,
            justify=tk.LEFT
        )
        self.robot_status_label.pack(fill=tk.X, padx=12, pady=(0,8))
        
        # Progress bar
        self.progress_frame = tk.Frame(content, bg="#1e1e1e")
        self.progress_label = tk.Label(
            self.progress_frame,
            text="Progress: 0%",
            font=("Arial", 9, "bold"),
            bg="#1e1e1e",
            fg="white"
        )
        self.progress_label.pack(anchor=tk.W)
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            mode='determinate',
            length=300
        )
        self.progress_bar.pack(fill=tk.X, pady=2)
        
        # Canvas
        self.canvas = tk.Canvas(
            content,
            bg="#0a0a0a",
            highlightthickness=2,
            highlightbackground="#00ff00"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=5)
        self.canvas.bind('<Configure>', lambda e: self.draw_canvas())
        
        # Control buttons
        control_frame = tk.Frame(content, bg="#1e1e1e")
        control_frame.pack(fill=tk.X, pady=10)
        
        self.pause_btn = tk.Button(
            control_frame, text="⏸️ Pause", command=self.pause_simulation,
            bg="#f39c12", fg="white", font=("Arial", 9, "bold"),
            relief=tk.RAISED, bd=2, state=tk.DISABLED, cursor="hand2"
        )
        self.pause_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        
        self.resume_btn = tk.Button(
            control_frame, text="▶️ Resume", command=self.resume_simulation,
            bg="#00cc66", fg="white", font=("Arial", 9, "bold"),
            relief=tk.RAISED, bd=2, state=tk.DISABLED, cursor="hand2"
        )
        self.resume_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        
        self.reset_btn = tk.Button(
            control_frame, text="🔄 Reset", command=self.reset_simulation,
            bg="#e74c3c", fg="white", font=("Arial", 9, "bold"),
            relief=tk.RAISED, bd=2, state=tk.DISABLED, cursor="hand2"
        )
        self.reset_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        
        self.origin_btn = tk.Button(
            control_frame, text="🏠 Return to Origin", command=self.return_to_origin,
            bg="#9b59b6", fg="white", font=("Arial", 9, "bold"),
            relief=tk.RAISED, bd=2, state=tk.DISABLED, cursor="hand2"
        )
        self.origin_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        
        # Final Status
        self.final_status_frame = tk.Frame(content, bg="#00cc66", relief=tk.GROOVE, bd=3)
        self.final_status_label = tk.Label(
            self.final_status_frame, text="", font=("Arial", 11, "bold"),
            bg="#00cc66", fg="white"
        )
        self.final_status_label.pack(padx=15, pady=15)
    
    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================
    
    def on_robot_changed(self):
        """Handle robot selection change."""
        robot_id = self.robot_var.get()
        self.selected_robot = next((r for r in self.robots if r['id'] == robot_id), None)
        
        if self.selected_robot:
            self.update_robot_status_display()
            self.draw_canvas()
            self.update_current_prompt()
        
        self.update_config_status()
    
    def on_path_changed(self):
        """Handle path selection change."""
        self.selected_paths = [
            path for path in self.paths 
            if self.path_vars[path['id']].get()
        ]
        
        if self.selected_paths:
            names = [p['name'] for p in self.selected_paths]
            self.selected_paths_label.config(
                text=f"✅ Selected ({len(self.selected_paths)}): {', '.join(names)}",
                bg="#00cc66" if len(self.selected_paths) >= 2 else "#ffc107",
                fg="white" if len(self.selected_paths) >= 2 else "#000000"
            )
        else:
            self.selected_paths_label.config(
                text="Selected: None", bg="#ffc107", fg="#000000"
            )
        
        self.draw_canvas()
        self.update_config_status()
        self.update_current_prompt()
    
    def on_mode_changed(self):
        """Handle ethical mode change."""
        self.update_current_prompt()
    
    def update_config_status(self):
        """Update configuration status indicator."""
        if self.selected_robot and len(self.selected_paths) >= 2:
            self.config_status.config(
                text=f"✅ Ready: {self.selected_robot['name']} with {len(self.selected_paths)} paths",
                bg="#00cc66", fg="white"
            )
            self.start_btn.config(state=tk.NORMAL)
            self.quick_execute_btn.config(state=tk.NORMAL)
        else:
            missing = []
            if not self.selected_robot:
                missing.append("robot")
            if len(self.selected_paths) < 2:
                missing.append(f"{2-len(self.selected_paths)} more path(s)")
            
            self.config_status.config(
                text=f"⚠️ Need: {', '.join(missing)}",
                bg="#ffc107", fg="#000000"
            )
            self.start_btn.config(state=tk.DISABLED)
            self.quick_execute_btn.config(state=tk.DISABLED)
    
    # ========================================================================
    # CUSTOM MODE MANAGEMENT
    # ========================================================================
    
    def create_custom_mode(self):
        """Open dialog to create new custom ethical mode."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Create Custom Ethical Mode")
        dialog.geometry("600x500")
        dialog.configure(bg="#1e1e1e")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog, text="🎨 Create Custom Ethical Mode",
            font=("Arial", 14, "bold"), bg="#1e1e1e", fg="#00ff00"
        ).pack(pady=15)
        
        # Name
        name_frame = tk.Frame(dialog, bg="#1e1e1e")
        name_frame.pack(fill=tk.X, padx=20, pady=10)
        tk.Label(name_frame, text="Mode Name:", font=("Arial", 10, "bold"),
                bg="#1e1e1e", fg="white").pack(anchor=tk.W)
        name_entry = tk.Entry(name_frame, font=("Arial", 11), bg="#2a2a2a",
                             fg="white", insertbackground="white")
        name_entry.pack(fill=tk.X, pady=5)
        
        # Description
        desc_frame = tk.Frame(dialog, bg="#1e1e1e")
        desc_frame.pack(fill=tk.X, padx=20, pady=10)
        tk.Label(desc_frame, text="Description:", font=("Arial", 10, "bold"),
                bg="#1e1e1e", fg="white").pack(anchor=tk.W)
        desc_entry = tk.Entry(desc_frame, font=("Arial", 10), bg="#2a2a2a",
                             fg="white", insertbackground="white")
        desc_entry.pack(fill=tk.X, pady=5)
        
        # Base mode selection
        base_frame = tk.Frame(dialog, bg="#1e1e1e")
        base_frame.pack(fill=tk.X, padx=20, pady=10)
        tk.Label(base_frame, text="Base on existing mode:", font=("Arial", 10, "bold"),
                bg="#1e1e1e", fg="white").pack(anchor=tk.W)
        
        base_var = tk.StringVar(value="safety")
        all_modes = self.modes_manager.get_all_modes()
        for mode_name in all_modes.keys():
            tk.Radiobutton(
                base_frame, text=mode_name.replace('_', ' ').title(),
                variable=base_var, value=mode_name, bg="#1e1e1e", fg="white",
                font=("Arial", 9), activebackground="#1e1e1e", selectcolor="#00ff00"
            ).pack(anchor=tk.W, padx=20)
        
        # Priorities editor
        priorities_frame = tk.Frame(dialog, bg="#1e1e1e")
        priorities_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        tk.Label(priorities_frame, text="Edit Priorities:", font=("Arial", 10, "bold"),
                bg="#1e1e1e", fg="white").pack(anchor=tk.W)
        
        priorities_text = scrolledtext.ScrolledText(
            priorities_frame, height=8, wrap=tk.WORD, font=("Courier", 9),
            bg="#2a2a2a", fg="#00ff00", insertbackground="white"
        )
        priorities_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        def load_base_mode():
            base_mode = base_var.get()
            mode_data = all_modes.get(base_mode, {})
            priorities = mode_data.get("priorities", [])
            priorities_text.delete(1.0, tk.END)
            priorities_text.insert(1.0, "\n".join(priorities))
        
        load_base_mode()
        base_var.trace('w', lambda *args: load_base_mode())
        
        # Save button
        def save_mode():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("Warning", "Please enter a mode name!")
                return
            
            name = name.lower().replace(' ', '_')
            if name in ["safety", "efficiency", "energy", "balanced"]:
                messagebox.showwarning("Warning", "Cannot override built-in modes!")
                return
            
            description = desc_entry.get().strip()
            priorities_raw = priorities_text.get(1.0, tk.END).strip()
            priorities = [p.strip() for p in priorities_raw.split('\n') if p.strip()]
            
            self.modes_manager.add_mode(name, priorities, description)
            messagebox.showinfo("Success", f"✅ Custom mode '{name}' created!")
            dialog.destroy()
            self.log_reasoning(f"\n🎨 Custom mode created: {name}")
        
        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        tk.Button(btn_frame, text="💾 Save Mode", command=save_mode,
                 bg="#00cc66", fg="white", font=("Arial", 10, "bold"),
                 relief=tk.RAISED, bd=2, cursor="hand2"
        ).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        tk.Button(btn_frame, text="❌ Cancel", command=dialog.destroy,
                 bg="#e74c3c", fg="white", font=("Arial", 10, "bold"),
                 relief=tk.RAISED, bd=2, cursor="hand2"
        ).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
    
    def delete_custom_mode(self):
        """Open dialog to delete custom mode."""
        custom_modes = {k: v for k, v in self.modes_manager.custom_modes.items()}
        
        if not custom_modes:
            messagebox.showinfo("Info", "No custom modes to delete!")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Delete Custom Mode")
        dialog.geometry("400x300")
        dialog.configure(bg="#1e1e1e")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="🗑️ Select mode to delete:",
                font=("Arial", 12, "bold"), bg="#1e1e1e", fg="#ff6b6b"
        ).pack(pady=15)
        
        listbox = tk.Listbox(dialog, font=("Arial", 10), bg="#2a2a2a", fg="white",
                            selectbackground="#ff6b6b", selectforeground="white")
        listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        for mode_name in custom_modes.keys():
            listbox.insert(tk.END, mode_name)
        
        def delete_selected():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a mode!")
                return
            
            mode_name = listbox.get(selection[0])
            if messagebox.askyesno("Confirm", f"Delete mode '{mode_name}'?"):
                self.modes_manager.delete_mode(mode_name)
                messagebox.showinfo("Success", f"✅ Mode '{mode_name}' deleted!")
                dialog.destroy()
                self.log_reasoning(f"\n🗑️ Custom mode deleted: {mode_name}")
        
        tk.Button(dialog, text="🗑️ Delete Selected", command=delete_selected,
                 bg="#ff6b6b", fg="white", font=("Arial", 10, "bold"),
                 relief=tk.RAISED, bd=2, cursor="hand2"
        ).pack(pady=10)
    
    # ========================================================================
    # PROMPT MANAGEMENT
    # ========================================================================
    
    def switch_prompt_tab(self):
        """Switch between prompt and response tabs."""
        if self.prompt_tab_var.get() == "prompt":
            self.prompt_text.delete(1.0, tk.END)
            if self.current_prompt:
                self.prompt_text.insert(1.0, self.current_prompt)
            else:
                self.prompt_text.insert(1.0, "No prompt generated yet. Configure and click 'ANALYZE & DECIDE'.")
        else:
            self.prompt_text.delete(1.0, tk.END)
            if self.llm_response_raw:
                self.prompt_text.insert(1.0, self.llm_response_raw)
            else:
                self.prompt_text.insert(1.0, "No LLM response yet. Run reasoning first.")
    
    def update_current_prompt(self):
        """Update the current prompt preview."""
        if not self.selected_robot or not self.selected_paths:
            return
        
        ethical_mode = self.ethical_mode.get()
        custom_inst = self.custom_instructions.get(1.0, tk.END).strip()
        if "Add specific" in custom_inst or "Example:" in custom_inst:
            custom_inst = ""
        
        self.current_prompt = build_custom_prompt(
            self.selected_robot, self.selected_paths,
            ethical_mode, custom_inst, self.modes_manager
        )
        
        if self.prompt_tab_var.get() == "prompt":
            self.prompt_text.delete(1.0, tk.END)
            self.prompt_text.insert(1.0, self.current_prompt)
    
    def copy_prompt(self):
        """Copy prompt to clipboard."""
        text = self.prompt_text.get(1.0, tk.END).strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Copied", "✅ Content copied to clipboard!")
    
    # ========================================================================
    # CONNECTION TESTING
    # ========================================================================
    
    def test_fiware_connection(self):
        """Test FIWARE connection and show diagnostic."""
        
        diagnostic = test_fiware_connection()
        
        diag_text = "🔍 FIWARE DIAGNOSTIC\n" + "="*60 + "\n\n"
        
        if diagnostic["connected"]:
            diag_text += "✅ FIWARE is running\n"
            diag_text += f"   Robots found: {diagnostic['entities_count']['robots']}\n"
            diag_text += f"   Paths found: {diagnostic['entities_count']['paths']}\n"
        else:
            diag_text += f"❌ Connection failed\n"
            diag_text += f"   Error: {diagnostic['error']}\n"
        
        dialog = tk.Toplevel(self.root)
        dialog.title("FIWARE Diagnostic")
        dialog.geometry("700x400")
        dialog.configure(bg="#1e1e1e")
        
        text_widget = scrolledtext.ScrolledText(
            dialog, wrap=tk.WORD, font=("Courier", 9),
            bg="#0a0a0a", fg="#00ff00"
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        text_widget.insert(1.0, diag_text)
        text_widget.config(state=tk.DISABLED)
        
        tk.Button(dialog, text="Close", command=dialog.destroy,
                 bg="#e74c3c", fg="white", font=("Arial", 10, "bold"),
                 relief=tk.RAISED, bd=2, cursor="hand2"
        ).pack(pady=10)
    
    def refresh_fiware_data(self):
        """Refresh data from FIWARE."""
        print("\n🔄 Refreshing FIWARE data...")
        self.load_fiware_data()
        
        # Clear selections
        self.selected_robot = None
        self.selected_paths = []
        self.robot_var.set("")
        for var in self.path_vars.values():
            var.set(False)
        
        self.update_config_status()
        self.draw_canvas()
        
        messagebox.showinfo(
            "Refresh Complete",
            f"✅ Data refreshed!\n\n"
            f"Robots: {len(self.robots)}\n"
            f"Paths: {len(self.paths)}\n\n"
            f"Please reconfigure your selections."
        )
    
    # ========================================================================
    # REASONING & DECISION
    # ========================================================================
    
    def quick_decide_and_execute(self):
        """Quick decision and immediate execution."""
        if not self.selected_robot or len(self.selected_paths) < 2:
            messagebox.showwarning("Warning", "Please select a robot and at least 2 paths!")
            return
        
        self.update_status("⚡ QUICK MODE: Deciding and executing...", "#ff6b6b")
        self.quick_execute_btn.config(state=tk.DISABLED, text="⏳ Processing...")
        
        thread = Thread(target=self._quick_execute_thread)
        thread.daemon = True
        thread.start()
    
    def _quick_execute_thread(self):
        """Quick execution thread."""
        self._reasoning_logic()
        
        if self.decision:
            time.sleep(0.5)
            self.root.after(0, self.apply_decision)
        
        self.root.after(0, lambda: self.quick_execute_btn.config(
            state=tk.NORMAL, text="⚡ DECIDE & EXECUTE"
        ))
    
    def start_reasoning(self):
        """Start the ethical reasoning process."""
        if not self.selected_robot or len(self.selected_paths) < 2:
            messagebox.showwarning("Warning", "Please select a robot and at least 2 paths!")
            return
        
        self.update_status("🔄 Starting ethical reasoning...", "#ff9800")
        self.reasoning_log.config(state=tk.NORMAL)
        self.reasoning_log.delete(1.0, tk.END)
        self.reasoning_log.config(state=tk.DISABLED)
        
        self.start_btn.config(state=tk.DISABLED, text="⏳ Processing...")
        
        thread = Thread(target=self._reasoning_thread)
        thread.daemon = True
        thread.start()
    
    def _reasoning_thread(self):
        """Background thread for reasoning."""
        self._reasoning_logic()
        self.root.after(0, lambda: self.start_btn.config(
            state=tk.NORMAL, text="🧠 ANALYZE & DECIDE"
        ))
    
    def _reasoning_logic(self):
        """Core reasoning logic."""
        # ✅ PAS besoin d'import - les fonctions sont dans le même fichier
        
        self.log_reasoning("="*60)
        self.log_reasoning("🧠 ETHICAL REASONING PROCESS INITIATED")
        self.log_reasoning("="*60)
        
        self.log_reasoning("\n📝 Building prompt...")
        ethical_mode = self.ethical_mode.get()
        custom_inst = self.custom_instructions.get(1.0, tk.END).strip()
        if "Add specific" in custom_inst:
            custom_inst = ""
        
        # ✅ Appel direct de la fonction (définie plus haut dans le fichier)
        prompt = build_custom_prompt(
            self.selected_robot, 
            self.selected_paths,
            ethical_mode, 
            custom_inst, 
            self.modes_manager
        )
        
        self.current_prompt = prompt
        self.log_reasoning(f"✅ Prompt built with mode: {ethical_mode.upper()}")
        self.root.after(0, lambda: self.switch_prompt_tab())
        
        self.log_reasoning("\n🤖 Calling LLM for decision...")
        self.log_reasoning("   ⏱️ Measuring inference time...")
        
        # ✅ Appel direct de la fonction
        response, inference_time = call_llm_with_prompt(prompt)
        
        self.inference_time = inference_time
        self.llm_response_raw = response
        
        if not response:
            self.log_reasoning("\n❌ ERROR: No response from LLM")
            self.root.after(0, lambda: self.update_status("❌ LLM reasoning failed", "#e74c3c"))
            return
        
        self.log_reasoning(f"\n✅ LLM response received in {inference_time:.2f}s")
        
        self.root.after(0, lambda: self.metrics_label.config(
            text=f"⏱️ Inference Time: {inference_time:.2f}s"
        ))
        
        self.log_reasoning("\n🔍 Parsing decision...")
        
        # ✅ Appel direct de la fonction
        self.decision = parse_llm_response(response)
        
        if not self.decision:
            self.log_reasoning("\n❌ ERROR: Could not parse LLM response")
            self.root.after(0, lambda: self.update_status("❌ Failed to parse decision", "#e74c3c"))
            return
        
        self.log_reasoning("\n✅ Decision parsed successfully")
        self.log_reasoning("\n" + "="*60)
        self.log_reasoning("🎯 FINAL DECISION")
        self.log_reasoning("="*60)
        self.log_reasoning(f"Chosen Path: {self.decision['chosen_path']}")
        self.log_reasoning(f"Confidence: {self.decision['confidence']*100:.1f}%")
        self.log_reasoning(f"Safety Score: {self.decision['safety_score']}/100")
        self.log_reasoning(f"Reasoning: {self.decision['reasoning']}")
        self.log_reasoning("="*60)
        
        self.root.after(0, self._update_decision_display)


    def _update_decision_display(self):
        """Update decision display."""
        if not self.decision:
            return
        
        self.decision_text.config(state=tk.NORMAL)
        self.decision_text.delete(1.0, tk.END)
        
        decision_str = f"🎯 CHOSEN PATH: {self.decision['chosen_path']}\n\n"
        decision_str += f"📊 Confidence: {self.decision['confidence']*100:.1f}%\n"
        decision_str += f"🛡️ Safety Score: {self.decision['safety_score']}/100\n"
        decision_str += f"⏱️ Inference Time: {self.inference_time:.2f}s\n\n"
        decision_str += f"💭 Reasoning:\n{self.decision['reasoning']}"
        
        self.decision_text.insert(1.0, decision_str)
        self.decision_text.config(state=tk.DISABLED)
        
        self.apply_btn.config(state=tk.NORMAL)
        self.update_status("✅ Decision ready - Apply to start simulation", "#00cc66")
    
    def save_decision_to_fiware(self):
        """Save decision to FIWARE."""
        
        if not self.decision or not self.selected_robot:
            messagebox.showwarning("Warning", "No decision to save!")
            return
        
        success = record_decision_in_fiware(self.selected_robot['id'], self.decision)
        
        if success:
            messagebox.showinfo("Success", "✅ Decision recorded in FIWARE Digital Twin!")
            self.log_reasoning("\n💾 Decision saved to FIWARE")
        else:
            messagebox.showerror("Error", "❌ Failed to record decision in FIWARE")
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def update_robot_status_display(self):
        """Update robot status display."""
        if self.selected_robot:
            pos = self.selected_robot['position']
            text = f"ID: {self.selected_robot['name']}\n"
            text += f"Position: [{pos[0]:.1f}, {pos[1]:.1f}]\n"
            text += f"Battery: {self.selected_robot['battery']}%\n"
            text += f"Status: {self.selected_robot['status']}"
            
            if self.simulation_running and self.waypoints:
                text += f"\n\n📊 Progress: {self.current_waypoint_idx}/{len(self.waypoints)-1}"
                if self.current_waypoint_idx < len(self.waypoints) - 1:
                    next_wp = self.waypoints[self.current_waypoint_idx + 1]
                    text += f"\n🎯 Next: [{next_wp[0]:.1f}, {next_wp[1]:.1f}]"
            
            self.robot_status_label.config(text=text)
    
    def update_robot_info_in_config(self):
        """Update robot info in configuration panel."""
        if not self.selected_robot:
            return
        
        robot_id = self.selected_robot['id']
        if robot_id in self.robot_info_labels:
            pos = self.selected_robot['position']
            new_text = f"   🔋 {self.selected_robot['battery']}% | 📍 [{pos[0]:.1f}, {pos[1]:.1f}]"
            if self.simulation_running:
                new_text += " 🔄"
            self.robot_info_labels[robot_id].config(text=new_text)
    
    def log_reasoning(self, text):
        """Add text to reasoning log."""
        self.reasoning_log.config(state=tk.NORMAL)
        self.reasoning_log.insert(tk.END, f"{text}\n")
        self.reasoning_log.see(tk.END)
        self.reasoning_log.config(state=tk.DISABLED)
    
    def update_status(self, text, color="#ffffff"):
        """Update status label."""
        self.status_label.config(text=text, fg=color)



    # ========================================================================
    # SIMULATION LOGIC
    # ========================================================================
    
    def apply_decision(self):
        """Apply decision and start simulation."""
        if not self.decision:
            messagebox.showwarning("Warning", "No decision to apply!")
            return
        
        chosen_letter = self.decision['chosen_path']
        path_index = ord(chosen_letter) - ord('A')
        
        if path_index >= len(self.selected_paths):
            messagebox.showerror("Error", f"Invalid path choice: {chosen_letter}")
            return
        
        self.chosen_path = self.selected_paths[path_index]
        
        # Save to FIWARE
        record_decision_in_fiware(self.selected_robot['id'], self.decision)
        
        # Update robot status
        update_robot_status(self.selected_robot['id'], "path_chosen")
        self.selected_robot['status'] = 'path_chosen'
        
        self.log_reasoning(f"\n🚀 Starting simulation on Path {chosen_letter}: {self.chosen_path['name']}...")
        self.update_status(f"🎬 Simulating path {chosen_letter}...", "#3498db")
        
        # Prepare waypoints
        self.waypoints = self.chosen_path['waypoints'].copy()
        if not self.waypoints or self.waypoints[0] != self.selected_robot['position']:
            self.waypoints.insert(0, self.selected_robot['position'])
        
        self.current_waypoint_idx = 0
        self.simulation_running = True
        self.paused = False
        
        # Enable controls
        self.pause_btn.config(state=tk.NORMAL)
        self.resume_btn.config(state=tk.NORMAL)
        self.reset_btn.config(state=tk.NORMAL)
        self.origin_btn.config(state=tk.DISABLED)
        
        # Show progress
        self.progress_frame.pack(fill=tk.X, pady=(0,5))
        self.progress_bar['maximum'] = len(self.waypoints) - 1
        self.progress_bar['value'] = 0
        self.progress_label.config(text="Progress: 0%")
        
        # Update robot status
        update_robot_status(self.selected_robot['id'], "moving")
        self.selected_robot['status'] = 'moving'
        self.update_robot_status_display()
        self.update_robot_info_in_config()
        
        self.draw_canvas()
        
        # Start animation
        thread = Thread(target=self._simulation_thread)
        thread.daemon = True
        thread.start()
    
    def _simulation_thread(self):
        """Simulation thread."""
        while self.current_waypoint_idx < len(self.waypoints) - 1:
            if not self.simulation_running:
                break
            
            if self.paused:
                time.sleep(0.1)
                continue
            
            self._move_to_next_waypoint()
            time.sleep(0.3)  # Delay between waypoints
        
        if self.current_waypoint_idx >= len(self.waypoints) - 1:
            self.root.after(0, self._simulation_complete)
    
    def _move_to_next_waypoint(self):
        """Animate movement to next waypoint."""

        current_pos = self.waypoints[self.current_waypoint_idx]
        next_pos = self.waypoints[self.current_waypoint_idx + 1]
        
        # Smooth animation
        steps = 20
        for step in range(steps + 1):
            if self.paused or not self.simulation_running:
                return
            
            progress = step / steps
            self.current_display_pos = [
                current_pos[0] + progress * (next_pos[0] - current_pos[0]),
                current_pos[1] + progress * (next_pos[1] - current_pos[1])
            ]
            
            time.sleep(0.02)
            self.root.after(0, self.draw_canvas)
        
        # Waypoint reached
        self.current_waypoint_idx += 1
        self.current_display_pos = None
        
        # Update position
        self.selected_robot['position'] = next_pos
        
        # Update FIWARE
        success = update_robot_position(self.selected_robot['id'], next_pos[0], next_pos[1])
        
        # Update progress
        progress_pct = (self.current_waypoint_idx / (len(self.waypoints) - 1)) * 100
        self.root.after(0, lambda: self.progress_bar.config(value=self.current_waypoint_idx))
        self.root.after(0, lambda: self.progress_label.config(
            text=f"Progress: {progress_pct:.0f}% ({self.current_waypoint_idx}/{len(self.waypoints)-1})"
        ))
        
        # Log
        if success:
            self.root.after(0, lambda: self.log_reasoning(
                f"✅ Waypoint {self.current_waypoint_idx}/{len(self.waypoints)-1} reached: ({next_pos[0]:.1f}, {next_pos[1]:.1f})"
            ))
        else:
            self.root.after(0, lambda: self.log_reasoning(
                f"⚠️ Waypoint {self.current_waypoint_idx}/{len(self.waypoints)-1} reached: ({next_pos[0]:.1f}, {next_pos[1]:.1f}) [FIWARE ✗]"
            ))
        
        # Update displays
        self.root.after(0, self.update_robot_status_display)
        self.root.after(0, self.update_robot_info_in_config)
        self.root.after(0, self.draw_canvas)
    
    def _simulation_complete(self):
        """Handle simulation completion."""

        self.simulation_running = False
        
        final_pos = self.waypoints[-1]
        self.selected_robot['position'] = final_pos
        
        # Update FIWARE
        update_robot_position(self.selected_robot['id'], final_pos[0], final_pos[1])
        update_robot_status(self.selected_robot['id'], "arrived")
        
        self.log_reasoning("\n" + "="*60)
        self.log_reasoning("🎉 SIMULATION COMPLETE!")
        self.log_reasoning("="*60)
        self.log_reasoning(f"Final position: [{final_pos[0]:.2f}, {final_pos[1]:.2f}]")
        self.log_reasoning(f"Path taken: {self.decision['chosen_path']} - {self.chosen_path['name']}")
        self.log_reasoning(f"Total distance: {self.chosen_path['distance']}m")
        self.log_reasoning(f"Total waypoints: {len(self.waypoints)}")
        self.log_reasoning(f"Status: ARRIVED ✅")
        self.log_reasoning("="*60)
        
        self.update_status("✅ Simulation completed successfully!", "#00cc66")
        
        self.selected_robot['status'] = 'arrived'
        self.update_robot_status_display()
        
        final_text = f"🎉 DESTINATION REACHED!\n\n"
        final_text += f"Robot: {self.selected_robot['name']}\n"
        final_text += f"Final Position: [{final_pos[0]:.2f}, {final_pos[1]:.2f}]\n"
        final_text += f"Path: {self.decision['chosen_path']} - {self.chosen_path['name']}\n"
        final_text += f"Distance: {self.chosen_path['distance']}m\n"
        final_text += f"Status: ARRIVED ✅"
        
        self.final_status_label.config(text=final_text)
        self.final_status_frame.pack(fill=tk.X, pady=10)
        
        self.pause_btn.config(state=tk.DISABLED)
        self.resume_btn.config(state=tk.DISABLED)
        self.origin_btn.config(state=tk.NORMAL)
        
        # Progress complete
        self.progress_bar['value'] = self.progress_bar['maximum']
        self.progress_label.config(text="Progress: 100% - COMPLETE!")
        
        self.draw_canvas()
    
    def pause_simulation(self):
        """Pause simulation."""
        self.paused = True
        self.log_reasoning("\n⏸️ Simulation paused")
        self.update_status("⏸️ Simulation paused", "#f39c12")
    
    def resume_simulation(self):
        """Resume simulation."""
        self.paused = False
        self.log_reasoning("\n▶️ Simulation resumed")
        self.update_status("▶️ Simulation resumed", "#3498db")
    
    def reset_simulation(self):
        """Reset simulation."""
        self.simulation_running = False
        self.paused = False
        self.current_waypoint_idx = 0
        self.current_display_pos = None
        
        if self.waypoints:
            initial_pos = self.waypoints[0]
            update_robot_position(self.selected_robot['id'], initial_pos[0], initial_pos[1])
            update_robot_status(self.selected_robot['id'], "idle")
            self.selected_robot['position'] = initial_pos
            self.update_robot_status_display()
            self.update_robot_info_in_config()
        
        self.final_status_frame.pack_forget()
        self.progress_bar['value'] = 0
        self.progress_label.config(text="Progress: 0%")
        
        self.draw_canvas()
        
        self.log_reasoning("\n🔄 Simulation reset")
        self.update_status("🔄 Simulation reset - Ready to restart", "#95a5a6")
        
        self.apply_btn.config(state=tk.NORMAL)
        self.origin_btn.config(state=tk.DISABLED)
    
    def return_to_origin(self):
        """Return robot to initial position."""
  
        if not self.selected_robot:
            return
        
        origin = self.selected_robot.get('initial_position', [0, 0])
        
        self.log_reasoning(f"\n🏠 Returning to origin: {origin}")
        
        # Update position
        self.selected_robot['position'] = origin
        update_robot_position(self.selected_robot['id'], origin[0], origin[1])
        update_robot_status(self.selected_robot['id'], "idle")
        self.selected_robot['status'] = 'idle'
        
        self.update_robot_status_display()
        self.update_robot_info_in_config()
        self.draw_canvas()
        
        self.log_reasoning(f"✅ Robot returned to origin")
        self.update_status("✅ Robot returned to origin", "#9b59b6")
        
        messagebox.showinfo("Success", f"✅ Robot returned to origin:\n{origin}")
    
    # ========================================================================
    # VISUALIZATION
    # ========================================================================
    
    def draw_canvas(self):
        """Draw complete visualization on canvas."""
        self.canvas.delete("all")
        
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        
        if cw < 10 or ch < 10:
            return
        
        # Collect points
        all_points = []
        
        if self.selected_robot:
            all_points.append(self.selected_robot['position'])
        
        for path in self.selected_paths:
            all_points.extend(path['waypoints'])
        
        if self.current_display_pos:
            all_points.append(self.current_display_pos)
        
        if not all_points:
            self.canvas.create_text(
                cw//2, ch//2,
                text="Configure robot and paths to visualize",
                font=("Arial", 14, "bold"),
                fill="#666666"
            )
            return
        
        # Calculate bounds
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        padding = 70
        if max_x == min_x:
            max_x += 1
        if max_y == min_y:
            max_y += 1
        
        scale_x = (cw - 2 * padding) / (max_x - min_x)
        scale_y = (ch - 2 * padding) / (max_y - min_y)
        scale = min(scale_x, scale_y)
        
        def world_to_canvas(point):
            x = padding + (point[0] - min_x) * scale
            y = ch - padding - (point[1] - min_y) * scale
            return int(x), int(y)
        
        # Draw grid
        for i in range(6):
            x = padding + i * (cw - 2*padding) / 5
            self.canvas.create_line(
                x, padding, x, ch-padding, 
                fill=self.COLORS['grid'],  # ← Gris élégant
                width=1
            )
            y = padding + i * (ch - 2*padding) / 5
            self.canvas.create_line(
                padding, y, cw-padding, y, 
                fill=self.COLORS['grid'],
                width=1
            )
        # Draw paths
        if self.simulation_running and self.chosen_path:
            self._draw_path(self.chosen_path, world_to_canvas, is_chosen=True)
        else:
            colors = ["#3498db", "#e74c3c", "#f39c12", "#9b59b6", "#1abc9c", "#e67e22"]
            for i, path in enumerate(self.selected_paths):
                color = colors[i % len(colors)]
                self._draw_path(path, world_to_canvas, color=color, path_index=i)
        
        # Draw robot
        if self.selected_robot:
            if self.current_display_pos:
                robot_pos = world_to_canvas(self.current_display_pos)
            else:
                robot_pos = world_to_canvas(self.selected_robot['position'])
            
            # Outer glow
            self.canvas.create_oval(
                robot_pos[0]-30, robot_pos[1]-30,
                robot_pos[0]+30, robot_pos[1]+30,
                fill=self.COLORS['sim_robot_glow'],  # ← Rose clair glow
                outline="",
                width=0
            )
            
            # Robot body
            self.canvas.create_oval(
                robot_pos[0]-22, robot_pos[1]-22,
                robot_pos[0]+22, robot_pos[1]+22,
                fill=self.COLORS['sim_robot'],       # ← Rouge vif
                outline=self.COLORS['text_primary'], # ← Blanc cassé
                width=3
            )
            
            # Robot icon
            self.canvas.create_text(
                robot_pos[0], robot_pos[1],
                text="🤖",
                font=("Arial", 26)
            )
            
            # Robot label
            self.canvas.create_text(
                robot_pos[0], robot_pos[1]-40,
                text=self.selected_robot['name'],
                font=('Segoe UI', 11, 'bold'),
                fill=self.COLORS['text_primary']  # ← Blanc cassé
            )
        
        # Draw title
        if self.simulation_running and self.chosen_path:
            title = f"🎯 Following Path: {self.chosen_path['name']}"
            title_color = "#8b5cf6"
        elif self.selected_paths:
            title = f"📍 Viewing {len(self.selected_paths)} Path(s)"
            title_color = "#6366f1"
        else:
            title = "📍 Live Visualization"
            title_color = "#666666"
        
        self.canvas.create_text(
            cw//2, 30,
            text=title,
            font=("Arial", 14, "bold"),
            fill=title_color
        )
        
        # Draw legend
        self._draw_legend(cw, ch)
    
    def _draw_path(self, path, world_to_canvas, color=None, path_index=None, is_chosen=False):
        """Draw path with premium colors"""
        waypoints = path['waypoints']
        
        if not waypoints:
            return
        
        # Use default color if not specified
        if color is None:
            color = self.COLORS['sim_path_a']
        
        # Draw connections
        for i in range(len(waypoints) - 1):
            start = world_to_canvas(waypoints[i])
            end = world_to_canvas(waypoints[i + 1])
            
            if is_chosen and self.simulation_running:
                if i < self.current_waypoint_idx:
                    line_color = self.COLORS['sim_completed']  # ← Vert émeraude
                    width = 6
                    dash = None
                elif i == self.current_waypoint_idx:
                    line_color = self.COLORS['sim_current']    # ← Ambre
                    width = 7
                    dash = None
                else:
                    line_color = self.COLORS['sim_future']     # ← Gris ardoise
                    width = 4
                    dash = (8, 4)
            else:
                line_color = color
                width = 3
                dash = (6, 6)
            
            self.canvas.create_line(
                start, end,
                fill=line_color,
                width=width,
                dash=dash,
                capstyle=tk.ROUND
            )
        
        # Draw waypoints
        for i, wp in enumerate(waypoints):
            cx, cy = world_to_canvas(wp)
            
            if is_chosen and self.simulation_running:
                if i < self.current_waypoint_idx:
                    wp_color = self.COLORS['sim_completed']
                elif i == self.current_waypoint_idx:
                    wp_color = self.COLORS['sim_current']
                else:
                    wp_color = self.COLORS['sim_future']
            else:
                wp_color = color
            
            # Waypoint circle
            self.canvas.create_oval(
                cx-9, cy-9, cx+9, cy+9,
                fill=wp_color,
                outline=self.COLORS['text_primary'],
                width=2
            )
            
            # Waypoint number
            self.canvas.create_text(
                cx, cy-20,
                text=str(i),
                font=('Segoe UI', 9, 'bold'),
                fill=self.COLORS['text_primary']
            )

        
        # Path label
        if waypoints and path_index is not None and not is_chosen:
            mid_point = world_to_canvas(waypoints[len(waypoints)//2])
            label = f"Path {chr(65 + path_index)}: {path['name']}"
            
            self.canvas.create_text(
                mid_point[0], mid_point[1]-30,
                text=label,
                font=("Arial", 10, "bold"),
                fill=color
            )
    
    def _draw_legend(self, cw, ch):
        """Draw legend on canvas."""
        legend_y = ch - 30
        legend_x = 25
        
        if self.simulation_running:
            # Simulation legend
            self.canvas.create_line(legend_x, legend_y, legend_x+25, legend_y, 
                                   fill="#00ff00", width=5)
            self.canvas.create_text(legend_x+30, legend_y, text="Completed", 
                                   anchor=tk.W, font=("Arial", 9, "bold"), fill="#ffffff")
            
            self.canvas.create_line(legend_x+120, legend_y, legend_x+145, legend_y, 
                                   fill="#ff9800", width=6)
            self.canvas.create_text(legend_x+150, legend_y, text="Current", 
                                   anchor=tk.W, font=("Arial", 9, "bold"), fill="#ffffff")
            
            self.canvas.create_line(legend_x+230, legend_y, legend_x+255, legend_y, 
                                   fill="#444444", width=3, dash=(6,4))
            self.canvas.create_text(legend_x+260, legend_y, text="Remaining", 
                                   anchor=tk.W, font=("Arial", 9, "bold"), fill="#ffffff")
        else:
            # Selection legend
            self.canvas.create_text(legend_x, legend_y, 
                                   text="🛣️ Selected paths shown with different colors", 
                                   anchor=tk.W, font=("Arial", 9), fill="#888888")



# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """
    Launch the Ultimate Ethical Navigation System.
    
    This is the main entry point that:
    1. Initializes all managers
    2. Creates the GUI window
    3. Starts the application
    """
    
    print("\n" + "="*70)
    print("🚀 ULTIMATE ETHICAL NAVIGATION SYSTEM")
    print("="*70)
    print("\n✨ Enhanced Features:")
    print("   • Resizable panels with smooth interaction")
    print("   • Live prompt viewing and editing")
    print("   • Custom ethical modes with save/load")
    print("   • One-click 'Decide & Execute' button")
    print("   • Complete path visualization with progress")
    print("   • Return to origin functionality")
    print("   • Inference time tracking")
    print("   • Smooth animations and modern dark UI")
    print("   • Real-time FIWARE synchronization")
    print("\n" + "="*70 + "\n")
    
    # Check configuration
    print("🔑 Configuration Check:")
    
    fiware_url = os.getenv("FIWARE_URL", "http://localhost:1026/ngsi-ld/v1")
    print(f"   FIWARE URL: {fiware_url}")
    
    hf_token = os.getenv("HF_TOKEN")
    if hf_token:
        print(f"   ✅ HuggingFace: {hf_token[:10]}...")
    else:
        print("   ⚠️  HuggingFace: No token (will use mock decisions)")
    
    
    # Test FIWARE connection
    print("\n🌐 Testing FIWARE Connection:")
    diagnostic = test_fiware_connection()
    
    if diagnostic["connected"]:
        print(f"   ✅ FIWARE is accessible")
        print(f"   📊 Robots: {diagnostic['entities_count']['robots']}")
        print(f"   📊 Paths: {diagnostic['entities_count']['paths']}")
    else:
        print(f"   ⚠️  FIWARE connection issue: {diagnostic['error']}")
        print(f"   💡 Make sure FIWARE is running at {fiware_url}")
    
    print("\n✅ Launching GUI...\n")
    
    # Initialize managers
    modes_manager = CustomModesManager()
    
    # Create tkinter root window
    root = tk.Tk()
    
    # Create GUI application
    # Pass functions as dependencies for flexibility
    app = UltimateEthicalNavigationGUI(
        root=root,
        modes_manager=modes_manager,
        get_robots_func=get_all_robots,
        get_paths_func=get_all_paths
    )
    
    # Center window on screen
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    print("🎉 GUI launched successfully!")
    print("   Configure your robot, paths, and ethical mode to begin.\n")
    print("💡 TIPS:")
    print("   • Drag panel dividers to resize sections")
    print("   • Create custom ethical modes for specific scenarios")
    print("   • Use 'Decide & Execute' for quick testing")
    print("   • Check prompt viewer to see LLM input/output")
    print("\n" + "="*70 + "\n")
    
    # Start main event loop
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n\n⚠️  Keyboard interrupt detected")
    
    # Cleanup
    print("\n" + "="*70)
    print("👋 Ultimate Ethical Navigation System closed")
    print("="*70)
    print("   Thank you for using the system!")
    print("   All custom modes have been saved.\n")


if __name__ == "__main__":
    main()

