"""Serve only this local demo directory, never the repository or its credentials."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __name__ == "__main__":
    directory = str(Path(__file__).resolve().parent)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 8088), partial(SimpleHTTPRequestHandler, directory=directory)
    )
    print("Mount Hua demo: http://127.0.0.1:8088", flush=True)
    server.serve_forever()
