#!/usr/bin/env python3
# run.py — entry point for the Web Synth
# Usage: python3 run.py

import threading
import time

from backend.api import app, start_audio, stop_audio

if __name__ == '__main__':
    def run_server():
        app.run(host='0.0.0.0', port=8000, threaded=True)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print('Flask server running at http://localhost:8000')

    start_audio()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print('Shutting down...')
        stop_audio()
