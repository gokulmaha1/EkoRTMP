import sys
import os
import signal
import threading
import gi
import cairo

gi.require_version('Gst', '1.0')
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.0')

from gi.repository import Gst, Gtk, GObject, WebKit2, GLib

# Initialize GStreamer and GTK
Gst.init(None)

# Configuration
WIDTH = 1280
HEIGHT = 720
RTMP_URL = os.environ.get('RTMP_URL', 'rtmp://localhost/live/test')
FRAMERATE = 30

class StreamOverlayApp:
    def __init__(self):
        self.mainloop = Gtk.MainLoop()
        
        # --- shared state for overlay ---
        self.surface_lock = threading.Lock()
        self.current_surface = None
        
        # --- WebKit Setup (Headless) ---
        self.window = Gtk.OffscreenWindow()
        self.window.set_default_size(WIDTH, HEIGHT)
        
        self.webview = WebKit2.WebView()
        self.webview.set_background_color(Gtk.gdk.RGBA(0, 0, 0, 0)) # Transparent background
        self.window.add(self.webview)
        
        # Load local HTML file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, 'overlay.html')
        self.webview.load_uri(f'file://{html_path}')
        
        self.window.show_all()
        
        # Start a timer to snapshot the webview
        GLib.timeout_add(1000 // FRAMERATE, self.update_surface)

        # --- GStreamer Pipeline ---
        # Using videotestsrc as base. In production, this might be rtspsrc or filesrc.
        # We blend the cairooverlay on top.
        pipeline_str = (
            f'videotestsrc pattern=ball ! video/x-raw,width={WIDTH},height={HEIGHT},framerate={FRAMERATE}/1 ! '
            'videoconvert ! '
            'cairooverlay name=overlay ! '
            'videoconvert ! '
            'x264enc bitrate=2000 tune=zerolatency speed-preset=veryfast ! '
            'flvmux ! '
            f'rtmpsink location="{RTMP_URL}"'
        )
        
        print(f"Starting pipeline: {pipeline_str}")
        self.pipeline = Gst.parse_launch(pipeline_str)
        
        # Connect to cairooverlay draw signal
        self.overlay = self.pipeline.get_by_name('overlay')
        self.overlay.connect('draw', self.on_draw)
        
        # Bus handling
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.on_message)

    def update_surface(self):
        # This runs in the main GTK thread
        # We get the surface from the OffscreenWindow
        surface = self.window.get_surface()
        if surface:
            # We must copy it because the window surface might change while we draw
            # in the other thread. 
            # Or simpler: create an ImageSurface and paint the window surface to it.
            img_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
            ctx = cairo.Context(img_surface)
            ctx.set_source_surface(surface, 0, 0)
            ctx.paint()
            
            with self.surface_lock:
                self.current_surface = img_surface
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
            self.mainloop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, {debug}")
            self.mainloop.quit()

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
