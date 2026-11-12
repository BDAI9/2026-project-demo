"""모임 장소 추천 서버.  실행: python -m moim  (같은 와이파이 공유: python -m moim --lan)

표준 라이브러리만 사용한다. 설정은 환경 변수 또는 저장소 루트의 .env 파일에서 읽는다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import options
from .eatpl import make_client
from .recommend import recommend, summarize
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
MAX_BODY = 16_384
STATIC = {
    "/": ("index.html", "text/html"),
    "/static/style.css": ("style.css", "text/css"),
    "/static/index.js": ("index.js", "text/javascript"),
    "/static/room.js": ("room.js", "text/javascript"),
}
ROOM_RE = re.compile(r"^/api/rooms/([A-Za-z0-9_-]{4,20})(/participants(?:/([A-Za-z0-9_-]{4,20}))?|/recommend)?$")


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """간단한 .env 읽기: KEY=VALUE 줄만. 이미 설정된 환경 변수는 덮어쓰지 않는다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _public(room: dict) -> dict:
    return {"id": room["id"], "title": room["title"], "participants": room["participants"],
            "summary": summarize(room["participants"])}


class App:
    def __init__(self, store: Store, client=None):
        self.store = store
        self.client = client or make_client(store)

    def handle(self, method: str, path: str, body):
        if method == "GET" and path == "/api/options":
            return 200, {**options.catalog(), "data_source": self.client.source}
        if method == "POST" and path == "/api/rooms":
            if not isinstance(body, dict) or set(body) - {"title"}:
                raise ValueError("입력 형식이 올바르지 않아요.")
            title = (body.get("title") or "").strip() or "우리 모임"
            if len(title) > 40:
                raise ValueError("모임 이름은 40자 이내로 입력해 주세요.")
            return 201, {"id": self.store.create_room(title)}

        m = ROOM_RE.match(path)
        if not m:
            return 404, {"message": "요청 경로를 찾을 수 없어요."}
        room_id, sub, pid = m.group(1), m.group(2), m.group(3)
        room = self.store.get_room(room_id)
        if room is None:
            return 404, {"message": "모임을 찾을 수 없어요. 링크를 확인해 주세요."}

        if sub is None and method == "GET":
            return 200, _public(room)
        if sub == "/participants" and method == "POST":
            data = options.validate_preference(body)
            new_id, token = self.store.add_participant(room_id, data)
            return 201, {"id": new_id, "token": token}
        if pid and method in ("PUT", "DELETE"):
            token = body.get("token") if isinstance(body, dict) else None
            if not isinstance(token, str):
                return 403, {"message": "수정 권한이 없어요."}
            if method == "DELETE":
                ok = self.store.delete_participant(room_id, pid, token)
            else:
                data = options.validate_preference({k: v for k, v in body.items() if k != "token"})
                ok = self.store.update_participant(room_id, pid, token, data)
            return (200, {"ok": True}) if ok else (403, {"message": "수정 권한이 없어요."})
        if sub == "/recommend" and method == "POST":
            body = body if isinstance(body, dict) else {}
            region, place_type = body.get("region"), body.get("place_type")
            if region is not None and (not isinstance(region, str) or len(region) > options.MAX_CUSTOM):
                raise ValueError("지역을 확인해 주세요.")
            return 200, recommend(room["participants"], self.client, self.store,
                                  region=region, place_type=place_type)
        return 405, {"message": "지원하지 않는 요청이에요."}


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 터미널에 개인 입력이 남지 않게
            pass

        def _send(self, status, content: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            self.end_headers()
            self.wfile.write(content)

        def _json(self, status, value):
            self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json")

        def do_GET(self):
            path = urlsplit(self.path).path
            if path.startswith("/r/"):
                path = "/room"
            if path == "/room":
                return self._send(200, (WEB / "room.html").read_bytes(), "text/html")
            if path in STATIC:
                name, ctype = STATIC[path]
                return self._send(200, (WEB / name).read_bytes(), ctype)
            self._dispatch("GET", path, None)

        def _with_body(self, method):
            if self.headers.get_content_type() != "application/json":
                return self._json(415, {"message": "JSON 요청이 필요해요."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size > MAX_BODY:
                    return self._json(413, {"message": "입력이 너무 커요."})
                body = json.loads(self.rfile.read(size)) if size else {}
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"message": "요청을 읽지 못했어요."})
            self._dispatch(method, urlsplit(self.path).path, body)

        def do_POST(self):
            self._with_body("POST")

        def do_PUT(self):
            self._with_body("PUT")

        def do_DELETE(self):
            self._with_body("DELETE")

        def _dispatch(self, method, path, body):
            try:
                status, value = app.handle(method, path, body)
            except ValueError as e:
                status, value = 400, {"message": str(e)}
            except Exception:
                status, value = 500, {"message": "서버 오류가 났어요. 잠시 후 다시 시도해 주세요."}
            self._json(status, value)

    return Handler


def lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="모임 장소 추천 서버")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--lan", action="store_true", help="같은 와이파이의 다른 기기에서도 접속 허용")
    parser.add_argument("--db", default=str(ROOT / "moim.sqlite3"))
    args = parser.parse_args()
    load_dotenv()
    app = App(Store(args.db))
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    server = ThreadingHTTPServer((host, args.port), make_handler(app))
    print(f"데이터: {'잇플 API' if app.client.source == 'eatpl' else '샘플(가상 가게)'}"
          f" · AI 추정: {'켜짐' if os.getenv('OPENROUTER_API_KEY') else '꺼짐(키 없음)'}")
    print(f"이 컴퓨터에서 열기: http://127.0.0.1:{args.port}/")
    if args.lan and lan_ip():
        print(f"같은 와이파이의 친구들은: http://{lan_ip()}:{args.port}/")
    print("끄려면 Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
