import os
import sys
import subprocess
import requests
import json
import time

# --- CONFIGURATION ---
APP_FILENAME = "app.py"
ASSETS_DIR = "assets"
GEOJSON_FILE = "india_states.geojson"
GEOJSON_URL = "https://raw.githubusercontent.com/Subhash9325/GeoJson-Data-of-Indian-States/master/Indian_States"

def print_status(message, status="INFO"):
    colors = {
        "INFO": "\033[94m",    # Blue
        "SUCCESS": "\033[92m", # Green
        "WARNING": "\033[93m", # Yellow
        "ERROR": "\033[91m",   # Red
        "RESET": "\033[0m"
    }
    print(f"{colors.get(status, '')}[{status}] {message}{colors['RESET']}")

def check_and_download_assets():
    """
    Checks if the assets folder and GeoJSON map exist.
    If not, downloads them automatically.
    """
    # 1. Create Assets Directory
    if not os.path.exists(ASSETS_DIR):
        print_status(f"Creating directory: {ASSETS_DIR}", "INFO")
        os.makedirs(ASSETS_DIR)

    # 2. Check for Map File
    map_path = os.path.join(ASSETS_DIR, GEOJSON_FILE)
    if not os.path.exists(map_path):
        print_status("GeoJSON map not found. Downloading...", "WARNING")
        try:
            response = requests.get(GEOJSON_URL)
            if response.status_code == 200:
                with open(map_path, 'w', encoding='utf-8') as f:
                    json.dump(response.json(), f)
                print_status(f"Map downloaded successfully: {map_path}", "SUCCESS")
            else:
                print_status(f"Failed to download map. HTTP {response.status_code}", "ERROR")
        except Exception as e:
            print_status(f"Download error: {e}", "ERROR")
    else:
        print_status("Map assets verified.", "SUCCESS")

def run_streamlit_app():
    """
    Launches the Streamlit application using subprocess.
    """
    if not os.path.exists(APP_FILENAME):
        print_status(f"Critical Error: {APP_FILENAME} not found in current directory.", "ERROR")
        return

    print_status("Initializing UIDAI Insight Engine...", "INFO")
    time.sleep(1) # Dramatic pause for effect
    
    cmd = [sys.executable, "-m", "streamlit", "run", APP_FILENAME]
    
    try:
        print_status(f"Launching on local server...", "SUCCESS")
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print_status("\nApp stopped by user.", "WARNING")
    except Exception as e:
        print_status(f"Failed to launch app: {e}", "ERROR")

if __name__ == "__main__":
    print("--------------------------------------------------")
    print("   🇮🇳  UIDAI INSIGHT ENGINE LAUNCHER  🇮🇳   ")
    print("--------------------------------------------------")
    
    check_and_download_assets()
    print("--------------------------------------------------")
    run_streamlit_app()