
import os
import sys
import urllib.request
import urllib.parse
import time

print("--- TTS Diagnostic Tool ---")

# 1. Check pyttsx3
print("\n[1] Testing pyttsx3...")
try:
    import pyttsx3
    print(f"pyttsx3 version: {pyttsx3.__version__}")
    engine = pyttsx3.init()
    output_file = "test_pyttsx3.wav"
    engine.save_to_file("Hello from pyttsx3", output_file)
    engine.runAndWait()
    if os.path.exists(output_file):
        print(f"SUCCESS: Generated {output_file}")
    else:
        print("FAILURE: File not created")
except ImportError:
    print("pyttsx3 not installed")
except Exception as e:
    print(f"pyttsx3 Error: {e}")

# 2. Check Google TTS (Direct URL)
print("\n[2] Testing Google TTS (Hack method)...")
try:
    text = "Hello from Google"
    text_enc = urllib.parse.quote(text)
    url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_enc}&tl=en&client=tw-ob"
    print(f"URL: {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    output_file = "test_google.wav"
    with urllib.request.urlopen(req) as response, open(output_file, 'wb') as out_file:
        out_file.write(response.read())
    
    if os.path.exists(output_file):
        print(f"SUCCESS: Generated {output_file}")
    else:
        print("FAILURE: File not created")
except Exception as e:
    print(f"Google TTS Error: {e}")

# 3. Check Coqui TCS
print("\n[3] Testing Coqui TTS...")
try:
    from TTS.api import TTS
    print("TTS library imported")
except ImportError:
    print("TTS library not installed")
except Exception as e:
    print(f"TTS Import Error: {e}")
