# Digital Ethical Twin (DET) - Omron Robot

## 📋 Objectif
Intégration d'un raisonnement éthique basé sur LLM dans un jumeau numérique 
pour robot mobile Omron.

## 🛠️ Stack technique
- FIWARE Orion Context Broker (Digital Twin)
- Python 3.11+
- Docker Compose
- LLM API 

---

## 📋 Table of Contents

1. [Daily Startup Guide](#-daily-startup-guide)
2. [Project Structure](#-project-structure)
3. [Initial Setup (One-time)](#-initial-setup-one-time)
4. [Common Commands](#-common-commands)
5. [Troubleshooting](#-troubleshooting)

---

## ⚙️ Initial Setup (One-time)

**Only do this ONCE when first setting up the project on a new machine.**

### Prerequisites (tested on macOS (M4 Pro))
1. Homebrew installed
2. Python 3.11+
3. Docker Desktop installed
4. VS Code (optional but recommended)

### Installation
```
# 1. Clone/navigate to project
cd ~/Documents/DET

# 2. Create Python virtual environment
python3.11 -m venv det_env
source det_env/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Start FIWARE for the first time
docker compose up -d

# 5. Create initial Digital Twin entities
python src/digital_twin/create_robot.py
python src/digital_twin/create_paths.py

# 6. Verify everything works
python src/digital_twin/inspect_dt.py
```
---

## 🚀 Daily Startup Guide

**Follow these steps EVERY TIME you start working:**

### Step 1: Start Docker Desktop

```
# Option A: Launch Docker Desktop app
# Press Cmd+Space → type "Docker" → Enter
# Wait until the whale icon 🐳 in top-right turns GREEN (1-2 min)

# Option B: Check if Docker is already running
docker ps
```
#### Expected output: 
ist of running containers (or empty if none running)

If error: Docker is not running → Launch Docker Desktop app


### Step 2: Start FIWARE Services
```
cd ~/Documents/DET

# Start FIWARE (Orion Context Broker + MongoDB)
docker compose up -d
```
#### Expected output:
```
✔ Container det-mongo   Started
✔ Container det-orion   Started
```
#### Verify FIWARE is running:
```
curl http://localhost:1026/version
```
Expected: JSON response with FIWARE version

---

### Step 3: Activate Python Environment
```
cd ~/Documents/DET

# Activate virtual environment
source det_env/bin/activate
```
#### Expected: 
Your prompt should now show (det_env) at the beginning

### Step 4: Verify Digital Twin Status
```
# Check what entities exist in FIWARE
python src/digital_twin/inspect_dt.py
```
If entities are missing, recreate them:
```
python src/digital_twin/create_robot.py
python src/digital_twin/create_paths.py
```

---

## 🛠️ Common Commands

**Docker Management**
```
# Start FIWARE services
docker compose up -d

# Stop FIWARE services (keeps data)
docker compose down

# Stop and remove all data (CAUTION!)
docker compose down -v

# View logs
docker compose logs orion
docker compose logs mongo

# Check running containers
docker ps

# Restart FIWARE
docker compose restart
```
**Digital twin Operations**
```
# Activate Python environment (ALWAYS DO THIS FIRST)
source det_env/bin/activate

# View current Digital Twin state
python src/digital_twin/inspect_dt.py

# Recreate robot
python src/digital_twin/create_robot.py

# Recreate paths
python src/digital_twin/create_paths.py

# Delete specific entity
curl -X DELETE http://localhost:1026/ngsi-ld/v1/entities/urn:ngsi-ld:Robot:omron_01
curl -X DELETE http://localhost:1026/ngsi-ld/v1/entities/urn:ngsi-ld:Path:route_A
curl -X DELETE http://localhost:1026/ngsi-ld/v1/entities/urn:ngsi-ld:Path:route_B
curl -X DELETE http://localhost:1026/ngsi-ld/v1/entities/urn:ngsi-ld:Waypoint:storage_B

# List all entities (by type)
curl "http://localhost:1026/ngsi-ld/v1/entities?type=MobileRobot"
curl "http://localhost:1026/ngsi-ld/v1/entities?type=NavigationPath"
```

**Python Environment**
```
# Activate environment
source det_env/bin/activate

# Deactivate environment
deactivate

# Install new package
pip install package_name
pip freeze > requirements.txt

# Update all packages
pip list --outdated
pip install --upgrade package_name
```