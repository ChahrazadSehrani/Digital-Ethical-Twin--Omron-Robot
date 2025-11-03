"""
Script to create the digital twin of robot Omron in FIWARE
"""
import requests  # Library to send HTTP requests to FIWARE (GET, POST, PATCH, etc.)
import json
from datetime import datetime

# FIWARE Configuration
FIWARE_URL = "http://localhost:1026/ngsi-ld/v1"  # FIWARE API address running in Docker
CONTEXT = ["https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"]  # NGSI-LD standard (like a dictionary defining data formats)

def create_robot():
    """Create robot Omron entity in FIWARE"""
    
    # Build the robot object following NGSI-LD standard
    robot = {
        # Unique identifier: prefix:category:name -> urn:ngsi-ld:Robot:omron_01
        "id": "urn:ngsi-ld:Robot:omron_01",
        
        # Entity type
        "type": "MobileRobot",
        
        # Robot name (Property = simple value)
        "name": {
            "type": "Property",
            "value": "Omron LD-60 Production"
        },
        
        # Robot description
        "description": {
            "type": "Property",
            "value": "Autonomous mobile robot with ethical reasoning"
        },
        
        # Geographic position (GeoProperty = special for coordinates)
        "location": {
            "type": "GeoProperty",
            "value": {
                "type": "Point",
                "coordinates": [0.0, 0.0]  # Starting position [x, y] in warehouse
            }
        },
        
        # Battery level with timestamp
        "battery": {
            "type": "Property",
            "value": 85,  # 85% battery
            "unitCode": "P1",  # Standard code for "percentage"
            "observedAt": datetime.utcnow().isoformat() + "Z"  # When this value was measured
        },
        
        # Current status of the robot
        "status": {
            "type": "Property",
            "value": "idle",  # Possible values: idle, moving, charging, executing, error
            "observedAt": datetime.utcnow().isoformat() + "Z"
        },
        
        # Current velocity
        "velocity": {
            "type": "Property",
            "value": 0.0,  # 0 meters per second (stationary)
            "unitCode": "MTS"  # Meters per second
        },
        
        # Destination (Relationship = link to another entity)
        "destination": {
            "type": "Relationship",  # Points to another entity (not a simple value)
            "object": "urn:ngsi-ld:Waypoint:storage_B"  # Storage point B
        },
        
        # Context (mandatory for FIWARE to understand the format)
        "@context": CONTEXT
    }
    
    # Send POST request to FIWARE to create the entity
    try:
        response = requests.post(
            f"{FIWARE_URL}/entities",  # FIWARE endpoint to create entities
            headers={"Content-Type": "application/ld+json"},  # Specify JSON-LD format
            json=robot  # Send the robot object
        )
        
        # Handle response: 201 = Created successfully
        if response.status_code == 201:
            print("✅ Robot Omron created successfully in FIWARE!")
            print(f"   ID: {robot['id']}")
            print(f"   Type: {robot['type']}")
            print(f"   Position: {robot['location']['value']['coordinates']}")
            print(f"   Battery: {robot['battery']['value']}%")
            print(f"   Status: {robot['status']['value']}")
            return True
        
        # Handle response: 409 = Already exists (conflict)
        elif response.status_code == 409:
            print("⚠️  Robot already exists in FIWARE")
            print("   Use update_robot.py to modify it")
            return False
        
        # Handle other errors
        else:
            print(f"❌ Error during creation: {response.status_code}")
            print(f"   Message: {response.text}")
            return False
    
    # Handle connection error (Docker not running, FIWARE down, etc.)
    except requests.exceptions.ConnectionError:
        print("❌ Unable to connect to FIWARE")
        print("   Check that Docker is running: docker ps")
        return False
    
    # Handle any other unexpected error
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def verify_robot_exists():
    """Verify that the robot exists in FIWARE"""
    
    try:
        # Send GET request to read the robot entity
        response = requests.get(
            f"{FIWARE_URL}/entities/urn:ngsi-ld:Robot:omron_01"
        )
        
        # Handle response: 200 = OK (found)
        if response.status_code == 200:
            print("\n✅ Verification: Robot found in FIWARE")
            robot = response.json()  # Convert response to Python dictionary
            
            # Display robot info using .get() to avoid crashes if key is missing
            print(f"   Name: {robot.get('name', {}).get('value', 'N/A')}")
            print(f"   Position: {robot.get('location', {}).get('value', {}).get('coordinates', 'N/A')}")
            print(f"   Battery: {robot.get('battery', {}).get('value', 'N/A')}%")
            return True
        else:
            print("\n❌ Robot not found in FIWARE")
            return False
    
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        return False

# Entry point: execute only if script is run directly (not imported)
if __name__ == "__main__":
    print("🤖 DIGITAL TWIN CREATION - ROBOT OMRON")
    print("=" * 60)
    print()
    
    # Step 1: Create the robot
    success = create_robot()
    
    # Step 2: If creation successful, verify it exists
    if success:
        verify_robot_exists()
    
    print()
    print("=" * 60)