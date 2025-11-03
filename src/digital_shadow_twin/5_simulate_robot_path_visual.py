import requests
import json
import time
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation

FIWARE_URL = "http://localhost:1026/ngsi-ld/v1"
ROBOT_ID = "urn:ngsi-ld:Robot:omron_01"
PATH_A_ID = "urn:ngsi-ld:Path:route_A"

def get_entity(entity_id):
    resp = requests.get(f"{FIWARE_URL}/entities/{entity_id}")
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"❌ Entity {entity_id} not found: {resp.status_code}")
        return None

def update_robot_position(robot_id, coords):
    # convertir tous les éléments en float natif Python
    coords = [float(c) for c in coords]

    url = f"{FIWARE_URL}/entities/{robot_id}/attrs"
    payload = {
        "location": {
            "type": "GeoProperty",
            "value": {"type": "Point", "coordinates": coords}
        }
    }
    response = requests.patch(url, json=payload)
    if response.status_code in [204, 200]:
        print(f"✅ Robot moved to {coords}")
    else:
        print(f"❌ Failed to update robot: {response.status_code} - {response.text}")


def simulate_path_a_visual():
    robot = get_entity(ROBOT_ID)
    path_a = get_entity(PATH_A_ID)
    if not robot or not path_a:
        return

    waypoints = path_a.get("waypoints", {}).get("value", [])
    path_coords = []

    for wp in waypoints:
        if isinstance(wp, str) and wp.startswith("urn:ngsi-ld:Waypoint:"):
            wp_entity = get_entity(wp)
            if wp_entity:
                coords = wp_entity.get("location", {}).get("value", {}).get("coordinates", None)
            else:
                coords = None
        elif isinstance(wp, list) and len(wp) == 2:
            coords = wp
        else:
            coords = None

        if coords:
            path_coords.append(coords)
        else:
            print(f"⚠️ Invalid waypoint {wp}")

    if not path_coords:
        print("⚠️ No valid coordinates found")
        return

    print(f"🚀 Simulating robot {ROBOT_ID} along PATH A ({len(path_coords)} waypoints)")

    fig, ax = plt.subplots()
    path_coords = np.array(path_coords)
    ax.plot(path_coords[:,0], path_coords[:,1], "o--", label="Waypoints")
    robot_marker, = ax.plot([], [], "ro", label="Robot")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title("Robot Path Simulation")
    ax.legend()
    ax.grid(True)
    ax.set_aspect('equal', 'box')

    def animate(frame):
        if frame >= len(path_coords):
            return robot_marker,
        coords = path_coords[frame]
        robot_marker.set_data([coords[0]], [coords[1]])
        update_robot_position(ROBOT_ID, coords)
        return robot_marker,

    anim = FuncAnimation(fig, animate, frames=len(path_coords), interval=1000, repeat=False)  # blit=False
    plt.show()
    print("✅ Robot reached end of PATH A")

if __name__ == "__main__":
    simulate_path_a_visual()
