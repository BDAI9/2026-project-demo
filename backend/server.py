"""Local, single-process demo server: python -m backend.server."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit

from backend.app.service import search_courses
from backend.app.team_integration import interpret, recommend


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
STATIC = {"/": ("team.html", "text/html"), "/team.js": ("team.js", "text/javascript"),
          "/team.css": ("team.css", "text/css"), "/date-demo": ("index.html", "text/html"),
          "/app.js": ("app.js", "text/javascript"), "/styles.css": ("styles.css", "text/css")}
MAX_BODY_BYTES = 16_384


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Avoid writing location queries or credentials to a local terminal log.
        pass

    def _local_request(self):
        port = self.server.server_port
        host = self.headers.get("Host", "")
        allowed = {f"localhost:{port}", f"127.0.0.1:{port}"}
        if host not in allowed:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{h}" for h in allowed}

    def _send(self, status, content, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status, value):
        self._send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        if not self._local_request():
            return self._json(403, {"message": "허용되지 않은 요청입니다."})
        entry = STATIC.get(urlsplit(self.path).path)
        if entry is None:
            return self._json(404, {"message": "페이지를 찾을 수 없습니다."})
        path = FRONTEND / entry[0]
        try:
            content = path.read_bytes()
        except OSError:
            return self._json(503, {"message": "화면 파일을 찾을 수 없습니다."})
        return self._send(200, content, entry[1] + "; charset=utf-8")

    def do_POST(self):
        if not self._local_request():
            return self._json(403, {"message": "허용되지 않은 요청입니다."})
        routes = {"/api/search": search_courses, "/api/interpret": interpret, "/api/team-search": recommend}
        if self.path not in routes:
            return self._json(404, {"message": "요청 경로를 찾을 수 없습니다."})
        if self.headers.get_content_type() != "application/json":
            return self._json(415, {"message": "JSON 요청이 필요합니다."})
        try:
            size = int(self.headers.get("Content-Length", ""))
            if size < 1 or size > MAX_BODY_BYTES:
                raise ValueError
            payload = json.loads(self.rfile.read(size))
            result = routes[self.path](payload)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return self._json(400, {"status": "error", "message": "입력한 지역, 순서, 예산과 거리를 확인해 주세요.", "courses": []})
        except Exception:
            return self._json(500, {"status": "error", "message": "결과를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.", "courses": []})
        return self._json(200, result)


def main():
    parser = argparse.ArgumentParser(description="Local date-course demo")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Open http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
