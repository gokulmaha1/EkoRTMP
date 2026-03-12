#!/bin/bash
rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1280x720x24 > /dev/null 2>&1 &
exec uvicorn server:app --host 0.0.0.0 --port 8123
