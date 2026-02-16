
import sys
import os

print(f"Python Executable: {sys.executable}")
print(f"Version: {sys.version}")

def check_import(module_name):
    try:
        __import__(module_name)
        print(f"[OK] {module_name}")
    except ImportError as e:
        print(f"[FAIL] {module_name}: {e}")
    except Exception as e:
        print(f"[ERROR] {module_name}: {e}")

modules = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "pydantic",
    "dotenv",
    "requests",
    "feedparser",
    "bs4",
    "gi",
    "cairo"
]

print("--- Checking Imports ---")
for m in modules:
    check_import(m)

print("--- Checking Local Modules ---")
try:
    import database
    print("[OK] database")
except Exception as e:
    print(f"[FAIL] database: {e}")

try:
    import services.youtube_service
    print("[OK] services.youtube_service")
except Exception as e:
    print(f"[FAIL] services.youtube_service: {e}")

try:
    import services.news_fetcher
    print("[OK] services.news_fetcher")
except Exception as e:
    print(f"[FAIL] services.news_fetcher: {e}")
