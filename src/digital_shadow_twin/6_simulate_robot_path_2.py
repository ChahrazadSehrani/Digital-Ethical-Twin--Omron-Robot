"""
Simulate robot movement along a path with advanced GUI
The robot follows waypoints and updates its position in FIWARE only at waypoints
"""
import requests
import time
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from threading import Thread

# FIWARE Configuration
FIWARE_URL = "http://localhost:1026/ngsi-ld/v1"

class RobotSimulatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🤖 Robot Movement Simulator")
        self.root.geometry("1200x800")
        self.root.resizable(True, True)
        
        # State variables
        self.robot = None
        self.path = None
        self.waypoints = []
        self.current_waypoint_index = 0
        self.is_moving = False
        self.path_choice = None
        self.current_robot_display_pos = None
        self.current_segment_progress = None
        
        # GUI components
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the user interface"""
        # Control panel
        control_frame = ttk.Frame(self.root)
        control_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=10, pady=10)
        
        ttk.Label(control_frame, text="🎮 CONTRÔLES", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Path selection
        ttk.Label(control_frame, text="Sélectionner un chemin:", font=("Arial", 10)).pack()
        path_frame = ttk.Frame(control_frame)
        path_frame.pack(pady=5)
        
        self.path_var = tk.StringVar()
        ttk.Radiobutton(path_frame, text="Route A", variable=self.path_var, value="A", 
                       command=self.on_path_selected).pack(anchor=tk.W)
        ttk.Radiobutton(path_frame, text="Route B", variable=self.path_var, value="B",
                       command=self.on_path_selected).pack(anchor=tk.W)
        
        ttk.Button(control_frame, text="Démarrer la simulation", command=self.start_simulation).pack(pady=10)
        ttk.Button(control_frame, text="▶ Waypoint suivant", command=self.move_to_next_waypoint).pack(pady=5)
        ttk.Button(control_frame, text="⏭️  Simulation complète", command=self.auto_simulate_all).pack(pady=5)
        ttk.Button(control_frame, text="Réinitialiser", command=self.reset_simulation).pack(pady=5)
        ttk.Button(control_frame, text="🏠 Retour à l'origine (0,0)", command=self.reset_to_origin).pack(pady=10)
        
        # Info panel
        ttk.Label(control_frame, text="ℹ️ INFORMATIONS", font=("Arial", 14, "bold")).pack(pady=20)
        
        self.info_text = tk.Text(control_frame, width=25, height=20, state=tk.DISABLED)
        self.info_text.pack(pady=10, fill=tk.BOTH, expand=True)
        
        # Canvas for visualization
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        ttk.Label(canvas_frame, text="📍 VISUALISATION", font=("Arial", 14, "bold")).pack()
        
        self.canvas = tk.Canvas(canvas_frame, bg="white", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        
    def add_info(self, text):
        """Add text to info panel"""
        self.info_text.config(state=tk.NORMAL)
        self.info_text.insert(tk.END, text + "\n")
        self.info_text.see(tk.END)
        self.info_text.config(state=tk.DISABLED)
        
    def clear_info(self):
        """Clear info panel"""
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.config(state=tk.DISABLED)
        
    def on_path_selected(self):
        """Handle path selection"""
        self.path_choice = self.path_var.get()
        self.load_path_data()
        
    def load_path_data(self):
        """Load path data from FIWARE"""
        if not self.path_choice:
            return
            
        self.robot = self.get_robot()
        self.path = self.get_path(f"route_{self.path_choice}")
        
        if not self.robot or not self.path:
            messagebox.showerror("Erreur", "Impossible de charger les données FIWARE")
            return
            
        # Extract waypoints
        current_position = self.robot.get("location", {}).get("value", {}).get("coordinates", [0.0, 0.0])
        self.waypoints = self.path.get('waypoints', {}).get('value', [])
        
        if not self.waypoints or self.waypoints[0] != current_position:
            self.waypoints.insert(0, current_position)
        
        self.current_waypoint_index = 0
        self.is_moving = False
        
        # Display info
        self.clear_info()
        self.add_info(f"📦 Chemin: {self.path.get('name', {}).get('value', 'Inconnu')}")
        self.add_info(f"📏 Distance: {self.path.get('distance', {}).get('value', 0)}m")
        self.add_info(f"⏱️  Durée: {self.path.get('estimatedDuration', {}).get('value', 0)}s")
        self.add_info(f"🛣️  Waypoints: {len(self.waypoints)}")
        self.add_info(f"👥 Humains: {len(self.path.get('detectedHumans', {}).get('value', []))}")
        self.add_info("\n📍 Position initiale:")
        self.add_info(f"   X: {current_position[0]:.2f}")
        self.add_info(f"   Y: {current_position[1]:.2f}")
        
        # Draw canvas
        self.draw_canvas()
        
    def draw_canvas(self):
        """Draw the path and robot on canvas"""
        self.canvas.delete("all")
        
        if not self.waypoints:
            return
        
        # Get canvas dimensions
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        
        if cw < 2 or ch < 2:
            self.root.after(100, self.draw_canvas)
            return
        
        # Calculate scaling
        xs = [p[0] for p in self.waypoints]
        ys = [p[1] for p in self.waypoints]
        
        if not xs or not ys:
            return
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        padding = 50
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
        
        # Draw all waypoints in blue
        for i, wp in enumerate(self.waypoints):
            cx, cy = world_to_canvas(wp)
            self.canvas.create_oval(cx-8, cy-8, cx+8, cy+8, fill="blue", outline="darkblue", width=2)
            self.canvas.create_text(cx, cy-15, text=str(i), fill="blue", font=("Arial", 10, "bold"))
        
        # Draw all segments in light gray (full path)
        for i in range(len(self.waypoints) - 1):
            start = world_to_canvas(self.waypoints[i])
            end = world_to_canvas(self.waypoints[i + 1])
            self.canvas.create_line(start, end, fill="lightgray", width=2, dash=(4, 4))
        
        # Draw visited segments in red dotted
        if self.current_waypoint_index > 0:
            for i in range(self.current_waypoint_index):
                start = world_to_canvas(self.waypoints[i])
                end = world_to_canvas(self.waypoints[i + 1])
                self.canvas.create_line(start, end, fill="red", width=3, dash=(4, 4))
        
        # Draw current segment being traveled (if moving)
        if self.is_moving and self.current_waypoint_index < len(self.waypoints) - 1:
            start = world_to_canvas(self.waypoints[self.current_waypoint_index])
            end = world_to_canvas(self.waypoints[self.current_waypoint_index + 1])
            self.canvas.create_line(start, end, fill="red", width=4, dash=(4, 4))
        
        # Draw robot at current position
        if self.current_robot_display_pos:
            robot_pos = world_to_canvas(self.current_robot_display_pos)
        else:
            robot_pos = world_to_canvas(self.waypoints[self.current_waypoint_index])
            
        self.canvas.create_oval(robot_pos[0]-10, robot_pos[1]-10, 
                               robot_pos[0]+10, robot_pos[1]+10, 
                               fill="red", outline="darkred", width=3)
        self.canvas.create_text(robot_pos[0], robot_pos[1], text="🤖", font=("Arial", 16))
        
        # Draw title and legend
        self.canvas.create_text(cw//2, 15, text="Simulation du Mouvement du Robot", 
                              font=("Arial", 14, "bold"))
        self.canvas.create_text(20, ch-20, text="🔵 Bleu = waypoints | 🔴 Rouge = chemin parcouru", 
                              font=("Arial", 9), anchor=tk.W)
        
    def on_canvas_click(self, event):
        """Handle canvas click to move to next waypoint"""
        if not self.is_moving and self.current_waypoint_index < len(self.waypoints) - 1:
            self.move_to_next_waypoint()
        
    def move_to_next_waypoint(self):
        """Move robot to next waypoint"""
        if not self.waypoints:
            messagebox.showwarning("Avertissement", "Chargez d'abord un chemin")
            return
        
        if self.current_waypoint_index >= len(self.waypoints) - 1:
            messagebox.showinfo("Info", "Vous êtes arrivé à destination!")
            return
        
        thread = Thread(target=self._move_animation)
        thread.daemon = True
        thread.start()
        
    def _move_animation(self):
        """Animate movement to next waypoint with synchronized display"""
        self.is_moving = True
        
        current_pos = self.waypoints[self.current_waypoint_index]
        next_pos = self.waypoints[self.current_waypoint_index + 1]
        
        # Animate movement with synchronized path drawing
        steps = 30
        for step in range(steps + 1):
            progress = step / steps
            self.current_robot_display_pos = [
                current_pos[0] + progress * (next_pos[0] - current_pos[0]),
                current_pos[1] + progress * (next_pos[1] - current_pos[1])
            ]
            
            time.sleep(0.05)
            self.draw_canvas()
            self.root.update()
        
        # Update FIWARE only at the waypoint
        success = self.update_robot_position(next_pos[0], next_pos[1])
        
        if success:
            self.add_info(f"✅ Waypoint {self.current_waypoint_index + 1} atteint: ({next_pos[0]:.1f}, {next_pos[1]:.1f})")
        else:
            self.add_info(f"⚠️  Échec FIWARE pour waypoint {self.current_waypoint_index + 1}")
        
        self.current_waypoint_index += 1
        self.current_robot_display_pos = None
        self.is_moving = False
        
        if self.current_waypoint_index >= len(self.waypoints) - 1:
            self.update_robot_status("arrived")
            self.add_info("\n🎉 Destination atteinte!")
        
        self.draw_canvas()
        
    def start_simulation(self):
        """Start the simulation"""
        if not self.path_choice:
            messagebox.showwarning("Avertissement", "Sélectionnez d'abord un chemin")
            return
        
        self.clear_info()
        self.add_info("🚀 Simulation démarrée")
        self.add_info("Cliquez ou 'Waypoint suivant'")
        self.update_robot_status("moving")
        
    def reset_simulation(self):
        """Reset the simulation"""
        self.current_waypoint_index = 0
        self.is_moving = False
        self.current_robot_display_pos = None
        if self.robot:
            current_pos = self.robot.get("location", {}).get("value", {}).get("coordinates", [0.0, 0.0])
            self.update_robot_position(current_pos[0], current_pos[1])
            self.update_robot_status("idle")
        self.clear_info()
        self.add_info("↻ Simulation réinitialisée")
        self.draw_canvas()
        
    def reset_to_origin(self):
        """Reset robot to origin (0, 0) and update FIWARE"""
        if not self.robot:
            messagebox.showwarning("Avertissement", "Aucun robot chargé")
            return
        
        success = self.update_robot_position(0.0, 0.0)
        
        if success:
            if self.waypoints:
                self.waypoints[0] = [0.0, 0.0]
            self.current_waypoint_index = 0
            self.is_moving = False
            self.current_robot_display_pos = None
            
            self.clear_info()
            self.add_info("🏠 Robot retourné à l'origine (0, 0)")
            self.add_info("✅ Position mise à jour dans FIWARE")
            self.update_robot_status("idle")
            self.draw_canvas()
        else:
            messagebox.showerror("Erreur", "Impossible de mettre à jour FIWARE")
        
    def auto_simulate_all(self):
        """Automatically simulate the entire path"""
        if not self.waypoints:
            messagebox.showwarning("Avertissement", "Chargez d'abord un chemin")
            return
        
        if self.current_waypoint_index >= len(self.waypoints) - 1:
            messagebox.showinfo("Info", "Destination déjà atteinte!")
            return
        
        self.clear_info()
        self.add_info("🚀 Simulation automatique en cours...")
        self.update_robot_status("moving")
        
        thread = Thread(target=self._auto_simulate_thread)
        thread.daemon = True
        thread.start()
        
    def _auto_simulate_thread(self):
        """Thread for automatic simulation"""
        while self.current_waypoint_index < len(self.waypoints) - 1:
            self._move_animation()
            time.sleep(0.3)
        
        self.add_info("\n✅ Simulation automatique terminée!")
        
    def get_robot(self):
        """Get current robot state from FIWARE"""
        try:
            response = requests.get(f"{FIWARE_URL}/entities/urn:ngsi-ld:Robot:omron_01")
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Robot not found: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
        
    def get_path(self, path_id):
        """Get path from FIWARE"""
        try:
            response = requests.get(f"{FIWARE_URL}/entities/urn:ngsi-ld:Path:{path_id}")
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Path {path_id} not found: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
        
    def update_robot_position(self, x, y):
        """Update robot position in FIWARE (only at waypoints)"""
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
        except Exception as e:
            print(f"❌ Error updating position: {e}")
            return False
        
    def update_robot_status(self, status):
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
                f"{FIWARE_URL}/entities/urn:ngsi-ld:Robot:omron_01/attrs",
                headers={"Content-Type": "application/json"},
                json=update
            )
            
            return response.status_code == 204
        except Exception as e:
            print(f"❌ Error updating status: {e}")
            return False


def main():
    root = tk.Tk()
    app = RobotSimulatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()