#!/usr/bin/env python3
"""Aggregate 'updates available' counts from the per-host WUD instances into a
single JSON summary for a Homepage customapi tile. Only LAN-reachable hosts are
polled (the Pi's WUD is Tailscale-only and unreachable from the cluster)."""
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOSTS = {
    "mediaserver": "http://192.168.86.10:3000",
    "nas": "http://192.168.86.12:3001",
    "thor": "http://192.168.86.11:3001",
}
PORT = 8080


def fetch(base):
    try:
        req = urllib.request.Request(
            base + "/api/containers?updateAvailable=true",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.load(r)
        return data if isinstance(data, list) else []
    except Exception:
        return None


def summary():
    out = {"total": 0, "containers": [], "errors": []}
    for host, base in HOSTS.items():
        items = fetch(base)
        if items is None:
            out[host] = -1
            out["errors"].append(host)
            continue
        out[host] = len(items)
        out["total"] += len(items)
        for c in items:
            name = c.get("displayName") or c.get("name") or "?"
            out["containers"].append(f"{host}/{name}")
    return out


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/healthz"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        body = json.dumps(summary()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
