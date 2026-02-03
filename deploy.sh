#!/bin/bash

echo "🚀 Deploying Stream Broadcaster..."

# 1. Stop and remove existing container (suppress errors if it doesn't exist)
echo "🛑 Stopping old container..."
sudo docker rm -f broadcaster || true

# 2. Pull latest code
echo "⬇️ Pulling latest code..."
git pull

# 3. Build image
echo "🔨 Building Docker image..."
sudo docker build -t rtmp-broadcaster .

# 4. Run new container
echo "▶️ Starting new container on port 8123..."
sudo docker run -d \
  --name broadcaster \
  -p 8123:8123 \
  --restart unless-stopped \
  rtmp-broadcaster

echo "✅ Deployment Complete! Access at http://$(curl -s ifconfig.me):8123"
