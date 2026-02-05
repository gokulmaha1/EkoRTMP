import requests
import os

url = "https://github.com/google/fonts/raw/main/ofl/notosanstamil/NotoSansTamil-Bold.ttf"
output_path = "media/NotoSansTamil-Bold.ttf"

if not os.path.exists("media"):
    os.makedirs("media")

print(f"Downloading font from {url}...")
try:
    response = requests.get(url)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(response.content)
    print(f"Reference: Font saved to {output_path} ({len(response.content)} bytes)")
except Exception as e:
    print(f"Error: {e}")
