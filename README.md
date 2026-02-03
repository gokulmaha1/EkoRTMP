# RTMP Broadcaster with Live HTML Overlays

This application uses GStreamer, Python, and WebKit to stream video with live HTML overlays to an RTMP destination (like YouTube, Twitch, or your own server).
It features a modern web-based dashboard to control the stream and update overlays in real-time.

## Project Structure
- `main.py`: Core application logic using GStreamer and GTK.
- `overlay.html` & `style.css`: The HTML overlay content. Modify these to change the look of your overlay.
- `Dockerfile`: Instructions to build the Linux environment with all dependencies.

## Deployment on Hostinger VPS

### 1. Prerequisites
Ensure your VPS has Docker installed.
```bash
sudo apt update
sudo apt install docker.io
```

### 2. Setup on Server
SSH into your VPS and clone the repository:
```bash
git clone https://github.com/gokulmaha1/EkoRTMP.git
cd EkoRTMP
```

### 3. Build Docker Image
Run the following command in the project directory:
```bash
sudo docker build -t rtmp-broadcaster .
```

### 4. Run the Broadcaster
You need to specify the RTMP URL where you want to stream.

### 4. Run the Broadcaster
You need to specify the RTMP URL where you want to stream.

```bash
sudo docker run -d \
  --name broadcaster \
  -p 8123:8123 \
  rtmp-broadcaster
```

### 5. Access the Dashboard
Open your browser and navigate to:
`http://YOUR_VPS_IP:8123`

### 6. Customization
- **Overlay**: The overlay is now managed via the dashboard.
- **Pipeline**: Edit `main.py` if you want to change the video source.

## Troubleshooting
If the stream doesn't start, check logs:
```bash
sudo docker logs broadcaster
```
- Ensure port 8123 is allowed in your VPS firewall.
