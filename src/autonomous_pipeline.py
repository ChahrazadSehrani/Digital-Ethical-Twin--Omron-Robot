"""
AUTONOMOUS ETHICAL DECISION PIPELINE FOR MOBILE ROBOTS
=======================================================

This script implements a complete autonomous pipeline that:
1. Retrieves robot and path data from FIWARE Digital Twin
2. Sends context to an LLM for ethical reasoning
3. Executes the LLM's decision by updating FIWARE
4. Launches an automatic GUI simulation showing the robot following the chosen path

The system prioritizes human safety while balancing operational efficiency.
"""

import os
import sys
import json
import re
import time
import requests
import tkinter as tk
from pathlib import Path
from datetime import datetime
from threading import Thread
from tkinter import ttk
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

# Load environment variables from .env file
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================
FIWARE_URL = "http://localhost:1026/ngsi-ld/v1"  # FIWARE Context Broker URL
HF_TOKEN = os.getenv("HF_TOKEN")  # HuggingFace API token
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # OpenAI API key (optional fallback)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # Anthropic API key (optional fallback)

# Model configuration - try different options
MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"  # Primary LLM model for ethical reasoning

# Initialize HuggingFace InferenceClient for LLM communication
try:
    client = InferenceClient(provider="novita", api_key=HF_TOKEN)
    LLM_PROVIDER = "huggingface"
except:
    client = None
    LLM_PROVIDER = None


# ============================================================================
# PART 1: CONTEXT BUILDING FROM FIWARE DIGITAL TWIN
# ============================================================================
# This section retrieves real-time data from FIWARE to build the decision context

def get_robot_state():
    """
    Retrieves the current state of the robot from FIWARE Digital Twin
    
    Returns:
        dict: Robot state including position, battery, status, velocity
        None: If request fails
    """
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
        print(f"❌ Error retrieving robot: {e}")
        return None


def get_path_info(path_id):
    """
    Retrieves path information from FIWARE Digital Twin
    
    Args:
        path_id (str): Path identifier (e.g., "route_A", "route_B")
    
    Returns:
        dict: Path data including distance, duration, detected humans, waypoints
        None: If request fails
    """
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
        print(f"❌ Error retrieving path {path_id}: {e}")
        return None


def build_context():
    """
    Builds the complete decision context by fetching robot and path data from FIWARE
    
    This function:
    - Retrieves current robot state
    - Fetches both available paths (A and B)
    - Combines all data into a structured context object
    
    Returns:
        dict: Complete context with robot state, path_a, path_b, and timestamp
        None: If any data retrieval fails
    """
    print("📊 Building context from FIWARE Digital Twin...")
    
    # Get current robot state
    robot = get_robot_state()
    if not robot:
        print("❌ Failed to retrieve robot state")
        return None
    
    # Get both available paths
    path_a = get_path_info("route_A")
    path_b = get_path_info("route_B")
    
    if not path_a or not path_b:
        print("❌ Failed to retrieve path information")
        return None
    
    # Combine all data into context object
    context = {
        "robot": robot,
        "path_a": path_a,
        "path_b": path_b,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    print("✅ Context built successfully")
    return context


def format_context_for_llm(context, ethical_priority="safety"):
    """
    Formats the context data into a natural language prompt for the LLM
    
    This function creates a structured prompt that:
    - Describes the current situation
    - Provides robot status information
    - Details both available paths with human detection data
    - States ethical principles in priority order (CONFIGURABLE)
    - Requests a JSON response with specific fields
    
    Args:
        context (dict): Context object from build_context()
        ethical_priority (str): "safety", "efficiency", or "energy" - changes priority order
    
    Returns:
        str: Formatted prompt for LLM
    """
    robot = context["robot"]
    path_a = context["path_a"]
    path_b = context["path_b"]
    
    # Calculate safety metrics for Path A
    humans_a = path_a["detected_humans"]
    min_distance_a = min([h["distance"] for h in humans_a]) if humans_a else None
    
    # Define different ethical priority orders
    priority_configs = {
        "safety": [
            "1. Human safety is the ABSOLUTE PRIORITY - never compromise safety",
            "2. Operational efficiency (minimize delivery time)",
            "3. Energy conservation (battery usage)"
        ],
        "efficiency": [
            "1. Operational efficiency (minimize delivery time) is the PRIMARY goal",
            "2. Human safety (maintain reasonable safe distance)",
            "3. Energy conservation (battery usage)"
        ],
        "energy": [
            "1. Energy conservation (maximize battery life) is CRITICAL",
            "2. Operational efficiency (minimize delivery time)",
            "3. Human safety (maintain minimum safe distance)"
        ],
        "balanced": [
            "1. Balance human safety with operational needs",
            "2. Optimize for efficiency when safety permits",
            "3. Consider energy conservation as a secondary factor"
        ]
    }
    
    priorities = priority_configs.get(ethical_priority, priority_configs["safety"])
    
    # Build the prompt with all relevant information
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

    # Add human position details if any are detected
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

ETHICAL PRINCIPLES (PRIORITY MODE: {ethical_priority.upper()}):
{chr(10).join(priorities)}

YOUR TASK:
Based on the raw sensor data above and the PRIORITY MODE "{ethical_priority.upper()}", analyze the ethical implications of each path and decide which path the robot should take.

IMPORTANT: You must respond ONLY with a valid JSON object in this exact format:
{{
  "chosen_path": "A" or "B",
  "confidence": 0.0 to 1.0,
  "reasoning": "Brief explanation in 1-2 sentences mentioning the priority mode",
  "safety_score": 0 to 100,
  "primary_concern": "safety" or "efficiency" or "energy" or "balanced"
}}

Do not include any text outside the JSON object. Your response must start with {{ and end with }}.
"""
    
    return prompt


# ============================================================================
# PART 2: LLM ETHICAL REASONING
# ============================================================================
# This section handles communication with the LLM for ethical decision-making

def call_llm(prompt, max_tokens=800):
    """
    Calls the LLM via multiple providers with automatic fallback
    
    Tries in order:
    1. HuggingFace InferenceClient
    2. OpenAI API (if key available)
    3. Anthropic Claude API (if key available)
    4. Mock decision (for testing without LLM)
    
    Args:
        prompt (str): The formatted ethical reasoning prompt
        max_tokens (int): Maximum length of LLM response
    
    Returns:
        str: LLM response text (should be JSON)
        None: If all methods fail
    """
    
    # DIAGNOSTIC: Show prompt hash to detect if prompt actually changes
    import hashlib
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
    print(f"🔍 Prompt hash: {prompt_hash} (use this to verify prompt changes)")
    
    # DIAGNOSTIC: Save prompt to file for inspection
    with open(f"debug_prompt_{prompt_hash}.txt", "w") as f:
        f.write(prompt)
    print(f"💾 Prompt saved to: debug_prompt_{prompt_hash}.txt")
    
    # Method 1: Try HuggingFace
    if client and HF_TOKEN:
        try:
            print(f"🤖 Calling LLM: {MODEL.split('/')[-1]}...")
            print("   (This may take 10-30 seconds...)")
            
            # Add randomness to bypass cache
            import random
            cache_buster = random.randint(1000, 9999)
            
            completion = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are an ethical decision system for autonomous robots. You analyze situations and make decisions prioritizing human safety. Always respond with valid JSON only. Request ID: {cache_buster}"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=max_tokens,
                temperature=0.7,  # INCREASED from 0.3 for more variety
            )
            
            response_text = completion.choices[0].message.content
            
            # DIAGNOSTIC: Save response
            response_hash = hashlib.md5(response_text.encode()).hexdigest()[:8]
            with open(f"debug_response_{response_hash}.txt", "w") as f:
                f.write(response_text)
            
            print(f"✅ LLM response received (HuggingFace)")
            print(f"🔍 Response hash: {response_hash}")
            print(f"💾 Response saved to: debug_response_{response_hash}.txt")
            return response_text
            
        except Exception as e:
            print(f"⚠️  HuggingFace failed: {str(e)[:100]}...")
            print("   Trying fallback methods...")
    
    # Method 2: Try OpenAI
    if OPENAI_API_KEY:
        try:
            print("🤖 Trying OpenAI API...")
            import openai
            openai.api_key = OPENAI_API_KEY
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an ethical decision system for autonomous robots. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=max_tokens
            )
            
            response_text = response.choices[0].message.content
            print("✅ LLM response received (OpenAI)")
            return response_text
            
        except Exception as e:
            print(f"⚠️  OpenAI failed: {e}")
    
    # Method 3: Try Anthropic Claude
    if ANTHROPIC_API_KEY:
        try:
            print("🤖 Trying Anthropic Claude API...")
            import anthropic
            
            client_claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            message = client_claude.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=max_tokens,
                temperature=0.3,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = message.content[0].text
            print("✅ LLM response received (Anthropic)")
            return response_text
            
        except Exception as e:
            print(f"⚠️  Anthropic failed: {e}")
    
    # Method 4: Mock decision for testing
    print("⚠️  All LLM providers failed. Using MOCK DECISION for testing.")
    print("   Add API keys to .env for real LLM reasoning:")
    print("   - HF_TOKEN=your_huggingface_token")
    print("   - OPENAI_API_KEY=your_openai_key")
    print("   - ANTHROPIC_API_KEY=your_anthropic_key")
    
    # Extract human count from prompt to make intelligent mock decision
    humans_path_a = prompt.count("Human positions:") > 0
    
    if humans_path_a:
        # If humans detected on Path A, choose safer Path B
        mock_decision = {
            "chosen_path": "B",
            "confidence": 0.95,
            "reasoning": "Path B chosen for maximum safety as Path A has human workers detected nearby.",
            "safety_score": 95,
            "primary_concern": "safety"
        }
    else:
        # If no humans, can choose shorter Path A
        mock_decision = {
            "chosen_path": "A",
            "confidence": 0.85,
            "reasoning": "Path A chosen for efficiency as no human workers detected on this route.",
            "safety_score": 90,
            "primary_concern": "efficiency"
        }
    
    return json.dumps(mock_decision)



def parse_llm_response(response_text):
    """
    Parses and validates the LLM response
    
    This function:
    - Attempts to parse the response as JSON
    - If that fails, extracts JSON from surrounding text
    - Validates the parsed decision structure
    
    Args:
        response_text (str): Raw LLM response
    
    Returns:
        dict: Validated decision object
        None: If parsing or validation fails
    """
    if not response_text:
        return None
    
    try:
        # Try direct JSON parsing first
        decision = json.loads(response_text)
        return validate_decision(decision)
    except json.JSONDecodeError:
        # If direct parsing fails, try to extract JSON from text
        print("⚠️  Response not pure JSON, attempting extraction...")
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
        
        if json_match:
            try:
                decision = json.loads(json_match.group())
                return validate_decision(decision)
            except:
                pass
        
        print("❌ Could not parse LLM response as JSON")
        return None


def validate_decision(decision):
    """
    Validates that the decision contains all required fields with valid values
    
    Checks:
    - All required fields are present
    - chosen_path is either "A" or "B"
    - confidence is between 0 and 1
    - safety_score is between 0 and 100
    
    Args:
        decision (dict): Parsed decision from LLM
    
    Returns:
        dict: Validated decision (with normalized values)
        None: If validation fails
    """
    required_fields = ["chosen_path", "confidence", "reasoning", "safety_score"]
    
    # Check all required fields exist
    for field in required_fields:
        if field not in decision:
            print(f"❌ Missing required field: {field}")
            return None
    
    # Validate path choice
    if decision["chosen_path"] not in ["A", "B"]:
        print(f"❌ Invalid path choice: {decision['chosen_path']}")
        return None
    
    # Normalize confidence to 0-1 range if needed
    if decision["confidence"] > 1:
        decision["confidence"] = decision["confidence"] / 100
    
    # Clamp confidence to valid range
    if not (0 <= decision["confidence"] <= 1):
        decision["confidence"] = max(0, min(1, decision["confidence"]))
    
    # Clamp safety score to valid range
    if not (0 <= decision["safety_score"] <= 100):
        decision["safety_score"] = max(0, min(100, decision["safety_score"]))
    
    return decision


def execute_decision(decision, context):
    """
    Records the LLM's decision in the FIWARE Digital Twin
    
    Updates the robot entity with:
    - Chosen path (A or B)
    - Ethical reasoning explanation
    - Decision confidence level
    - Updated status
    
    Args:
        decision (dict): Validated decision from LLM
        context (dict): Original context used for decision
    
    Returns:
        bool: True if update successful, False otherwise
    """
    chosen_path = decision["chosen_path"]
    
    print(f"\n🎯 EXECUTING DECISION: Path {chosen_path}")
    print(f"   Reasoning: {decision['reasoning']}")
    print(f"   Confidence: {decision['confidence']*100:.0f}%")
    print(f"   Safety Score: {decision['safety_score']}/100")
    
    # Prepare update data for FIWARE
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
        # Send PATCH request to update robot entity
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


# ============================================================================
# PART 3: AUTOMATIC GUI SIMULATION
# ============================================================================
# This section implements the graphical interface for visualizing robot movement

class AutoSimulatorGUI:
    """
    Graphical User Interface for automatic robot simulation
    
    This class:
    - Displays the robot's path visually on a canvas
    - Automatically simulates robot movement along waypoints
    - Updates robot position in FIWARE at each waypoint
    - Provides controls for pause, resume, and restart
    
    The simulation runs automatically once launched, following the path
    chosen by the LLM's ethical reasoning.
    """
    
    def __init__(self, root, chosen_path, context):
        """
        Initialize the GUI simulator
        
        Args:
            root: Tkinter root window
            chosen_path (str): "A" or "B" - the path chosen by LLM
            context (dict): Context object with robot and path data
        """
        self.root = root
        self.root.title("🤖 Autonomous Robot Simulation")
        self.root.geometry("1200x800")
        
        # Store simulation parameters
        self.chosen_path = chosen_path
        self.context = context
        
        # State variables for simulation
        self.robot = None
        self.path = None
        self.waypoints = []
        self.current_waypoint_index = 0
        self.is_moving = False
        self.current_robot_display_pos = None
        self.paused = False
        
        # Build UI and start simulation
        self.setup_ui()
        self.load_and_start()
        
    def setup_ui(self):
        """
        Sets up the user interface with control panel and visualization canvas
        
        Creates:
        - Left panel: Controls and information display
        - Right panel: Canvas for visual path representation
        """
        # Left control panel
        control_frame = ttk.Frame(self.root)
        control_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=10, pady=10)
        
        ttk.Label(control_frame, text="🤖 AUTONOMOUS SIMULATION", 
                 font=("Arial", 14, "bold")).pack(pady=10)
        
        ttk.Label(control_frame, text="ℹ️ INFORMATION", 
                 font=("Arial", 12, "bold")).pack(pady=20)
        
        # Text widget for status information
        self.info_text = tk.Text(control_frame, width=30, height=25, state=tk.DISABLED)
        self.info_text.pack(pady=10, fill=tk.BOTH, expand=True)
        
        # Control buttons
        ttk.Button(control_frame, text="⏸️  Pause", 
                  command=self.pause_simulation).pack(pady=5)
        ttk.Button(control_frame, text="▶️  Resume", 
                  command=self.resume_simulation).pack(pady=5)
        ttk.Button(control_frame, text="🔄 Restart", 
                  command=self.restart_simulation).pack(pady=5)
        
        # Right canvas panel
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        ttk.Label(canvas_frame, text="📍 REAL-TIME VISUALIZATION", 
                 font=("Arial", 14, "bold")).pack()
        
        # Canvas for drawing path and robot
        self.canvas = tk.Canvas(canvas_frame, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
    def add_info(self, text):
        """
        Adds text to the information panel
        
        Args:
            text (str): Text to display
        """
        self.info_text.config(state=tk.NORMAL)
        self.info_text.insert(tk.END, text + "\n")
        self.info_text.see(tk.END)
        self.info_text.config(state=tk.DISABLED)
        
    def load_and_start(self):
        """
        Loads path data from FIWARE and automatically starts simulation
        
        This function:
        1. Displays chosen path information
        2. Retrieves robot and path data from FIWARE
        3. Extracts waypoints for the chosen path
        4. Draws initial visualization
        5. Starts automatic simulation after 1 second delay
        """
        self.add_info("🚀 AUTOMATIC START")
        self.add_info("="*30)
        self.add_info(f"Chosen path: Route {self.chosen_path}")
        
        # Get path data from context
        path_key = f"path_{'a' if self.chosen_path == 'A' else 'b'}"
        path_data = self.context[path_key]
        
        self.add_info(f"Distance: {path_data['distance']}m")
        self.add_info(f"Estimated duration: {path_data['duration']}s")
        self.add_info(f"Detected humans: {len(path_data['detected_humans'])}")
        self.add_info("="*30 + "\n")
        
        # Fetch current data from FIWARE
        self.robot = self.get_robot()
        self.path = self.get_path(f"route_{self.chosen_path}")
        
        if not self.robot or not self.path:
            self.add_info("❌ Error loading data")
            return
        
        # Extract waypoints
        current_position = self.robot.get("location", {}).get("value", {}).get("coordinates", [0.0, 0.0])
        self.waypoints = self.path.get('waypoints', {}).get('value', [])
        
        # Ensure current position is first waypoint
        if not self.waypoints or self.waypoints[0] != current_position:
            self.waypoints.insert(0, current_position)
        
        self.add_info(f"📍 Start position: ({current_position[0]:.1f}, {current_position[1]:.1f})")
        self.add_info(f"🛣️  Number of waypoints: {len(self.waypoints)}\n")
        
        # Draw initial state
        self.draw_canvas()
        
        # Start automatic simulation after 1 second
        self.root.after(1000, self.auto_simulate_all)
        
    def draw_canvas(self):
        """
        Draws the path and robot on the canvas
        
        This function:
        - Calculates appropriate scaling for the coordinate space
        - Draws all waypoints as blue circles
        - Draws path segments (gray for unvisited, red for visited)
        - Draws the robot at its current position
        - Updates in real-time during movement
        """
        self.canvas.delete("all")
        
        if not self.waypoints:
            return
        
        # Get canvas dimensions
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        
        # Wait for canvas to be properly sized
        if cw < 2 or ch < 2:
            self.root.after(100, self.draw_canvas)
            return
        
        # Calculate bounds of waypoint coordinates
        xs = [p[0] for p in self.waypoints]
        ys = [p[1] for p in self.waypoints]
        
        if not xs or not ys:
            return
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        # Add padding and calculate scale
        padding = 50
        if max_x == min_x:
            max_x += 1
        if max_y == min_y:
            max_y += 1
        
        scale_x = (cw - 2 * padding) / (max_x - min_x)
        scale_y = (ch - 2 * padding) / (max_y - min_y)
        scale = min(scale_x, scale_y)
        
        def world_to_canvas(point):
            """Convert world coordinates to canvas coordinates"""
            x = padding + (point[0] - min_x) * scale
            y = ch - padding - (point[1] - min_y) * scale  # Invert Y axis
            return int(x), int(y)
        
        # Draw all waypoints as blue circles
        for i, wp in enumerate(self.waypoints):
            cx, cy = world_to_canvas(wp)
            self.canvas.create_oval(cx-8, cy-8, cx+8, cy+8, 
                                   fill="blue", outline="darkblue", width=2)
            self.canvas.create_text(cx, cy-15, text=str(i), 
                                   fill="blue", font=("Arial", 10, "bold"))
        
        # Draw all path segments in light gray (full path preview)
        for i in range(len(self.waypoints) - 1):
            start = world_to_canvas(self.waypoints[i])
            end = world_to_canvas(self.waypoints[i + 1])
            self.canvas.create_line(start, end, fill="lightgray", width=2, dash=(4, 4))
        
        # Draw visited segments in red dotted line
        if self.current_waypoint_index > 0:
            for i in range(self.current_waypoint_index):
                start = world_to_canvas(self.waypoints[i])
                end = world_to_canvas(self.waypoints[i + 1])
                self.canvas.create_line(start, end, fill="red", width=3, dash=(4, 4))
        
        # Draw current segment being traveled (solid red)
        if self.is_moving and self.current_waypoint_index < len(self.waypoints) - 1:
            start = world_to_canvas(self.waypoints[self.current_waypoint_index])
            end = world_to_canvas(self.waypoints[self.current_waypoint_index + 1])
            self.canvas.create_line(start, end, fill="red", width=4)
        
        # Draw robot at current position
        if self.current_robot_display_pos:
            robot_pos = world_to_canvas(self.current_robot_display_pos)
        else:
            robot_pos = world_to_canvas(self.waypoints[self.current_waypoint_index])
        
        self.canvas.create_oval(robot_pos[0]-12, robot_pos[1]-12, 
                               robot_pos[0]+12, robot_pos[1]+12, 
                               fill="red", outline="darkred", width=3)
        self.canvas.create_text(robot_pos[0], robot_pos[1], text="🤖", 
                               font=("Arial", 18))
        
        # Draw title
        self.canvas.create_text(cw//2, 20, 
                               text=f"Autonomous Simulation - Route {self.chosen_path}", 
                               font=("Arial", 16, "bold"))
        
    def auto_simulate_all(self):
        """
        Automatically simulates the entire path
        
        Starts a background thread that moves the robot through
        all waypoints until reaching the destination
        """
        if not self.waypoints:
            return
        
        self.add_info("🎬 Starting automatic simulation...")
        self.update_robot_status("moving")
        
        # Start simulation in separate thread to avoid blocking UI
        thread = Thread(target=self._auto_simulate_thread)
        thread.daemon = True
        thread.start()
        
    def _auto_simulate_thread(self):
        """
        Background thread for automatic simulation
        
        Loops through all waypoints, animating movement and
        updating FIWARE at each waypoint
        """
        while self.current_waypoint_index < len(self.waypoints) - 1:
            # Check if simulation is paused
            if self.paused:
                time.sleep(0.1)
                continue
            
            # Move to next waypoint
            self._move_animation()
            time.sleep(0.5)  # Pause between waypoints
        
        # Simulation complete
        self.add_info("\n" + "="*30)
        self.add_info("🎉 DESTINATION REACHED!")
        self.add_info("✅ Simulation completed successfully")
        self.add_info("="*30)
        
    def _move_animation(self):
        """
        Animates smooth movement from current waypoint to next waypoint
        
        This function:
        - Interpolates robot position over 30 steps
        - Updates display at each step for smooth animation
        - Updates FIWARE position when waypoint is reached
        - Updates status information
        """
        self.is_moving = True
        
        # Get current and next positions
        current_pos = self.waypoints[self.current_waypoint_index]
        next_pos = self.waypoints[self.current_waypoint_index + 1]
        
        # Animate movement with 30 interpolation steps
        steps = 30
        for step in range(steps + 1):
            if self.paused:
                return
            
            # Calculate interpolated position
            progress = step / steps
            self.current_robot_display_pos = [
                current_pos[0] + progress * (next_pos[0] - current_pos[0]),
                current_pos[1] + progress * (next_pos[1] - current_pos[1])
            ]
            
            # Update display
            time.sleep(0.05)
            self.draw_canvas()
            self.root.update()
        
        # Update FIWARE with new position at waypoint
        success = self.update_robot_position(next_pos[0], next_pos[1])
        
        if success:
            self.add_info(f"✅ Waypoint {self.current_waypoint_index + 1}/{len(self.waypoints)-1} "
                         f"reached: ({next_pos[0]:.1f}, {next_pos[1]:.1f})")
        
        # Update state
        self.current_waypoint_index += 1
        self.current_robot_display_pos = None
        self.is_moving = False
        
        # Check if destination reached
        if self.current_waypoint_index >= len(self.waypoints) - 1:
            self.update_robot_status("arrived")
        
        self.draw_canvas()
        
    def pause_simulation(self):
        """Pauses the automatic simulation"""
        self.paused = True
        self.add_info("⏸️  Simulation paused")
        
    def resume_simulation(self):
        """Resumes the paused simulation"""
        self.paused = False
        self.add_info("▶️  Simulation resumed")
        
    def restart_simulation(self):
        """
        Restarts the simulation from the beginning
        
        Resets all state variables and relaunches automatic simulation
        """
        self.current_waypoint_index = 0
        self.is_moving = False
        self.current_robot_display_pos = None
        self.paused = False
        self.add_info("\n🔄 Restarting simulation...")
        self.draw_canvas()
        self.root.after(500, self.auto_simulate_all)
        
    def get_robot(self):
        """Retrieves robot entity from FIWARE"""
        try:
            response = requests.get(f"{FIWARE_URL}/entities/urn:ngsi-ld:Robot:omron_01")
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None
        
    def get_path(self, path_id):
        """Retrieves path entity from FIWARE"""
        try:
            response = requests.get(f"{FIWARE_URL}/entities/urn:ngsi-ld:Path:{path_id}")
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None
        
    def update_robot_position(self, x, y):
        """
        Updates robot position in FIWARE Digital Twin
        
        Args:
            x (float): X coordinate
            y (float): Y coordinate
        
        Returns:
            bool: True if update successful
        """
        try:
            update = {
                "location": {
                    "type": "GeoProperty",
                    "value": {
                        "type": "Point",
                        "coordinates": [x, y]
                    }
                }
            }
            
            response = requests.patch(
                f"{FIWARE_URL}/entities/urn:ngsi-ld:Robot:omron_01/attrs",
                headers={"Content-Type": "application/json"},
                json=update
            )
            
            return response.status_code == 204
        except:
            return False
        
    def update_robot_status(self, status):
        """
        Updates robot status in FIWARE Digital Twin
        
        Args:
            status (str): New status (e.g., "moving", "arrived", "idle")
        
        Returns:
            bool: True if update successful
        """
        try:
            update = {
                "status": {
                    "type": "Property",
                    "value": status,
                    "observedAt": datetime.utcnow().isoformat() + "Z"
                }
            }
            
            response = requests.patch(
                f"{FIWARE_URL}/entities/urn:ngsi-ld:Robot:omron_01/attrs",
                headers={"Content-Type": "application/json"},
                json=update
            )
            
            return response.status_code == 204
        except:
            return False


# ============================================================================
# PART 4: MAIN AUTONOMOUS PIPELINE
# ============================================================================

def run_autonomous_pipeline(ethical_priority="safety"):
    """
    Complete autonomous pipeline:
    1. Retrieve FIWARE data
    2. Build context
    3. Call LLM for ethical decision
    4. Record decision in FIWARE
    5. Launch automatic GUI simulation
    
    Args:
        ethical_priority (str): "safety", "efficiency", "energy", or "balanced"
                                Changes the priority order in ethical reasoning
    
    Returns:
        dict: Decision object if successful, None otherwise
    """
    print("\n" + "="*70)
    print("🚀 AUTONOMOUS PIPELINE - ETHICAL DECISION SYSTEM")
    print("="*70 + "\n")
    
    # Check for API keys
    if not (HF_TOKEN or OPENAI_API_KEY or ANTHROPIC_API_KEY):
        print("⚠️  No LLM API keys found - will use MOCK DECISION mode")
        print("   The system will still work but with rule-based decisions")
        print("   Add API keys to .env for real LLM reasoning\n")
    else:
        print(f"✅ LLM provider available\n")
    
    # Display selected priority mode
    print(f"🎯 ETHICAL PRIORITY MODE: {ethical_priority.upper()}")
    print("-"*70 + "\n")
    
    # STEP 1: Build context from FIWARE
    print("STEP 1/5: Building context")
    print("-"*70)
    context = build_context()
    if not context:
        print("❌ Failed to build context")
        return None
    
    print(f"✅ Robot position: {context['robot']['position']}")
    print(f"✅ Battery: {context['robot']['battery']}%")
    print(f"✅ Path A: {context['path_a']['distance']}m, "
          f"{len(context['path_a']['detected_humans'])} humans")
    print(f"✅ Path B: {context['path_b']['distance']}m, "
          f"{len(context['path_b']['detected_humans'])} humans")
    
    # STEP 2: Format prompt for LLM with ethical priority
    print(f"\nSTEP 2/5: Formatting prompt with '{ethical_priority}' priority")
    print("-"*70)
    prompt = format_context_for_llm(context, ethical_priority)
    print(f"✅ Prompt created for LLM with {ethical_priority.upper()} priority mode")
    
    # STEP 3: Call LLM for ethical reasoning
    print("\nSTEP 3/5: LLM ethical reasoning")
    print("-"*70)
    llm_response = call_llm(prompt)
    
    if not llm_response:
        print("❌ No response from LLM")
        return None
    
    print(f"\n💬 LLM Response:")
    print(llm_response)
    
    # STEP 4: Parse and validate decision
    print("\nSTEP 4/5: Decision validation")
    print("-"*70)
    decision = parse_llm_response(llm_response)
    
    if not decision:
        print("❌ Failed to parse LLM decision")
        return None
    
    print(f"✅ Chosen path: {decision['chosen_path']}")
    print(f"✅ Confidence: {decision['confidence']*100:.0f}%")
    print(f"✅ Safety score: {decision['safety_score']}/100")
    print(f"✅ Reasoning: {decision['reasoning']}")
    
    # Record in FIWARE
    success = execute_decision(decision, context)
    if not success:
        print("⚠️  Warning: Failed to record in FIWARE")
    
    # STEP 5: Launch automatic GUI simulation
    print("\nSTEP 5/5: Launching GUI simulation")
    print("-"*70)
    print("✅ Opening graphical interface...")
    print(f"✅ Automatic simulation of path {decision['chosen_path']} starting...")
    
    # Create and launch GUI
    root = tk.Tk()
    app = AutoSimulatorGUI(root, decision['chosen_path'], context)
    
    print("\n" + "="*70)
    print("✅ COMPLETE PIPELINE LAUNCHED SUCCESSFULLY!")
    print("="*70)
    print("\n💡 The GUI simulation is now active.")
    print("   The robot will automatically follow the chosen path.")
    print("   Close the window to terminate.\n")
    
    root.mainloop()
    
    return decision


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print("\n🤖 AUTONOMOUS ETHICAL NAVIGATION SYSTEM")
    print("="*70)
    print("This script executes the complete pipeline:")
    print("  1. Retrieve data from FIWARE")
    print("  2. Ethical reasoning via LLM")
    print("  3. Decision recording")
    print("  4. Automatic visual simulation")
    print("="*70 + "\n")
    
    # Check available API keys
    print("🔑 Checking available LLM providers:")
    if HF_TOKEN:
        print(f"   ✅ HuggingFace: {HF_TOKEN[:10]}...")
    else:
        print("   ❌ HuggingFace: No token")
    
    if OPENAI_API_KEY:
        print(f"   ✅ OpenAI: {OPENAI_API_KEY[:10]}...")
    else:
        print("   ❌ OpenAI: No token")
        
    if ANTHROPIC_API_KEY:
        print(f"   ✅ Anthropic: {ANTHROPIC_API_KEY[:10]}...")
    else:
        print("   ❌ Anthropic: No token")
    
    if not (HF_TOKEN or OPENAI_API_KEY or ANTHROPIC_API_KEY):
        print("\n⚠️  No LLM API keys found. Will use MOCK DECISION mode.")
        print("   For real LLM reasoning, add to .env file:")
        print("   HF_TOKEN=your_token")
        print("   OPENAI_API_KEY=your_key")
        print("   ANTHROPIC_API_KEY=your_key")
    
    print()
    
    # CHOOSE ETHICAL PRIORITY MODE HERE
    print("🎯 Select Ethical Priority Mode:")
    print("   1. safety     - Safety first (default)")
    print("   2. efficiency - Efficiency first")
    print("   3. energy     - Energy conservation first")
    print("   4. balanced   - Balanced approach")
    print()
    
    # You can change this to test different priorities
    ETHICAL_MODE = "efficiency"  # Change to: "efficiency", "energy", or "balanced"
    
    # Or uncomment this for interactive mode:
    # user_choice = input("Enter mode (1-4) or press Enter for default: ").strip()
    # mode_map = {"1": "safety", "2": "efficiency", "3": "energy", "4": "balanced"}
    # ETHICAL_MODE = mode_map.get(user_choice, "safety")
    
    try:
        decision = run_autonomous_pipeline(ethical_priority=ETHICAL_MODE)
        
        if decision:
            print("\n" + "="*70)
            print("✅ MISSION ACCOMPLISHED!")
            print("="*70)
            print(f"Path taken: Route {decision['chosen_path']}")
            print(f"Reasoning: {decision['reasoning']}")
            print("="*70 + "\n")
        else:
            print("\n❌ Autonomous pipeline failed")
            print("   Check the errors above\n")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        print("   Goodbye! 👋\n")
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        print(f"   Type: {type(e).__name__}\n")
        import traceback
        traceback.print_exc()