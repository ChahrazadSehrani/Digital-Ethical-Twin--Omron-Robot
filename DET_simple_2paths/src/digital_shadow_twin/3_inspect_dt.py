"""
Script to inspect and visualize all entities in the Digital Twin (FIWARE)
Displays: Multiple Robots, Paths, and their relationships
"""
import requests
import json
from datetime import datetime

# FIWARE Configuration
FIWARE_URL = "http://localhost:1026/ngsi-ld/v1"

def get_all_entities():
    """Retrieve all entities from FIWARE by querying each type"""
    all_entities = []
    
    # FIWARE Orion-LD requires type filtering for broad queries
    entity_types = ['MobileRobot', 'NavigationPath', 'Waypoint', 'WorkZone']
    
    print("🔍 Retrieving entities by type...")
    try:
        for entity_type in entity_types:
            response = requests.get(
                f"{FIWARE_URL}/entities",
                params={"type": entity_type}
            )
            
            if response.status_code == 200:
                entities = response.json()
                if entities:
                    all_entities.extend(entities)
                    print(f"   ✅ {entity_type}: {len(entities)} found")
                else:
                    print(f"   ℹ️  {entity_type}: 0 found")
            elif response.status_code == 400:
                continue
        
        print(f"\n📊 Total: {len(all_entities)} entities\n")
        return all_entities
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def display_robot(robot, robot_number):
    """Display robot information in a readable format"""
    print("="*70)
    print(f"🤖 ROBOT {robot_number}: {robot['id']}")
    print("="*70)
    print(f"Type: {robot['type']}")
    print(f"Name: {robot.get('name', {}).get('value', 'N/A')}")
    print(f"Description: {robot.get('description', {}).get('value', 'N/A')}")
    print()
    print("📍 Current State:")
    
    location = robot.get('location', {}).get('value', {})
    coords = location.get('coordinates', [0, 0])
    print(f"   Position: ({coords[0]}, {coords[1]})")
    print(f"   Battery: {robot.get('battery', {}).get('value', 'N/A')}%")
    print(f"   Status: {robot.get('status', {}).get('value', 'N/A')}")
    print(f"   Velocity: {robot.get('velocity', {}).get('value', 'N/A')} m/s")
    
    destination_obj = robot.get('destination', {}).get('object', 'N/A')
    if destination_obj != 'N/A':
        dest_name = destination_obj.split(':')[-1]
        print(f"   Destination: {dest_name}")
    
    print()

def display_path(path, path_label):
    """Display path information in a readable format"""
    print("-"*70)
    print(f"🛣️  {path_label}")
    print("-"*70)
    print(f"ID: {path['id']}")
    print(f"Name: {path.get('name', {}).get('value', 'N/A')}")
    print()
    print("📏 Path Metrics:")
    print(f"   Distance: {path.get('distance', {}).get('value', 'N/A')}m")
    print(f"   Estimated Duration: {path.get('estimatedDuration', {}).get('value', 'N/A')}s")
    print(f"   Detection Radius: {path.get('detectionRadius', {}).get('value', 'N/A')}m")
    print()
    
    # Display detected humans
    detected = path.get('detectedHumans', {}).get('value', [])
    print(f"👥 Detected Humans: {len(detected)}")
    if detected:
        for human in detected:
            print(f"   • {human['id']}: {human['distance']}m away")
    else:
        print("   • No humans detected within sensor range")
    
    print()
    print("📍 Waypoints:")
    waypoints = path.get('waypoints', {}).get('value', [])
    for i, wp in enumerate(waypoints):
        if i == 0:
            print(f"   Start:  {wp}")
        elif i == len(waypoints) - 1:
            print(f"   End:    {wp}")
        else:
            print(f"   WP {i}:   {wp}")
    
    # Passes through which zone
    passes = path.get('passesThrough', {}).get('object', 'N/A')
    if passes != 'N/A':
        zone_name = passes.split(':')[-1].replace('_', ' ').title()
        print(f"\n🏭 Passes Through: {zone_name}")
    
    print()

def display_waypoint(waypoint):
    """Display waypoint/destination information"""
    print("-"*70)
    print(f"📍 DESTINATION")
    print("-"*70)
    print(f"ID: {waypoint['id']}")
    print(f"Name: {waypoint.get('name', {}).get('value', 'N/A')}")
    print(f"Description: {waypoint.get('description', {}).get('value', 'N/A')}")
    
    location = waypoint.get('location', {}).get('value', {})
    coords = location.get('coordinates', [0, 0])
    print(f"Location: ({coords[0]}, {coords[1]})")
    print()

def compare_paths(path_a, path_b):
    """Display side-by-side comparison of both paths"""
    print("="*70)
    print("📊 PATH COMPARISON (FOR ETHICAL DECISION)")
    print("="*70)
    
    # Extract data
    dist_a = path_a.get('distance', {}).get('value', 0)
    dist_b = path_b.get('distance', {}).get('value', 0)
    dur_a = path_a.get('estimatedDuration', {}).get('value', 0)
    dur_b = path_b.get('estimatedDuration', {}).get('value', 0)
    humans_a = len(path_a.get('detectedHumans', {}).get('value', []))
    humans_b = len(path_b.get('detectedHumans', {}).get('value', []))
    
    # Get closest human distance for Path A
    detected_a = path_a.get('detectedHumans', {}).get('value', [])
    min_dist_a = min([h['distance'] for h in detected_a]) if detected_a else None
    
    print(f"\n{'Criterion':<30} | {'Path A (Direct)':<18} | {'Path B (Corridor)':<18}")
    print("-"*70)
    print(f"{'Distance':<30} | {dist_a:<18}m | {dist_b:<18}m")
    print(f"{'Duration':<30} | {dur_a:<18}s | {dur_b:<18}s")
    print(f"{'Humans Detected':<30} | {humans_a:<18} | {humans_b:<18}")
    if min_dist_a:
        print(f"{'Closest Human Distance':<30} | {min_dist_a:<18}m | {'N/A':<18}")
    
    # Calculate differences
    if dist_a > 0 and dur_a > 0:
        dist_diff = ((dist_b - dist_a) / dist_a * 100)
        dur_diff = ((dur_b - dur_a) / dur_a * 100)
        
        print()
        print("📈 Differences:")
        print(f"   Path B is {dist_diff:.0f}% longer in distance")
        print(f"   Path B takes {dur_diff:.0f}% more time")
        print(f"   Path A has {humans_a} detected humans vs {humans_b} for Path B")
    
    print()
    print("💡 ETHICAL DILEMMA:")
    print(f"   • Efficiency (Path A): {dist_a}m, {dur_a}s")
    print(f"   • Safety (Path B): {dist_b}m, {dur_b}s, no humans")
    if min_dist_a:
        print(f"   • Risk Factor: Closest human on Path A is {min_dist_a}m away")
    print()

def display_statistics(entities):
    """Display overall statistics of the Digital Twin"""
    
    # Count by type
    types = {}
    for entity in entities:
        entity_type = entity.get('type', 'Unknown')
        types[entity_type] = types.get(entity_type, 0) + 1
    
    print("="*70)
    print("📊 DIGITAL TWIN STATISTICS")
    print("="*70)
    print(f"Total Entities: {len(entities)}")
    print()
    print("Entities by Type:")
    for entity_type, count in types.items():
        print(f"   • {entity_type}: {count}")
    print()

def main():
    """Main inspection function"""
    print("\n🔍 DIGITAL TWIN INSPECTION - MULTI-ROBOT")
    print("="*70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Get all entities
    entities = get_all_entities()
    
    if not entities:
        print("❌ No entities found in FIWARE.")
        print("\n💡 Recreate them by running:")
        print("   python src/digital_twin/create_robot.py")
        print("   python src/digital_twin/create_paths.py")
        return
    
    # Separate entities by type
    robots = []
    paths = []
    waypoints = []
    
    for entity in entities:
        entity_type = entity.get('type', '')
        
        if entity_type == 'MobileRobot':
            robots.append(entity)
        elif entity_type == 'NavigationPath':
            paths.append(entity)
        elif entity_type == 'Waypoint':
            waypoints.append(entity)
    
    # Display all robots
    if robots:
        print(f"🤖 Found {len(robots)} robot(s)\n")
        for i, robot in enumerate(robots, 1):
            display_robot(robot, i)
    else:
        print("⚠️  No robots found\n")
    
    # Display all paths
    if paths:
        print(f"🛣️  Found {len(paths)} path(s)\n")
        for path in paths:
            path_id = path.get('id', '')
            if 'route_A' in path_id or 'path_A' in path_id.lower():
                display_path(path, f"PATH A - {path_id}")
            elif 'route_B' in path_id or 'path_B' in path_id.lower():
                display_path(path, f"PATH B - {path_id}")
            else:
                display_path(path, f"PATH - {path_id}")
    else:
        print("⚠️  No paths found\n")
    
    # Display all waypoints
    if waypoints:
        print(f"📍 Found {len(waypoints)} waypoint(s)\n")
        for waypoint in waypoints:
            display_waypoint(waypoint)
    else:
        print("⚠️  No destination waypoints found\n")
    
    # Compare paths if we have exactly 2 paths (A and B)
    if len(paths) >= 2:
        path_a = None
        path_b = None
        for path in paths:
            path_id = path.get('id', '')
            if 'route_A' in path_id or 'path_A' in path_id.lower():
                path_a = path
            elif 'route_B' in path_id or 'path_B' in path_id.lower():
                path_b = path
        
        if path_a and path_b:
            compare_paths(path_a, path_b)
    
    # Statistics
    display_statistics(entities)
    
    print("="*70)
    print("✅ Inspection complete!")
    print()
    print("💡 Next step: Run ethical_reasoner.py to let the LLM make a decision")
    print("="*70)
    print()

if __name__ == "__main__":
    main()