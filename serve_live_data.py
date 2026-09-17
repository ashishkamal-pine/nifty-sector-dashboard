"""
serve_live_data.py
-------------------
Serves live_data.json on http://localhost:8765/live_data.json so the web app
(Sector_Performance_Board.html) can poll it automatically.

Run this alongside fyers_sync.py (in a second terminal), then in the web app
enter http://localhost:8765/live_data.json into the "Live source URL" field.

    python3 serve_live_data.py
"""

import http.server
import socketserver

PORT = 8765


class CORSHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # keep the console quiet; fyers_sync.py already logs


if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), CORSHandler) as httpd:
        print(f"Serving live_data.json at http://localhost:{PORT}/live_data.json")
        print("Leave this running alongside fyers_sync.py. Ctrl+C to stop.")
        httpd.serve_forever()
