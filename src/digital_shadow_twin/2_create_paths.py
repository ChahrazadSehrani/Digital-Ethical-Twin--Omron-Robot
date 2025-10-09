"""
Script to create the two possible paths for the robot in FIWARE
Path A: Short (passes near humans)
Path B: Long (secure corridor)
Note: Humans are detected with their exact distance (realistic sensor data) under 10 meters (it's an assumption)
"""
import requests
from datetime import datetime

# FIWARE Configuration
FIWARE_URL = "http://localhost:1026/ngsi-ld/v1"
CONTEXT = ["https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"]

def create_path_a():
    """Create Path A: Short path passing through production area"""
    
    path_a = {
        "id": "urn:ngsi-ld:Path:route_A",
        "type": "NavigationPath",
        
        "name": {
            "type": "Property",
            "value": "Route A - Direct"
        },
        
        "distance": {
            "type": "Property",
            "value": 50,
            "unitCode": "MTR"
        },
        
        "estimatedDuration": {
            "type": "Property",
            "value": 90,
            "unitCode": "SEC"
        },
        
        "waypoints": {
            "type": "Property",
            "value": [
                [0, 0],       # Start
                [25, 5],      # Waypoint 1
                [50, 10],     # Waypoint 2
                [75, 15],     # Waypoint 3
                [100, 20]     # END: Storage B (same as Path B)
            ]
        },
        
        # Detected humans with their distances (expected to be realistic sensor data)
        # Detection radius: 10m (anything beyond is not detected)
        "detectedHumans": {
            "type": "Property",
            "value": [
                {"id": "human_1", "distance": 1.5},  # Very close - HIGH RISK
                {"id": "human_2", "distance": 5.8},  # Medium distance
                {"id": "human_3", "distance": 8.2}   # Still within 10m radius
            ],
            "observedAt": datetime.utcnow().isoformat() + "Z"
        },
        
        # Detection radius (defines "nearby")
        "detectionRadius": {
            "type": "Property",
            "value": 10,  # Sensor scans within 10 meters
            "unitCode": "MTR"
        },
        
        # Zone this path passes through
        "passesThrough": {
            "type": "Relationship",
            "object": "urn:ngsi-ld:Zone:production_area"
        },
        
        "@context": CONTEXT
    }
    
    try:
        response = requests.post(
            f"{FIWARE_URL}/entities",
            headers={"Content-Type": "application/ld+json"},
            json=path_a
        )
        
        if response.status_code == 201:
            print("✅ Path A created successfully!")
            print(f"   Distance: {path_a['distance']['value']}m")
            print(f"   Duration: {path_a['estimatedDuration']['value']}s")
            print(f"   Detection radius: {path_a['detectionRadius']['value']}m")
            print(f"   Detected humans: {len(path_a['detectedHumans']['value'])}")
            for human in path_a['detectedHumans']['value']:
                print(f"      • {human['id']}: {human['distance']}m away")
            print(f"   Destination: {path_a['waypoints']['value'][-1]}")
            return True
        elif response.status_code == 409:
            print("⚠️  Path A already exists")
            return False
        else:
            print(f"❌ Error creating Path A: {response.status_code}")
            print(f"   {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def create_path_b():
    """Create Path B: Longer path through secure corridor"""
    
    path_b = {
        "id": "urn:ngsi-ld:Path:route_B",
        "type": "NavigationPath",
        
        "name": {
            "type": "Property",
            "value": "Route B - Secure Corridor"
        },
        
        "distance": {
            "type": "Property",
            "value": 150,
            "unitCode": "MTR"
        },
        
        "estimatedDuration": {
            "type": "Property",
            "value": 270,
            "unitCode": "SEC"
        },
        
        "waypoints": {
            "type": "Property",
            "value": [
                [0, 0],       # Start
                [20, -10],    # Waypoint 1
                [50, -15],    # Waypoint 2
                [80, -10],    # Waypoint 3
                [100, 0],     # Waypoint 4
                [100, 20]     # END: Storage B (same destination as Path A)
            ]
        },
        
        # No humans detected within detection radius
        "detectedHumans": {
            "type": "Property",
            "value": [],  # Empty list = no humans detected
            "observedAt": datetime.utcnow().isoformat() + "Z"
        },
        
        # Detection radius (same sensor as Path A)
        "detectionRadius": {
            "type": "Property",
            "value": 10,
            "unitCode": "MTR"
        },
        
        # Zone this path passes through
        "passesThrough": {
            "type": "Relationship",
            "object": "urn:ngsi-ld:Zone:secure_corridor"
        },
        
        "@context": CONTEXT
    }
    
    try:
        response = requests.post(
            f"{FIWARE_URL}/entities",
            headers={"Content-Type": "application/ld+json"},
            json=path_b
        )
        
        if response.status_code == 201:
            print("✅ Path B created successfully!")
            print(f"   Distance: {path_b['distance']['value']}m")
            print(f"   Duration: {path_b['estimatedDuration']['value']}s")
            print(f"   Detection radius: {path_b['detectionRadius']['value']}m")
            print(f"   Detected humans: {len(path_b['detectedHumans']['value'])} (secure corridor)")
            print(f"   Destination: {path_b['waypoints']['value'][-1]}")
            return True
        elif response.status_code == 409:
            print("⚠️  Path B already exists")
            return False
        else:
            print(f"❌ Error creating Path B: {response.status_code}")
            print(f"   {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def verify_paths():
    """Verify both paths exist and display comparison"""
    
    try:
        # Get both paths
        path_a_response = requests.get(f"{FIWARE_URL}/entities/urn:ngsi-ld:Path:route_A")
        path_b_response = requests.get(f"{FIWARE_URL}/entities/urn:ngsi-ld:Path:route_B")
        
        if path_a_response.status_code == 200 and path_b_response.status_code == 200:
            print("\n✅ Verification: Both paths found in FIWARE")
            print("\n📊 COMPARISON (RAW SENSOR DATA):")
            print("="*70)
            
            path_a = path_a_response.json()
            path_b = path_b_response.json()
            
            # Extract human detection data
            humans_a = path_a.get('detectedHumans', {}).get('value', [])
            humans_b = path_b.get('detectedHumans', {}).get('value', [])
            
            print(f"{'Criterion':<25} | {'Path A (Direct)':<20} | {'Path B (Corridor)':<20}")
            print("-"*70)
            print(f"{'Distance':<25} | {path_a['distance']['value']:<20}m | {path_b['distance']['value']:<20}m")
            print(f"{'Duration':<25} | {path_a['estimatedDuration']['value']:<20}s | {path_b['estimatedDuration']['value']:<20}s")
            print(f"{'Detection Radius':<25} | {path_a['detectionRadius']['value']:<20}m | {path_b['detectionRadius']['value']:<20}m")
            print(f"{'Humans Detected':<25} | {len(humans_a):<20} | {len(humans_b):<20}")
            
            # Detail humans for Path A
            if humans_a:
                print(f"\n{'Path A - Human Details:':<45}")
                for human in humans_a:
                    print(f"  • {human['id']}: {human['distance']}m")
            
            if humans_b:
                print(f"\n{'Path B - Human Details:':<45}")
                for human in humans_b:
                    print(f"  • {human['id']}: {human['distance']}m")
            else:
                print(f"\n{'Path B:':<45} No humans detected (secure area)")
            
            
            return True
        else:
            print("\n❌ One or both paths not found")
            return False
            
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        return False

if __name__ == "__main__":
    print("🛣️  CREATION OF NAVIGATION PATHS (REALISTIC SENSOR DATA)")
    print("="*70)
    print("Note: Humans detected with exact distances (like real lidar/radar)")
    print("      Detection radius: 10m (anything beyond is not detected)")
    print()
    
    # Create Path A (with humans)
    print("Creating Path A (production area)...")
    success_a = create_path_a()
    print()
    
    # Create Path B (no humans)
    print("Creating Path B (secure corridor)...")
    success_b = create_path_b()
    
    # Verify and compare
    if success_a or success_b:
        verify_paths()
    
    print()
    print("="*70)