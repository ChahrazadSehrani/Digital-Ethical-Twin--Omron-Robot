"""
ADVANCED ETHICAL NAVIGATION GUI - ENHANCED
==========================================
Complete graphical interface with improved visual feedback:
- Radio button selection for robots and paths
- Real-time visualization of selected entities
- Live path preview and robot tracking
- Enhanced simulation with path visualization
"""

import os
import sys
import json
import re
import time
import requests
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
from datetime import datetime
from threading import Thread
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
import hashlib

# Load environment variables
load_dotenv()

# Configuration
FIWARE_URL = "http://localhost:1026/ngsi-ld/v1"
HF_TOKEN = os.getenv("HF_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"

# Initialize HuggingFace client
try:
    client = InferenceClient(provider="novita", api_key=HF_TOKEN)
except:
    client = None


# ============================================================================
# FIWARE DATA RETRIEVAL
# ============================================================================

def get_all_robots():
    """Retrieve all robots from FIWARE"""
    try:
        for robot_type in ["MobileRobot", "Robot"]:
            response = requests.get(f"{FIWARE_URL}/entities?type={robot_type}")
            if response.status_code == 200:
                robots = response.json()
                if robots:
                    result = []
                    for r in robots:
                        robot_id = r.get("id", "Unknown")
                        robot_name = robot_id.split(":")[-1] if ":" in robot_id else robot_id
                        
                        result.append({
                            "id": robot_id,
                            "name": r.get('name', {}).get('value', robot_name),
                            "short_name": robot_name,
                            "position": r.get('location', {}).get('value', {}).get('coordinates', [0, 0]),
                            "battery": r.get('battery', {}).get('value', 100),
                            "status": r.get('status', {}).get('value', 'unknown'),
                            "type": r.get('type', robot_type)
                        })
                    return result
        return []
    except Exception as e:
        print(f"Error getting robots: {e}")
        return []


def get_all_paths():
    """Retrieve all paths from FIWARE"""
    try:
        for path_type in ["NavigationPath", "Path"]:
            response = requests.get(f"{FIWARE_URL}/entities?type={path_type}")
            if response.status_code == 200:
                paths = response.json()
                if paths:
                    return [{
                        "id": p.get("id", "Unknown"),
                        "name": p.get('name', {}).get('value', p.get("id", "Unknown").split(":")[-1]),
                        "distance": p.get('distance', {}).get('value', 0),
                        "duration": p.get('estimatedDuration', {}).get('value', 0),
                        "detected_humans": p.get('detectedHumans', {}).get('value', []),
                        "waypoints": p.get('waypoints', {}).get('value', []),
                        "type": p.get('type', path_type)
                    } for p in paths]
        return []
    except Exception as e:
        print(f"Error getting paths: {e}")
        return []


def update_robot_position(robot_id, x, y):
    """Update robot position in FIWARE"""
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
            f"{FIWARE_URL}/entities/{robot_id}/attrs",
            headers={"Content-Type": "application/json"},
            json=update
        )
        return response.status_code == 204
    except:
        return False


def update_robot_status(robot_id, status):
    """Update robot status in FIWARE"""
    try:
        update = {
            "status": {
                "type": "Property",
                "value": status,
                "observedAt": datetime.utcnow().isoformat() + "Z"
            }
        }
        response = requests.patch(
            f"{FIWARE_URL}/entities/{robot_id}/attrs",
            headers={"Content-Type": "application/json"},
            json=update
        )
        return response.status_code == 204
    except:
        return False


def record_decision_in_fiware(robot_id, decision):
    """Record LLM decision in FIWARE"""
    try:
        update = {
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
                "value": decision.get("confidence", 0.0)
            },
            "safetyScore": {
                "type": "Property",
                "value": decision.get("safety_score", 0)
            },
            "decisionTimestamp": {
                "type": "Property",
                "value": datetime.utcnow().isoformat() + "Z"
            }
        }
        response = requests.patch(
            f"{FIWARE_URL}/entities/{robot_id}/attrs",
            headers={"Content-Type": "application/json"},
            json=update
        )
        return response.status_code == 204
    except Exception as e:
        print(f"Error recording decision: {e}")
        return False


# ============================================================================
# LLM REASONING
# ============================================================================

def build_custom_prompt(robot, paths, ethical_mode, custom_instructions=""):
    """Build customizable prompt for LLM"""
    
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
    
    priorities = priority_configs.get(ethical_mode, priority_configs["safety"])
    
    prompt = f"""You are an ethical decision system for an autonomous mobile robot in an industrial warehouse.

CURRENT SITUATION:
The robot must navigate from its current position to a destination.

ROBOT STATUS:
- ID: {robot['name']}
- Current position: {robot['position']}
- Battery level: {robot['battery']}%
- Current status: {robot['status']}

AVAILABLE PATHS:
"""
    
    for i, path in enumerate(paths):
        humans = path['detected_humans']
        min_dist = min([h['distance'] for h in humans]) if humans else None
        
        prompt += f"""
PATH {chr(65+i)} - {path['name']}:
- Distance: {path['distance']} meters
- Estimated duration: {path['duration']} seconds
- Humans detected: {len(humans)}"""
        
        if humans:
            prompt += f"\n- Human positions:"
            for human in humans:
                prompt += f"\n  • {human['id']}: {human['distance']}m away"
            prompt += f"\n- Closest human: {min_dist}m"
    
    prompt += f"""

ETHICAL PRINCIPLES (PRIORITY MODE: {ethical_mode.upper()}):
{chr(10).join(priorities)}
"""
    
    if custom_instructions:
        prompt += f"""
CUSTOM INSTRUCTIONS:
{custom_instructions}
"""
    
    prompt += """
YOUR TASK:
Analyze the ethical implications of each path and decide which path the robot should take.

IMPORTANT: Respond ONLY with a valid JSON object in this exact format:
{
  "chosen_path": "A" or "B" or "C" etc.,
  "confidence": 0.0 to 1.0,
  "reasoning": "Brief explanation in 1-2 sentences",
  "safety_score": 0 to 100,
  "primary_concern": "safety" or "efficiency" or "energy" or "balanced"
}

Do not include any text outside the JSON object.
"""
    
    return prompt


def call_llm_with_prompt(prompt):
    """Call LLM with the given prompt"""
    
    import random
    cache_buster = random.randint(1000, 9999)
    
    if client and HF_TOKEN:
        try:
            completion = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are an ethical decision system for autonomous robots. Always respond with valid JSON only. Request ID: {cache_buster}"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=800,
                temperature=0.7,
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"HuggingFace error: {e}")
    
    # Fallback to mock decision
    return json.dumps({
        "chosen_path": "B",
        "confidence": 0.85,
        "reasoning": "Mock decision: Choosing safer path based on rule-based logic.",
        "safety_score": 90,
        "primary_concern": "safety"
    })


def parse_llm_response(response_text):
    """Parse and validate LLM response"""
    if not response_text:
        return None
    
    try:
        decision = json.loads(response_text)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
        if json_match:
            try:
                decision = json.loads(json_match.group())
            except:
                return None
        else:
            return None
    
    required = ["chosen_path", "confidence", "reasoning", "safety_score"]
    for field in required:
        if field not in decision:
            return None
    
    if decision["confidence"] > 1:
        decision["confidence"] = decision["confidence"] / 100
    decision["confidence"] = max(0, min(1, decision["confidence"]))
    decision["safety_score"] = max(0, min(100, decision["safety_score"]))
    
    return decision


# ============================================================================
# MAIN GUI APPLICATION
# ============================================================================

class EthicalNavigationGUI:
    """Advanced GUI for ethical robot navigation with enhanced visualization"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("🤖 Advanced Ethical Navigation System")
        self.root.geometry("1400x900")
        self.root.configure(bg="#f0f0f0")
        
        # State variables
        self.robots = []
        self.paths = []
        self.selected_robot = None
        self.selected_paths = []
        self.decision = None
        self.simulation_running = False
        self.current_waypoint_idx = 0
        self.current_display_pos = None
        self.chosen_path = None
        self.paused = False
        self.waypoints = []
        
        # Radio button variables
        self.robot_var = tk.StringVar()
        self.path_vars = {}
        self.robot_info_labels = {}  # Store labels for dynamic updates
        
        # Load initial data
        self.load_fiware_data()
        
        # Setup UI
        self.setup_ui()
        
        # Initial canvas draw
        self.root.after(100, self.draw_canvas)
        
    def load_fiware_data(self):
        """Load robots and paths from FIWARE"""
        print("🔄 Loading FIWARE data...")
        self.robots = get_all_robots()
        self.paths = get_all_paths()
        
        print(f"   Found {len(self.robots)} robot(s)")
        print(f"   Found {len(self.paths)} path(s)")
        
        if not self.robots:
            print("   ⚠️  No robots found - check FIWARE connection")
        if not self.paths:
            print("   ⚠️  No paths found - check FIWARE entities")
        
    def setup_ui(self):
        """Setup the complete user interface"""
        
        # Main title
        title_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
        title_frame.pack(fill=tk.X, side=tk.TOP)
        title_frame.pack_propagate(False)
        
        tk.Label(
            title_frame,
            text="🤖 ADVANCED ETHICAL NAVIGATION SYSTEM - ENHANCED",
            font=("Arial", 18, "bold"),
            bg="#2c3e50",
            fg="white"
        ).pack(pady=15)
        
        # Main container with three columns
        main_container = tk.Frame(self.root, bg="#f0f0f0")
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # LEFT COLUMN: Configuration
        left_frame = tk.Frame(main_container, bg="white", relief=tk.RAISED, bd=2)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5, expand=False)
        left_frame.configure(width=350)
        left_frame.pack_propagate(False)
        
        self.setup_configuration_panel(left_frame)
        
        # CENTER COLUMN: Reasoning & Decision
        center_frame = tk.Frame(main_container, bg="white", relief=tk.RAISED, bd=2)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5, expand=True)
        
        self.setup_reasoning_panel(center_frame)
        
        # RIGHT COLUMN: Simulation
        right_frame = tk.Frame(main_container, bg="white", relief=tk.RAISED, bd=2)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5, expand=True)
        
        self.setup_simulation_panel(right_frame)
        
    def setup_configuration_panel(self, parent):
        """Setup left panel: Configuration with radio buttons"""
        
        # Header
        header = tk.Frame(parent, bg="#3498db", height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="⚙️ CONFIGURATION",
            font=("Arial", 12, "bold"),
            bg="#3498db",
            fg="white"
        ).pack(pady=10)
        
        # Scrollable content
        canvas_container = tk.Frame(parent, bg="white")
        canvas_container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(canvas_container, bg="white", highlightthickness=0)
        scrollbar = tk.Scrollbar(canvas_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        content = scrollable_frame
        
        # 1. Robot Selection with Radio Buttons
        tk.Label(content, text="1️⃣ Select Robot:", font=("Arial", 11, "bold"), bg="white", fg="#2c3e50").pack(anchor=tk.W, pady=(10,5), padx=10)
        
        robot_container = tk.Frame(content, bg="white", relief=tk.GROOVE, bd=2)
        robot_container.pack(fill=tk.X, pady=5, padx=10)
        
        # Store robot info labels for dynamic updates
        self.robot_info_labels = {}
        
        if self.robots:
            for i, robot in enumerate(self.robots):
                rb_frame = tk.Frame(robot_container, bg="white")
                rb_frame.pack(fill=tk.X, padx=5, pady=3)
                
                rb = tk.Radiobutton(
                    rb_frame,
                    text=f"🤖 {robot['name']}",
                    variable=self.robot_var,
                    value=robot['id'],
                    bg="white",
                    font=("Arial", 10, "bold"),
                    activebackground="white",
                    selectcolor="#3498db",
                    command=self.on_robot_changed
                )
                rb.pack(anchor=tk.W)
                
                # Create info label that can be updated
                info_label = tk.Label(
                    rb_frame,
                    text=f"   Battery: {robot['battery']}% | Pos: [{robot['position'][0]:.1f}, {robot['position'][1]:.1f}]",
                    font=("Courier", 8),
                    bg="white",
                    fg="#7f8c8d"
                )
                info_label.pack(anchor=tk.W, padx=20)
                
                # Store reference to update later
                self.robot_info_labels[robot['id']] = info_label
        else:
            tk.Label(robot_container, text="⚠️ No robots found", bg="white", fg="#e74c3c", font=("Arial", 9)).pack(pady=10)
        
        # 2. Path Selection with Checkboxes
        tk.Label(content, text="2️⃣ Select Paths (choose 2+):", font=("Arial", 11, "bold"), bg="white", fg="#2c3e50").pack(anchor=tk.W, pady=(20,5), padx=10)
        
        path_container = tk.Frame(content, bg="white", relief=tk.GROOVE, bd=2)
        path_container.pack(fill=tk.X, pady=5, padx=10)
        
        if self.paths:
            for i, path in enumerate(self.paths):
                self.path_vars[path['id']] = tk.BooleanVar()
                
                cb_frame = tk.Frame(path_container, bg="white")
                cb_frame.pack(fill=tk.X, padx=5, pady=3)
                
                cb = tk.Checkbutton(
                    cb_frame,
                    text=f"🛣️  {path['name']}",
                    variable=self.path_vars[path['id']],
                    bg="white",
                    font=("Arial", 10, "bold"),
                    activebackground="white",
                    selectcolor="#e74c3c",
                    command=self.on_path_changed
                )
                cb.pack(anchor=tk.W)
                
                info_label = tk.Label(
                    cb_frame,
                    text=f"   {path['distance']}m | {path['duration']}s | {len(path['detected_humans'])} humans",
                    font=("Courier", 8),
                    bg="white",
                    fg="#7f8c8d"
                )
                info_label.pack(anchor=tk.W, padx=20)
        else:
            tk.Label(path_container, text="⚠️ No paths found", bg="white", fg="#e74c3c", font=("Arial", 9)).pack(pady=10)
        
        # Selected paths display
        self.selected_paths_label = tk.Label(
            content,
            text="Selected: None",
            font=("Arial", 9, "bold"),
            bg="#fff3cd",
            fg="#856404",
            relief=tk.GROOVE,
            bd=1
        )
        self.selected_paths_label.pack(fill=tk.X, pady=(5,0), padx=10)
        
        # 3. Ethical Mode
        tk.Label(content, text="3️⃣ Ethical Priority Mode:", font=("Arial", 11, "bold"), bg="white", fg="#2c3e50").pack(anchor=tk.W, pady=(20,5), padx=10)
        
        mode_frame = tk.Frame(content, bg="white", relief=tk.GROOVE, bd=2)
        mode_frame.pack(fill=tk.X, pady=5, padx=10)
        
        self.ethical_mode = tk.StringVar(value="safety")
        modes = [
            ("🛡️ Safety First", "safety", "#27ae60"),
            ("⚡ Efficiency First", "efficiency", "#3498db"),
            ("🔋 Energy First", "energy", "#f39c12"),
            ("⚖️ Balanced", "balanced", "#9b59b6")
        ]
        
        for text, mode, color in modes:
            rb = tk.Radiobutton(
                mode_frame,
                text=text,
                variable=self.ethical_mode,
                value=mode,
                bg="white",
                font=("Arial", 10),
                activebackground="white",
                selectcolor=color,
                indicatoron=True
            )
            rb.pack(anchor=tk.W, padx=10, pady=5)
        
        # 4. Custom Instructions
        tk.Label(content, text="4️⃣ Custom Instructions (Optional):", font=("Arial", 11, "bold"), bg="white", fg="#2c3e50").pack(anchor=tk.W, pady=(20,5), padx=10)
        
        instr_frame = tk.Frame(content, relief=tk.GROOVE, bd=2)
        instr_frame.pack(fill=tk.X, pady=5, padx=10)
        
        self.custom_instructions = scrolledtext.ScrolledText(
            instr_frame,
            height=4,
            wrap=tk.WORD,
            font=("Arial", 9),
            bg="#f8f9fa"
        )
        self.custom_instructions.pack(fill=tk.X, padx=2, pady=2)
        self.custom_instructions.insert(1.0, "Example: Prioritize paths with good lighting...")
        
        ttk.Button(
            content,
            text="🗑️ Clear Instructions",
            command=lambda: self.custom_instructions.delete(1.0, tk.END)
        ).pack(fill=tk.X, pady=(2,0), padx=10)
        
        # Start Button
        start_btn_frame = tk.Frame(content, bg="white")
        start_btn_frame.pack(fill=tk.X, pady=20, padx=10)
        
        self.start_btn = tk.Button(
            start_btn_frame,
            text="🚀 START ETHICAL REASONING",
            command=self.start_reasoning,
            font=("Arial", 12, "bold"),
            bg="#27ae60",
            fg="white",
            activebackground="#229954",
            activeforeground="white",
            relief=tk.RAISED,
            bd=3,
            cursor="hand2",
            height=2,
            state=tk.DISABLED
        )
        self.start_btn.pack(fill=tk.X)
        
        # Utility buttons
        ttk.Button(
            content,
            text="🔄 Refresh FIWARE Data",
            command=self.refresh_fiware_data
        ).pack(fill=tk.X, pady=5, padx=10)
        
        ttk.Button(
            content,
            text="🔍 Test FIWARE Connection",
            command=self.test_fiware_connection
        ).pack(fill=tk.X, pady=2, padx=10)
        
        # Status indicator
        self.config_status = tk.Label(
            content,
            text="⚠️ Select robot and at least 2 paths",
            font=("Arial", 9),
            bg="#fff3cd",
            fg="#856404",
            relief=tk.GROOVE,
            bd=1
        )
        self.config_status.pack(fill=tk.X, pady=(10,10), padx=10)
    
    def on_robot_changed(self):
        """Handle robot selection change"""
        robot_id = self.robot_var.get()
        self.selected_robot = next((r for r in self.robots if r['id'] == robot_id), None)
        
        if self.selected_robot:
            self.update_robot_status_display()
            self.draw_canvas()
        
        self.update_config_status()
    
    def on_path_changed(self):
        """Handle path selection change"""
        self.selected_paths = [
            path for path in self.paths 
            if self.path_vars[path['id']].get()
        ]
        
        if self.selected_paths:
            names = [p['name'] for p in self.selected_paths]
            self.selected_paths_label.config(
                text=f"Selected ({len(self.selected_paths)}): {', '.join(names)}",
                bg="#d4edda" if len(self.selected_paths) >= 2 else "#fff3cd",
                fg="#155724" if len(self.selected_paths) >= 2 else "#856404"
            )
        else:
            self.selected_paths_label.config(
                text="Selected: None",
                bg="#fff3cd",
                fg="#856404"
            )
        
        self.draw_canvas()
        self.update_config_status()
    
    def update_config_status(self):
        """Update configuration status indicator"""
        if self.selected_robot and len(self.selected_paths) >= 2:
            self.config_status.config(
                text=f"✅ Ready: {self.selected_robot['name']} with {len(self.selected_paths)} paths",
                bg="#d4edda",
                fg="#155724"
            )
            self.start_btn.config(state=tk.NORMAL)
        else:
            missing = []
            if not self.selected_robot:
                missing.append("robot")
            if len(self.selected_paths) < 2:
                missing.append(f"{2-len(self.selected_paths)} more path(s)")
            
            self.config_status.config(
                text=f"⚠️ Need: {', '.join(missing)}",
                bg="#fff3cd",
                fg="#856404"
            )
            self.start_btn.config(state=tk.DISABLED)
    
    def test_fiware_connection(self):
        """Test FIWARE connection"""
        diagnostic = "🔍 FIWARE DIAGNOSTIC\n"
        diagnostic += "="*50 + "\n\n"
        
        try:
            response = requests.get(f"{FIWARE_URL.replace('/ngsi-ld/v1', '')}/version", timeout=2)
            if response.status_code == 200:
                diagnostic += "✅ FIWARE is running\n"
                diagnostic += f"   URL: {FIWARE_URL}\n\n"
            else:
                diagnostic += f"⚠️  FIWARE responded with status {response.status_code}\n\n"
        except requests.exceptions.ConnectionError:
            diagnostic += "❌ Cannot connect to FIWARE\n"
            diagnostic += f"   URL: {FIWARE_URL}\n"
            diagnostic += "   Make sure FIWARE is running!\n\n"
        except Exception as e:
            diagnostic += f"❌ Connection error: {e}\n\n"
        
        try:
            for entity_type in ["MobileRobot", "NavigationPath"]:
                response = requests.get(f"{FIWARE_URL}/entities?type={entity_type}", timeout=2)
                if response.status_code == 200:
                    entities = response.json()
                    diagnostic += f"✅ {entity_type}: {len(entities)} found\n"
                    for e in entities:
                        diagnostic += f"   • {e.get('id', 'Unknown')}\n"
                else:
                    diagnostic += f"⚠️  {entity_type}: Query failed ({response.status_code})\n"
        except Exception as e:
            diagnostic += f"❌ Query error: {e}\n"
        
        dialog = tk.Toplevel(self.root)
        dialog.title("FIWARE Diagnostic")
        dialog.geometry("600x500")
        
        text_widget = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=("Courier", 9))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert(1.0, diagnostic)
        text_widget.config(state=tk.DISABLED)
        
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)
        
    def setup_reasoning_panel(self, parent):
        """Setup center panel: Reasoning & Decision"""
        
        # Header
        header = tk.Frame(parent, bg="#e74c3c", height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="🧠 ETHICAL REASONING",
            font=("Arial", 12, "bold"),
            bg="#e74c3c",
            fg="white"
        ).pack(pady=10)
        
        content = tk.Frame(parent, bg="white")
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Status
        status_frame = tk.Frame(content, bg="#ecf0f1", relief=tk.GROOVE, bd=2)
        status_frame.pack(fill=tk.X, pady=(0,10))
        
        self.status_label = tk.Label(
            status_frame,
            text="⏳ Waiting for configuration...",
            font=("Arial", 10),
            bg="#ecf0f1",
            fg="#34495e",
            anchor=tk.W
        )
        self.status_label.pack(fill=tk.X, padx=10, pady=10)
        
        # Reasoning Log
        tk.Label(content, text="📋 Reasoning Process:", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, pady=(5,2))
        
        self.reasoning_log = scrolledtext.ScrolledText(
            content,
            height=12,
            wrap=tk.WORD,
            font=("Courier", 9),
            bg="#f8f9fa"
        )
        self.reasoning_log.pack(fill=tk.BOTH, expand=True, pady=5)
        self.reasoning_log.config(state=tk.DISABLED)
        
        # Decision Display
        tk.Label(content, text="🎯 LLM Decision:", font=("Arial", 10, "bold"), bg="white").pack(anchor=tk.W, pady=(10,2))
        
        decision_frame = tk.Frame(content, bg="#d5f4e6", relief=tk.GROOVE, bd=2)
        decision_frame.pack(fill=tk.X, pady=5)
        
        self.decision_text = tk.Text(decision_frame, height=6, wrap=tk.WORD, font=("Arial", 9), bg="#d5f4e6", relief=tk.FLAT)
        self.decision_text.pack(fill=tk.X, padx=10, pady=10)
        self.decision_text.config(state=tk.DISABLED)
        
        # Action Buttons
        button_frame = tk.Frame(content, bg="white")
        button_frame.pack(fill=tk.X, pady=10)
        
        self.apply_btn = ttk.Button(
            button_frame,
            text="✅ APPLY DECISION & SIMULATE",
            command=self.apply_decision,
            state=tk.DISABLED
        )
        self.apply_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        ttk.Button(
            button_frame,
            text="💾 Save Decision to FIWARE",
            command=self.save_decision_to_fiware
        ).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
    def setup_simulation_panel(self, parent):
        """Setup right panel: Live Simulation"""
        
        # Header
        header = tk.Frame(parent, bg="#27ae60", height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="📍 LIVE SIMULATION",
            font=("Arial", 12, "bold"),
            bg="#27ae60",
            fg="white"
        ).pack(pady=10)
        
        content = tk.Frame(parent, bg="white")
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Robot Status
        status_frame = tk.Frame(content, bg="#e8f8f5", relief=tk.GROOVE, bd=2)
        status_frame.pack(fill=tk.X, pady=(0,10))
        
        tk.Label(status_frame, text="🤖 Robot Status:", font=("Arial", 9, "bold"), bg="#e8f8f5").pack(anchor=tk.W, padx=5, pady=(5,2))
        
        self.robot_status_label = tk.Label(
            status_frame,
            text="No robot selected",
            font=("Arial", 9),
            bg="#e8f8f5",
            anchor=tk.W,
            justify=tk.LEFT
        )
        self.robot_status_label.pack(fill=tk.X, padx=10, pady=(0,5))
        
        # Canvas
        self.canvas = tk.Canvas(content, bg="white", highlightthickness=1, highlightbackground="#bdc3c7")
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Bind resize event
        self.canvas.bind('<Configure>', lambda e: self.draw_canvas())
        
        # Simulation Controls
        control_frame = tk.Frame(content, bg="white")
        control_frame.pack(fill=tk.X, pady=10)
        
        self.pause_btn = ttk.Button(control_frame, text="⏸️ Pause", command=self.pause_simulation, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        
        self.resume_btn = ttk.Button(control_frame, text="▶️ Resume", command=self.resume_simulation, state=tk.DISABLED)
        self.resume_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        
        self.reset_btn = ttk.Button(control_frame, text="🔄 Reset", command=self.reset_simulation, state=tk.DISABLED)
        self.reset_btn.pack(side=tk.LEFT, padx=2, expand=True, fill=tk.X)
        
        # Final Status
        self.final_status_frame = tk.Frame(content, bg="#d4edda", relief=tk.GROOVE, bd=2)
        self.final_status_label = tk.Label(
            self.final_status_frame,
            text="",
            font=("Arial", 10, "bold"),
            bg="#d4edda",
            fg="#155724"
        )
        self.final_status_label.pack(padx=10, pady=10)
    
    def draw_canvas(self):
        """Draw the current state on canvas"""
        self.canvas.delete("all")
        
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        
        if cw < 10 or ch < 10:
            return
        
        # Collect all points to display
        all_points = []
        
        # Add robot position
        if self.selected_robot:
            all_points.append(self.selected_robot['position'])
        
        # Add selected path waypoints
        for path in self.selected_paths:
            all_points.extend(path['waypoints'])
        
        # Add current display position if simulating
        if self.current_display_pos:
            all_points.append(self.current_display_pos)
        
        if not all_points:
            # Draw empty state message
            self.canvas.create_text(
                cw//2, ch//2,
                text="Select a robot and paths to visualize",
                font=("Arial", 12),
                fill="#7f8c8d"
            )
            return
        
        # Calculate bounds
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        padding = 60
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
        grid_color = "#ecf0f1"
        for i in range(5):
            x = padding + i * (cw - 2*padding) / 4
            self.canvas.create_line(x, padding, x, ch-padding, fill=grid_color, dash=(2,2))
            y = padding + i * (ch - 2*padding) / 4
            self.canvas.create_line(padding, y, cw-padding, y, fill=grid_color, dash=(2,2))
        
        # Draw paths
        if self.simulation_running and self.chosen_path:
            # During simulation, only show chosen path
            self._draw_path(self.chosen_path, world_to_canvas, is_chosen=True)
        else:
            # Show all selected paths
            colors = ["#3498db", "#e74c3c", "#f39c12", "#9b59b6", "#1abc9c"]
            for i, path in enumerate(self.selected_paths):
                color = colors[i % len(colors)]
                self._draw_path(path, world_to_canvas, color=color, path_index=i)
        
        # Draw robot
        if self.selected_robot:
            if self.current_display_pos:
                robot_pos = world_to_canvas(self.current_display_pos)
            else:
                robot_pos = world_to_canvas(self.selected_robot['position'])
            
            # Robot circle
            self.canvas.create_oval(
                robot_pos[0]-18, robot_pos[1]-18,
                robot_pos[0]+18, robot_pos[1]+18,
                fill="#e74c3c", outline="#c0392b", width=3
            )
            
            # Robot icon
            self.canvas.create_text(
                robot_pos[0], robot_pos[1],
                text="🤖",
                font=("Arial", 20)
            )
            
            # Robot label
            self.canvas.create_text(
                robot_pos[0], robot_pos[1]-30,
                text=self.selected_robot['name'],
                font=("Arial", 9, "bold"),
                fill="#2c3e50"
            )
        
        # Draw title
        if self.simulation_running and self.chosen_path:
            title = f"🎯 Following Path: {self.chosen_path['name']}"
            title_color = "#27ae60"
        elif self.selected_paths:
            title = f"📍 Showing {len(self.selected_paths)} Selected Path(s)"
            title_color = "#3498db"
        else:
            title = "📍 Live Visualization"
            title_color = "#7f8c8d"
        
        self.canvas.create_text(
            cw//2, 25,
            text=title,
            font=("Arial", 12, "bold"),
            fill=title_color
        )
        
        # Draw legend
        self._draw_legend(cw, ch)
    
    def _draw_path(self, path, world_to_canvas, color="#3498db", path_index=None, is_chosen=False):
        """Draw a single path on the canvas"""
        waypoints = path['waypoints']
        
        if not waypoints:
            return
        
        # Draw waypoint connections
        for i in range(len(waypoints) - 1):
            start = world_to_canvas(waypoints[i])
            end = world_to_canvas(waypoints[i + 1])
            
            if is_chosen:
                # During simulation
                if self.simulation_running:
                    if i < self.current_waypoint_idx:
                        # Completed segments - green
                        line_color = "#27ae60"
                        width = 4
                        dash = None
                    elif i == self.current_waypoint_idx:
                        # Current segment - orange
                        line_color = "#e67e22"
                        width = 5
                        dash = None
                    else:
                        # Future segments - gray dashed
                        line_color = "#bdc3c7"
                        width = 3
                        dash = (5, 3)
                else:
                    line_color = color
                    width = 3
                    dash = None
            else:
                line_color = color
                width = 2
                dash = (4, 4)
            
            self.canvas.create_line(
                start, end,
                fill=line_color,
                width=width,
                dash=dash
            )
        
        # Draw waypoints
        for i, wp in enumerate(waypoints):
            cx, cy = world_to_canvas(wp)
            
            if is_chosen and self.simulation_running:
                # Color based on status
                if i < self.current_waypoint_idx:
                    wp_color = "#27ae60"  # Completed
                elif i == self.current_waypoint_idx:
                    wp_color = "#e67e22"  # Current
                else:
                    wp_color = "#bdc3c7"  # Future
            else:
                wp_color = color
            
            # Waypoint circle
            self.canvas.create_oval(
                cx-6, cy-6, cx+6, cy+6,
                fill=wp_color,
                outline="#2c3e50",
                width=2
            )
            
            # Waypoint number
            self.canvas.create_text(
                cx, cy-15,
                text=str(i),
                font=("Arial", 8, "bold"),
                fill="#2c3e50"
            )
        
        # Draw path label
        if waypoints and path_index is not None and not is_chosen:
            mid_point = world_to_canvas(waypoints[len(waypoints)//2])
            label = f"Path {chr(65 + path_index)}: {path['name']}"
            
            # Background for label
            bbox = self.canvas.create_text(
                mid_point[0], mid_point[1]-25,
                text=label,
                font=("Arial", 9, "bold"),
                fill=color
            )
    
    def _draw_legend(self, cw, ch):
        """Draw legend on canvas"""
        legend_y = ch - 25
        legend_x = 20
        
        if self.simulation_running:
            # Simulation legend
            self.canvas.create_line(legend_x, legend_y, legend_x+20, legend_y, 
                                   fill="#27ae60", width=4)
            self.canvas.create_text(legend_x+25, legend_y, text="Completed", 
                                   anchor=tk.W, font=("Arial", 8))
            
            self.canvas.create_line(legend_x+100, legend_y, legend_x+120, legend_y, 
                                   fill="#e67e22", width=5)
            self.canvas.create_text(legend_x+125, legend_y, text="Current", 
                                   anchor=tk.W, font=("Arial", 8))
            
            self.canvas.create_line(legend_x+190, legend_y, legend_x+210, legend_y, 
                                   fill="#bdc3c7", width=3, dash=(5,3))
            self.canvas.create_text(legend_x+215, legend_y, text="Remaining", 
                                   anchor=tk.W, font=("Arial", 8))
        else:
            # Selection legend
            self.canvas.create_text(legend_x, legend_y, 
                                   text="Selected paths shown with different colors", 
                                   anchor=tk.W, font=("Arial", 8), fill="#7f8c8d")
    
    def update_robot_status_display(self):
        """Update robot status display with current position"""
        if self.selected_robot:
            pos = self.selected_robot['position']
            
            # Build status text with formatted position
            text = f"ID: {self.selected_robot['name']}\n"
            text += f"Position: [{pos[0]:.1f}, {pos[1]:.1f}]\n"
            text += f"Battery: {self.selected_robot['battery']}%\n"
            text += f"Status: {self.selected_robot['status']}"
            
            # Add movement info during simulation
            if self.simulation_running and self.waypoints:
                text += f"\n\nProgress: {self.current_waypoint_idx}/{len(self.waypoints)-1} waypoints"
                if self.current_waypoint_idx < len(self.waypoints) - 1:
                    next_wp = self.waypoints[self.current_waypoint_idx + 1]
                    text += f"\nNext: [{next_wp[0]:.1f}, {next_wp[1]:.1f}]"
                else:
                    text += f"\n🎯 Final waypoint reached!"
            
            self.robot_status_label.config(text=text)
    
    def update_robot_info_in_config(self):
        """Update robot info in configuration panel (called when position changes)"""
        if not self.selected_robot:
            return
        
        robot_id = self.selected_robot['id']
        
        # Update the info label in config panel if it exists
        if robot_id in self.robot_info_labels:
            pos = self.selected_robot['position']
            new_text = f"   Battery: {self.selected_robot['battery']}% | Pos: [{pos[0]:.1f}, {pos[1]:.1f}]"
            
            # Add visual indicator during simulation
            if self.simulation_running:
                new_text += " 🔄"
            
            self.robot_info_labels[robot_id].config(text=new_text)
    
    def log_reasoning(self, text):
        """Add text to reasoning log"""
        self.reasoning_log.config(state=tk.NORMAL)
        self.reasoning_log.insert(tk.END, f"{text}\n")
        self.reasoning_log.see(tk.END)
        self.reasoning_log.config(state=tk.DISABLED)
    
    def update_status(self, text, color="#34495e"):
        """Update status label"""
        self.status_label.config(text=text, fg=color)
    
    def refresh_fiware_data(self):
        """Refresh data from FIWARE"""
        print("\n🔄 Refreshing FIWARE data...")
        self.load_fiware_data()
        
        # Clear selections
        self.selected_robot = None
        self.selected_paths = []
        self.robot_var.set("")
        for var in self.path_vars.values():
            var.set(False)
        
        # Rebuild UI
        messagebox.showinfo("Refresh", f"✅ Loaded {len(self.robots)} robot(s) and {len(self.paths)} path(s)\n\nPlease reconfigure selections.")
        
        # Note: In a full implementation, you'd rebuild the radio buttons/checkboxes here
        # For now, user needs to restart the app after refresh
    
    def start_reasoning(self):
        """Start the ethical reasoning process"""
        
        if not self.selected_robot or len(self.selected_paths) < 2:
            messagebox.showwarning("Warning", "Please select a robot and at least 2 paths!")
            return
        
        self.update_status("🔄 Starting ethical reasoning...", "#e67e22")
        self.reasoning_log.config(state=tk.NORMAL)
        self.reasoning_log.delete(1.0, tk.END)
        self.reasoning_log.config(state=tk.DISABLED)
        
        self.start_btn.config(state=tk.DISABLED, text="⏳ Processing...")
        
        thread = Thread(target=self._reasoning_thread)
        thread.daemon = True
        thread.start()
    
    def _reasoning_thread(self):
        """Background thread for LLM reasoning"""
        
        self.log_reasoning("="*60)
        self.log_reasoning("🧠 ETHICAL REASONING PROCESS INITIATED")
        self.log_reasoning("="*60)
        
        self.log_reasoning("\n📝 Building prompt...")
        ethical_mode = self.ethical_mode.get()
        custom_inst = self.custom_instructions.get(1.0, tk.END).strip()
        if "Example:" in custom_inst:
            custom_inst = ""
        
        prompt = build_custom_prompt(
            self.selected_robot,
            self.selected_paths,
            ethical_mode,
            custom_inst
        )
        
        self.log_reasoning(f"✅ Prompt built with mode: {ethical_mode.upper()}")
        self.log_reasoning(f"✅ Comparing {len(self.selected_paths)} paths")
        
        self.log_reasoning("\n🤖 Calling LLM for decision...")
        self.log_reasoning("   (This may take 10-30 seconds...)")
        
        response = call_llm_with_prompt(prompt)
        
        if not response:
            self.log_reasoning("\n❌ ERROR: No response from LLM")
            self.root.after(0, lambda: self.update_status("❌ LLM reasoning failed", "#c0392b"))
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL, text="🚀 START ETHICAL REASONING"))
            return
        
        self.log_reasoning("\n✅ LLM response received")
        self.log_reasoning(f"\n💬 Raw Response:\n{response}")
        
        self.log_reasoning("\n🔍 Parsing decision...")
        self.decision = parse_llm_response(response)
        
        if not self.decision:
            self.log_reasoning("\n❌ ERROR: Could not parse LLM response")
            self.root.after(0, lambda: self.update_status("❌ Failed to parse decision", "#c0392b"))
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL, text="🚀 START ETHICAL REASONING"))
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
        self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL, text="🚀 START ETHICAL REASONING"))
    
    def _update_decision_display(self):
        """Update the decision display panel"""
        if not self.decision:
            return
        
        self.decision_text.config(state=tk.NORMAL)
        self.decision_text.delete(1.0, tk.END)
        
        decision_str = f"🎯 CHOSEN PATH: {self.decision['chosen_path']}\n\n"
        decision_str += f"📊 Confidence: {self.decision['confidence']*100:.1f}%\n"
        decision_str += f"🛡️ Safety Score: {self.decision['safety_score']}/100\n"
        decision_str += f"🔍 Primary Concern: {self.decision.get('primary_concern', 'N/A')}\n\n"
        decision_str += f"💭 Reasoning:\n{self.decision['reasoning']}"
        
        self.decision_text.insert(1.0, decision_str)
        self.decision_text.config(state=tk.DISABLED)
        
        self.apply_btn.config(state=tk.NORMAL)
        self.update_status("✅ Decision ready - Apply to start simulation", "#27ae60")
    
    def save_decision_to_fiware(self):
        """Save decision to FIWARE"""
        if not self.decision or not self.selected_robot:
            messagebox.showwarning("Warning", "No decision to save!")
            return
        
        success = record_decision_in_fiware(self.selected_robot['id'], self.decision)
        
        if success:
            messagebox.showinfo("Success", "✅ Decision recorded in FIWARE Digital Twin!")
            self.log_reasoning("\n💾 Decision saved to FIWARE")
        else:
            messagebox.showerror("Error", "❌ Failed to record decision in FIWARE")
    
    def apply_decision(self):
        """Apply decision and start simulation"""
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
        
        # Update robot status to "path_chosen"
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
        
        # Update robot status to "moving" and update displays
        update_robot_status(self.selected_robot['id'], "moving")
        self.selected_robot['status'] = 'moving'
        self.update_robot_status_display()
        self.update_robot_info_in_config()
        
        # Draw initial state
        self.draw_canvas()
        
        # Start animation
        thread = Thread(target=self._simulation_thread)
        thread.daemon = True
        thread.start()
    
    def _simulation_thread(self):
        """Background thread for simulation"""
        while self.current_waypoint_idx < len(self.waypoints) - 1:
            if not self.simulation_running:
                break
            
            if self.paused:
                time.sleep(0.1)
                continue
            
            self._move_to_next_waypoint()
            time.sleep(0.5)
        
        if self.current_waypoint_idx >= len(self.waypoints) - 1:
            self.root.after(0, self._simulation_complete)
    
    def _move_to_next_waypoint(self):
        """Animate movement to next waypoint"""
        current_pos = self.waypoints[self.current_waypoint_idx]
        next_pos = self.waypoints[self.current_waypoint_idx + 1]
        
        steps = 30
        for step in range(steps + 1):
            if self.paused or not self.simulation_running:
                return
            
            progress = step / steps
            self.current_display_pos = [
                current_pos[0] + progress * (next_pos[0] - current_pos[0]),
                current_pos[1] + progress * (next_pos[1] - current_pos[1])
            ]
            
            # Only update canvas during animation, NOT position
            time.sleep(0.05)
            self.root.after(0, self.draw_canvas)
        
        # Waypoint reached - NOW update position everywhere
        self.current_waypoint_idx += 1
        self.current_display_pos = None
        
        # Update robot position to exact waypoint
        self.selected_robot['position'] = next_pos
        
        # Update FIWARE with exact waypoint position
        success = update_robot_position(self.selected_robot['id'], next_pos[0], next_pos[1])
        
        # Log waypoint reached
        if success:
            self.root.after(0, lambda: self.log_reasoning(
                f"✅ Waypoint {self.current_waypoint_idx}/{len(self.waypoints)-1} reached: ({next_pos[0]:.1f}, {next_pos[1]:.1f}) | FIWARE ✓"
            ))
        else:
            self.root.after(0, lambda: self.log_reasoning(
                f"⚠️  Waypoint {self.current_waypoint_idx}/{len(self.waypoints)-1} reached: ({next_pos[0]:.1f}, {next_pos[1]:.1f}) | FIWARE ✗"
            ))
        
        # Update ALL displays with new position
        self.root.after(0, self.update_robot_status_display)
        self.root.after(0, self.update_robot_info_in_config)
        self.root.after(0, self.draw_canvas)
    
    def _simulation_complete(self):
        """Handle simulation completion"""
        self.simulation_running = False
        
        # Final position update
        final_pos = self.waypoints[-1]
        self.selected_robot['position'] = final_pos
        
        # Update FIWARE with final status
        update_robot_position(self.selected_robot['id'], final_pos[0], final_pos[1])
        update_robot_status(self.selected_robot['id'], "arrived")
        
        self.log_reasoning("\n" + "="*60)
        self.log_reasoning("🎉 SIMULATION COMPLETE!")
        self.log_reasoning("="*60)
        self.log_reasoning(f"Final position: [{final_pos[0]:.2f}, {final_pos[1]:.2f}]")
        self.log_reasoning(f"Path taken: {self.decision['chosen_path']} - {self.chosen_path['name']}")
        self.log_reasoning(f"Total waypoints traversed: {len(self.waypoints)}")
        self.log_reasoning(f"FIWARE status updated to: ARRIVED")
        self.log_reasoning("="*60)
        
        self.update_status("✅ Simulation completed successfully!", "#27ae60")
        
        # Update robot status one final time
        self.selected_robot['status'] = 'arrived'
        self.update_robot_status_display()
        
        final_text = f"🎉 DESTINATION REACHED!\n\n"
        final_text += f"Robot: {self.selected_robot['name']}\n"
        final_text += f"Final Position: [{final_pos[0]:.2f}, {final_pos[1]:.2f}]\n"
        final_text += f"Path: {self.decision['chosen_path']} - {self.chosen_path['name']}\n"
        final_text += f"Total Distance: {self.chosen_path['distance']}m\n"
        final_text += f"Status: ARRIVED ✅"
        
        self.final_status_label.config(text=final_text)
        self.final_status_frame.pack(fill=tk.X, pady=10)
        
        self.pause_btn.config(state=tk.DISABLED)
        self.resume_btn.config(state=tk.DISABLED)
        
        self.draw_canvas()
        
        # Fetch and show updated FIWARE data
        self.root.after(500, self.show_final_fiware_status)
    
    def show_final_fiware_status(self):
        """Show final robot status from FIWARE"""
        try:
            response = requests.get(f"{FIWARE_URL}/entities/{self.selected_robot['id']}")
            if response.status_code == 200:
                robot_data = response.json()
                
                final_info = "\n📊 FIWARE FINAL STATUS VERIFICATION:\n"
                final_info += "="*50 + "\n"
                
                fiware_pos = robot_data.get('location', {}).get('value', {}).get('coordinates', 'N/A')
                final_info += f"Position: {fiware_pos}\n"
                final_info += f"Status: {robot_data.get('status', {}).get('value', 'N/A')}\n"
                final_info += f"Battery: {robot_data.get('battery', {}).get('value', 'N/A')}%\n"
                
                if 'chosenPath' in robot_data:
                    final_info += f"Chosen Path: {robot_data['chosenPath']['value']}\n"
                
                if 'ethicalReasoning' in robot_data:
                    reasoning = robot_data['ethicalReasoning']['value']
                    final_info += f"Reasoning: {reasoning[:100]}...\n" if len(reasoning) > 100 else f"Reasoning: {reasoning}\n"
                
                if 'decisionConfidence' in robot_data:
                    confidence = robot_data['decisionConfidence']['value']
                    final_info += f"Confidence: {confidence*100:.1f}%\n"
                
                if 'safetyScore' in robot_data:
                    final_info += f"Safety Score: {robot_data['safetyScore']['value']}/100\n"
                
                final_info += "="*50 + "\n"
                final_info += "✅ All data synchronized with FIWARE Digital Twin"
                
                self.log_reasoning(final_info)
                
                # Show in message box
                messagebox.showinfo("FIWARE Synchronization", 
                    f"✅ Robot data successfully synchronized!\n\n"
                    f"Final Position: {fiware_pos}\n"
                    f"Status: {robot_data.get('status', {}).get('value', 'N/A')}\n\n"
                    f"Check console for detailed FIWARE status."
                )
                
        except Exception as e:
            self.log_reasoning(f"\n⚠️ Could not fetch final FIWARE status: {e}")
            messagebox.showwarning("FIWARE Status", 
                f"⚠️ Could not verify FIWARE synchronization.\n\n"
                f"Robot position should be updated to:\n{self.waypoints[-1]}"
            )
    
    def pause_simulation(self):
        """Pause simulation"""
        self.paused = True
        self.log_reasoning("\n⏸️ Simulation paused")
        self.update_status("⏸️ Simulation paused", "#f39c12")
    
    def resume_simulation(self):
        """Resume simulation"""
        self.paused = False
        self.log_reasoning("\n▶️ Simulation resumed")
        self.update_status("▶️ Simulation resumed", "#3498db")
    
    def reset_simulation(self):
        """Reset simulation"""
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
        
        self.final_status_frame.pack_forget()
        self.draw_canvas()
        
        self.log_reasoning("\n🔄 Simulation reset")
        self.update_status("🔄 Simulation reset - Ready to restart", "#95a5a6")
        
        self.apply_btn.config(state=tk.NORMAL)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Launch the enhanced GUI application"""
    
    print("\n🤖 ADVANCED ETHICAL NAVIGATION SYSTEM - ENHANCED")
    print("="*70)
    print("Launching graphical interface with live visualization...")
    print("="*70 + "\n")
    
    print("🔑 Available LLM Providers:")
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
        print("\n⚠️  No LLM API keys found.")
        print("   System will use mock decisions.")
        print("   Add API keys to .env for real LLM reasoning.\n")
    
    print("\n✅ Launching Enhanced GUI...\n")
    
    root = tk.Tk()
    app = EthicalNavigationGUI(root)
    root.mainloop()
    
    print("\n👋 Application closed. Goodbye!\n")


if __name__ == "__main__":
    main()