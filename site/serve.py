"""Loopback-only preview server with capacity for concurrent browser asset loads."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class PreviewServer(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True


class PreviewHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_request(self, code="-", size="-"):
        if str(code).isdigit() and int(code) >= 400:
            super().log_request(code, size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent / "dist"
    with PreviewServer(("127.0.0.1", args.port), partial(PreviewHandler, directory=str(directory))) as server:
        print(f"Showcase preview: http://127.0.0.1:{args.port}/TeoJansen_Rhinoceros/", flush=True)
        server.serve_forever()
