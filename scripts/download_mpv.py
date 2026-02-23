import urllib.request
import json
import py7zr
import os
import shutil

api_url = "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest"

try:
    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        
    assets = data.get("assets", [])
    download_url = None
    for asset in assets:
        name = asset.get("name", "")
        # Look for the dev build 7z containing the libmpv dll
        if "dev" in name and "x86_64" in name and name.endswith(".7z") and "v3" not in name:
            download_url = asset.get("browser_download_url")
            break
            
    if not download_url:
        print("Could not find a valid latest x86_64 7z release")
        exit(1)
        
    print(f"Found latest release: {download_url}")
    print("Downloading...")
    urllib.request.urlretrieve(download_url, "mpv_dl.7z")
    
    os.makedirs("lib", exist_ok=True)
    
    print("Extracting using 7z.exe...")
    os.makedirs("lib", exist_ok=True)
    
    import subprocess
    seven_z_path = r"C:\Program Files\7-Zip\7z.exe"
        
    # Extract only mpv-2.dll flat into the lib folder
    subprocess.run([seven_z_path, 'e', 'mpv_dl.7z', '-o.', '*mpv-*.dll', '-r'], check=True)
    
    # Rename and move
    for f in os.listdir('.'):
        if f.endswith('.dll') and f.startswith('mpv-'):
            shutil.move(f, os.path.join("lib", "mpv-1.dll"))
            print(f"Extracted {f} -> lib/mpv-1.dll")
            break
            
    # cleanup
    os.remove("mpv_dl.7z")
    print("MPV DLL successfully downloaded and placed in lib/")
    
except Exception as e:
    print(f"Error fetching latest MPV: {e}")
