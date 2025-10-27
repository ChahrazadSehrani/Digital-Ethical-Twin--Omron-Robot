import requests
import json
import time

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


def simulate_path_a():
    # Récupérer robot et path
    robot = get_entity(ROBOT_ID)
    path_a = get_entity(PATH_A_ID)
    if not robot or not path_a:
        return

    waypoints = path_a.get("waypoints", {}).get("value", [])
    if not waypoints:
        print("⚠️ No waypoints in PATH A")
        return

    print(f"🚀 Simulating robot {ROBOT_ID} along PATH A ({len(waypoints)} waypoints)")
    for wp in waypoints:
        # Si waypoint est une référence à une entité Waypoint
        if isinstance(wp, str) and wp.startswith("urn:ngsi-ld:Waypoint:"):
            wp_entity = get_entity(wp)
            if wp_entity:
                coords = wp_entity.get("location", {}).get("value", {}).get("coordinates", None)
            else:
                coords = None
        elif isinstance(wp, list) and len(wp) == 2:
            # waypoint défini directement par coordonnées [x, y]
            coords = wp
        else:
            coords = None

        if coords:
            update_robot_position(ROBOT_ID, coords)
        else:
            print(f"⚠️ Invalid waypoint {wp}")
        time.sleep(1)


    print("✅ Robot reached end of PATH A")

if __name__ == "__main__":
    simulate_path_a()
