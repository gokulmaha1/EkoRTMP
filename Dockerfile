FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
# We need:
# - python3, pip
# - GStreamer and plugins
# - GTK3 and WebKit2GTK (for rendering HTML)
# - GObject introspection data
# - Xvfb (for headless display)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    gir1.2-webkit2-4.0 \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    libcairo2-dev \
    libgirepository1.0-dev \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY . .

# Environment variables for GStreamer and Display
ENV GST_DEBUG=2
ENV DISPLAY=:99

# Entrypoint script to handle Xvfb
RUN echo '#!/bin/bash\n\
    rm -f /tmp/.X99-lock\n\
    Xvfb :99 -screen 0 1280x720x24 > /dev/null 2>&1 &\n\
    exec uvicorn server:app --host 0.0.0.0 --port 8123' > /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8123

ENTRYPOINT ["/entrypoint.sh"]
