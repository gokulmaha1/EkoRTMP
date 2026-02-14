import sys
import os
import signal
import threading
import gi
import cairo

gi.require_version('Gst', '1.0')
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.0')

print("DEBUG: main.py is starting...", flush=True)

import time
import json
import urllib.request
from gi.repository import Gst, Gtk, GObject, WebKit2, GLib, Gdk

# Initialize GStreamer and GTK
Gst.init(None)

# Configuration
WIDTH = 1280
HEIGHT = 720
RTMP_URL = os.environ.get('RTMP_URL', 'rtmp://localhost/live/test')
FRAMERATE = 20

class StreamOverlayApp:
    def __init__(self):
        self.mainloop = GLib.MainLoop()
        
        # --- shared state for overlay ---
        self.surface_lock = threading.Lock()
        self.current_surface = None
        self.img_surface = None
        self.img_ctx = None
        self.last_heartbeat = time.time()
        
        # --- Program Schedule State ---
        self.current_program_id = None
        self.program_bin = None
        self.api_base = "http://127.0.0.1:8123/api"
        
        # --- WebKit Setup (Headless) ---
        self.window = Gtk.OffscreenWindow()
        self.window.set_default_size(WIDTH, HEIGHT)
        
        self.webview = WebKit2.WebView()
        
        # Configure WebView Settings
        settings = self.webview.get_settings()
        settings.set_enable_write_console_messages_to_stdout(True) # Debugging
        settings.set_enable_developer_extras(True)
        settings.set_enable_webgl(True)
        # Spoof a standard browser User-Agent to avoid being blocked
        settings.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        settings.set_media_playback_requires_user_gesture(False) # Allow autoplay
        self.webview.set_settings(settings)
        
        self.webview.set_background_color(Gdk.RGBA(0, 0, 0, 0)) # Transparent background
        self.window.add(self.webview)
        
        # Load overlay
        overlay_url = os.environ.get('OVERLAY_URL')
        if not overlay_url:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            html_path = os.path.join(current_dir, 'overlay.html')
            overlay_url = f'file://{html_path}'
        
        print(f"Loading overlay from: {overlay_url}")
        self.webview.load_uri(overlay_url)
        
        self.window.show_all()
        
        # Start a timer to snapshot the webview
        GLib.timeout_add(1000 // FRAMERATE, self.update_surface)
        
        # Start Schedule Poller
        GLib.timeout_add_seconds(5, self.check_schedule)

        # --- GStreamer Pipeline ---
        # We use input-selectors to switch between Default (Pad 0) and Program (Pad 1)
        
        BACKUP_RTMP_URL = os.environ.get('BACKUP_RTMP_URL')
        
        sink_pipeline = ""
        if BACKUP_RTMP_URL:
            # print(f"Configuring Dual Stream: Primary + Backup")
            sink_pipeline = (
                f'flvmux name=mux streamable=true ! tee name=t '
                f't. ! queue ! rtmpsink location="{RTMP_URL}" '
                f't. ! queue ! rtmpsink location="{BACKUP_RTMP_URL}" '
            )
        else:
            sink_pipeline = (
                f'flvmux name=mux streamable=true ! rtmpsink location="{RTMP_URL}" '
            )

        # --- VIDEO BRANCH ---
        # Selector 0: Default Black
        # Selector 1: Program Video (Dynamic)
        video_pipeline = (
            f'input-selector name=vsel ! '
            f'videoconvert ! cairooverlay name=overlay ! videoconvert ! queue ! '
            f'x264enc bitrate=2500 tune=zerolatency speed-preset=ultrafast key-int-max=40 threads=3 ! queue ! mux. '
            
            # Default Source (Pad 0) connected to vsel
            f'videotestsrc pattern=black ! video/x-raw,width={WIDTH},height={HEIGHT},framerate={FRAMERATE}/1 ! '
            f'videoconvert ! vsel.sink_0 '
        )
        
        # --- AUDIO BRANCH ---
        # We use audiomixer to mix Background Music and TTS
        # Selector 0: Default Mix (Music + TTS)
        # Selector 1: Program Audio (Dynamic)
        
        # Audio Mixer Construction
        # Pad 0: Music (Background)
        # Pad 1: TTS (Announcement)
        audio_mix_pipeline = (
            f'audiomixer name=amix ! '
            f'voaacenc bitrate=128000 ! mux. '
        )
        
        # Music Source (Pad 0 of Mixer)
        music_file = "news-music-2025-335894.mp3"
        if os.path.exists(music_file):
            # print(f"Found background music: {music_file}")
            audio_source = (
                f'multifilesrc location="{music_file}" loop=true ! '
                'decodebin ! audioconvert ! audioresample ! audio/x-raw,rate=44100,channels=2 ! '
                'volume name=vol_music volume=1.0 ! amix.sink_0 '
            )
        else:
            audio_source = (
                'audiotestsrc wave=silence ! audio/x-raw,rate=44100,channels=2 ! '
                'volume name=vol_music volume=1.0 ! amix.sink_0 '
            )
            
        # TTS Source (Pad 1 of Mixer) - Initially silence/waiting
        # We don't keep a live source open, we just want the pad ready?
        # Typically we dynamically link/unlink or use a latch.
        # Simplest: Input-selector for the Whole Audio Branch? 
        # No, we want mixing.
        # So we leave amix.sink_1 open (or request it dynamically).
        
        # Let's wrap the mix in an input-selector branch so we can switch to Program Audio totally.
        # Selector 0: The Mixer (Music + TTS)
        # Selector 1: Program Audio
        
        audio_pipeline = (
            f'input-selector name=asel ! '
            f'voaacenc bitrate=128000 ! mux. '
            
            # Branch 0: Mixer
            f'audiomixer name=amix ! asel.sink_0 '
        )
        
        # Determine Music Source string again for clarity
        if os.path.exists(music_file):
             audio_source_0 = (
                f'multifilesrc location="{music_file}" loop=true ! '
                'decodebin ! audioconvert ! audioresample ! audio/x-raw,rate=44100,channels=2 ! '
                'volume name=vol_music volume=1.0 ! amix.sink_0 '
            )
        else:
            audio_source_0 = (
                'audiotestsrc wave=silence ! audio/x-raw,rate=44100,channels=2 ! '
                'volume name=vol_music volume=1.0 ! amix.sink_0 '
            )

        pipeline_str = sink_pipeline + video_pipeline + audio_pipeline + audio_source_0
        
        print(f"Starting pipeline...")
        self.pipeline = Gst.parse_launch(pipeline_str)
        
        self.vsel = self.pipeline.get_by_name('vsel')
        self.asel = self.pipeline.get_by_name('asel')
        self.amix = self.pipeline.get_by_name('amix')
        self.vol_music = self.pipeline.get_by_name('vol_music')
        
        self.overlay = self.pipeline.get_by_name('overlay')
        self.overlay.connect('draw', self.on_draw)
        
        # Bus handling
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.on_message)

        # TTS State
        self.tts_bin = None
        self.last_tts_timestamp = 0
        self.tts_trigger_file = "tts_trigger.json"
        
        # Start TTS Poller
        GLib.timeout_add(1000, self.check_tts_trigger)

    def check_tts_trigger(self):
        # Don't interrupt Program
        if self.current_program_id is not None:
            return True
            
        try:
            if os.path.exists(self.tts_trigger_file):
                with open(self.tts_trigger_file, 'r') as f:
                    data = json.load(f)
                    
                ts = data.get('timestamp', 0)
                if ts > self.last_tts_timestamp:
                    self.last_tts_timestamp = ts
                    file_path = data.get('file')
                    if file_path and os.path.exists(file_path):
                        self.play_tts(file_path)
        except Exception as e:
            print(f"TTS Check failed: {e}")
            
        return True

    def play_tts(self, file_path):
        print(f"Playing TTS: {file_path}")
        
        # Duck Music
        if self.vol_music:
            self.vol_music.set_property("volume", 0.05)
            
        # Create TTS Bin if previous one exists (cleanup?)
        if self.tts_bin:
            self.tts_bin.set_state(Gst.State.NULL)
            self.pipeline.remove(self.tts_bin)
            self.tts_bin = None
            
        # New Bin
        # file -> decode -> convert -> resample -> volume -> amix.sink_1
        self.tts_bin = Gst.Bin.new("tts_bin")
        
        uri = f"file:///{file_path.replace(os.sep, '/')}"
        
        source = Gst.ElementFactory.make("uridecodebin")
        source.set_property("uri", uri)
        source.connect("pad-added", self.on_tts_pad_added)
        
        self.tts_bin.add(source)
        self.pipeline.add(self.tts_bin)
        self.tts_bin.set_state(Gst.State.PLAYING)

    def on_tts_pad_added(self, source, new_pad):
        # Link TTS to Mixer sink_1
        new_pad_caps = new_pad.query_caps(None)
        new_pad_struct = new_pad_caps.get_structure(0)
        new_pad_name = new_pad_struct.get_name()
        
        if new_pad_name.startswith("audio"):
            convert = Gst.ElementFactory.make("audioconvert")
            resample = Gst.ElementFactory.make("audioresample")
            vol = Gst.ElementFactory.make("volume")
            vol.set_property("volume", 1.5) # Boost TTS slightly
            
            self.tts_bin.add(convert)
            self.tts_bin.add(resample)
            self.tts_bin.add(vol)
            
            convert.sync_state_with_parent()
            resample.sync_state_with_parent()
            vol.sync_state_with_parent()
            
            # Logic: source -> convert -> resample -> vol -> amix.sink_1
            new_pad.link(convert.get_static_pad("sink"))
            convert.link(resample)
            resample.link(vol)
            
            src_pad = vol.get_static_pad("src")
            sink_pad = self.amix.get_request_pad("sink_%u")
            
            if sink_pad:
                 src_pad.link(sink_pad)
                 sink_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, self.on_tts_event, None)
            else:
                print("Failed to get amix sink pad")

    def on_tts_event(self, pad, info, user_data):
        event = info.get_event()
        if event.type == Gst.EventType.EOS:
            print("TTS Finished (EOS)")
            # Restore Music Volume
            GLib.idle_add(self.restore_music_volume)
        return Gst.PadProbeReturn.OK

    def restore_music_volume(self):
        if self.vol_music:
            self.vol_music.set_property("volume", 1.0)
        
        # Cleanup TTS bin
        if self.tts_bin:
            self.tts_bin.set_state(Gst.State.NULL)
            self.pipeline.remove(self.tts_bin)
            self.tts_bin = None
        return False


    def check_schedule(self):
        try:
            with urllib.request.urlopen(f"{self.api_base}/programs/current", timeout=2) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode())
                    if data and 'id' in data:
                        # Found active program
                        if self.current_program_id != data['id']:
                            self.start_program(data)
                    else:
                        # No active program
                        if self.current_program_id is not None:
                            self.stop_program()
                else:
                    if self.current_program_id is not None:
                        self.stop_program()
        except Exception as e:
            print(f"Schedule Check Error: {e}")
            
        return True

    def start_program(self, data):
        print(f"Starting Program: {data['title']} (ID: {data['id']})")
        self.current_program_id = data['id']
        
        # Construct path (handle relative media)
        video_path = data['video_path']
        if not os.path.isabs(video_path):
            video_path = os.path.abspath(video_path)
        
        uri = f"file:///{video_path.replace(os.sep, '/')}"
        
        # Create Dynamic Bin
        self.program_bin = Gst.Bin.new("program_bin")
        
        # URIDecodeBin
        source = Gst.ElementFactory.make("uridecodebin", "source")
        source.set_property("uri", uri)
        source.connect("pad-added", self.on_pad_added)
        
        self.program_bin.add(source)
        self.pipeline.add(self.program_bin)
        
        # Sync state
        self.program_bin.set_state(Gst.State.PLAYING)
        
        # Switch Selectors (Optimistic switch)
        # Note: If decode fails, we might get silence/black.
        pad0 = self.vsel.get_static_pad("sink_1")
        self.vsel.set_property("active-pad", pad0)
        
        apad0 = self.asel.get_static_pad("sink_1")
        self.asel.set_property("active-pad", apad0)
        
        # Notify Overlay (optional, hiding overlays done via API usually, but we can enforce)
        # For now, we leave overlays ON (Ticker over video is common)

    def stop_program(self):
        print("Stopping Program")
        self.current_program_id = None
        
        # Switch back to default
        pad0 = self.vsel.get_static_pad("sink_0")
        self.vsel.set_property("active-pad", pad0)
        
        apad0 = self.asel.get_static_pad("sink_0")
        self.asel.set_property("active-pad", apad0)
        
        # Cleanup Bin
        if self.program_bin:
            self.program_bin.set_state(Gst.State.NULL)
            self.pipeline.remove(self.program_bin)
            self.program_bin = None

    def on_pad_added(self, source, new_pad):
        # Link dynamic pads to selectors
        new_pad_caps = new_pad.query_caps(None)
        new_pad_struct = new_pad_caps.get_structure(0)
        new_pad_type = new_pad_struct.get_name()
        
        if new_pad_type.startswith("video"):
            # Ensure format compatibility
            # source -> videoconvert -> videoscale -> caps -> vsel.sink_1
            convert = Gst.ElementFactory.make("videoconvert")
            scale = Gst.ElementFactory.make("videoscale")
            capsfilter = Gst.ElementFactory.make("capsfilter")
            caps = Gst.Caps.from_string(f"video/x-raw,width={WIDTH},height={HEIGHT}")
            capsfilter.set_property("caps", caps)
            
            self.program_bin.add(convert)
            self.program_bin.add(scale)
            self.program_bin.add(capsfilter)
            
            convert.sync_state_with_parent()
            scale.sync_state_with_parent()
            capsfilter.sync_state_with_parent()
            
            # Internal Links
            new_pad.link(convert.get_static_pad("sink"))
            convert.link(scale)
            scale.link(capsfilter)
            
            # External Link to Selector
            src_pad = capsfilter.get_static_pad("src")
            sink_pad = self.vsel.get_request_pad("sink_%u") # Use request pad or static? input-selector has sometimes sink_%u
            # Actually input-selector usually has sink_%u request pads, but we manually used sink_0 in string.
            # sink_1 might not exist until requested?
            # GStreamer parse_launch might create sink_0 and sink_1 if referenced? No, sink_0 was referenced.
            # Let's request a pad.
            
            # Wait, in the pipeline string string I didn't reference vsel.sink_1.
            # So I should request a pad.
            # BUT I need to know it is index 1 for switching?
            # input-selector pads have a 'always-ok' property? No.
            # We used set_property("active-pad", pad).
            
            # If I request, I get sink_1?
            # sink_pad = self.vsel.get_compat_pad(sink_1)? 
            
            # Let's get static first?
            sink_pad = self.vsel.get_static_pad("sink_1")
            if not sink_pad:
                sink_pad = self.vsel.get_request_pad("sink_%u")
            
            if sink_pad:
                src_pad.link(sink_pad)
            else:
                print("Failed to get video sink pad")

        elif new_pad_type.startswith("audio"):
            # source -> audioconvert -> audioresample -> asel.sink_1
            convert = Gst.ElementFactory.make("audioconvert")
            resample = Gst.ElementFactory.make("audioresample")
            
            self.program_bin.add(convert)
            self.program_bin.add(resample)
            
            convert.sync_state_with_parent()
            resample.sync_state_with_parent()
            
            new_pad.link(convert.get_static_pad("sink"))
            convert.link(resample)
            
            src_pad = resample.get_static_pad("src")
            sink_pad = self.asel.get_static_pad("sink_1")
            if not sink_pad:
                sink_pad = self.asel.get_request_pad("sink_%u")
                
            if sink_pad:
                src_pad.link(sink_pad)

    def update_surface(self):
        # This runs in the main GTK thread
        surface = self.window.get_surface()
        if surface:
            # Reuse surface to reduce memory allocation churn
            if self.img_surface is None:
                try:
                    self.img_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
                    self.img_ctx = cairo.Context(self.img_surface)
                except Exception as e:
                    print(f"Error creating surface: {e}")
                    return True

            with self.surface_lock:
                if self.img_ctx:
                    self.img_ctx.set_source_surface(surface, 0, 0)
                    self.img_ctx.paint()
                    self.current_surface = self.img_surface
        
        # Heartbeat check (every 5 seconds)
        now = time.time()
        if now - self.last_heartbeat > 5.0:
            print(f"[HEARTBEAT] Stream active. Memory optimized.", flush=True)
            self.last_heartbeat = now
            
        return True # Keep calling

    def on_draw(self, overlay, context, timestamp, duration):
        # This runs in the GStreamer streaming thread
        with self.surface_lock:
            if self.current_surface:
                context.set_source_surface(self.current_surface, 0, 0)
                context.paint()
            else:
                # Debug: Draw a red rectangle if no surface yet
                context.set_source_rgba(1, 0, 0, 0.5)
                context.rectangle(100, 100, 200, 200)
                context.fill()

    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("End of stream")
            # If loading a file, EOS might trigger?
            # We should probably handle EOS from program_bin separately?
            # But the bus is shared.
            # If EOS comes from program_bin, we should loop or stop?
            # For now, simplistic approach: ignore EOS from files (loop handled by uridecodebin? no)
            pass 
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, {debug}")
            # self.mainloop.quit() # detailed error handling needed
        elif t == Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            print(f"Warning: {err}, {debug}")
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending_state = message.parse_state_changed()
                print(f"Pipeline state changed from {old_state.value_nick} to {new_state.value_nick}")

    def run(self):
        self.pipeline.set_state(Gst.State.PLAYING)
        try:
            self.mainloop.run()
        except KeyboardInterrupt:
            pass
        finally:
            self.pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    app = StreamOverlayApp()
    app.run()
