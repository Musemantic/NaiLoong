"""Loopback-only HTTP service for the zero-dependency browser data editor."""

from __future__ import annotations

import json
import mimetypes
import secrets
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlsplit

try:
    from .data_editor_ai import annotate
    from .data_editor_core import EditorError, git, project_metadata, scan_image_branch, with_baseline
    from .validate_data import validate_data
except ImportError:
    from data_editor_ai import annotate
    from data_editor_core import EditorError, git, project_metadata, scan_image_branch, with_baseline
    from validate_data import validate_data


TOOL_DIR = Path(__file__).resolve().parent.parent / "tools" / "data-editor"
SHA1 = re.compile(r"[0-9a-f]{40}\Z", re.IGNORECASE)
ROOT_STATIC = {
    "contribute.html", "docs.html", "assets/css/style.css", "assets/css/contribute.css",
    "assets/js/contribute.js", "assets/js/docs.js", "assets/js/md.js",
    "assets/icons/favicon.svg", "assets/placeholders/naiwa_laugh.gif",
}


def create_handler(root: Path, scans: dict, lock: threading.RLock):
    root = root.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "NaiLoongDataEditor/1"

        def log_message(self, _format, *_args):
            return

        def send_json(self, status: int, value: dict):
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def request_json(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise EditorError("请求长度无效。") from exc
            if length < 0 or length > 24 * 1024 * 1024:
                raise EditorError("请求超过本地工具允许的大小。")
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise EditorError("请求 JSON 格式无效。") from exc

        def same_origin(self):
            host = self.headers.get("Host", "")
            if host != self.server.server_address[0] + ":" + str(self.server.server_address[1]):
                return False
            origin = self.headers.get("Origin")
            return not origin or origin == f"http://{host}"

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/api/project":
                try:
                    result = project_metadata(root)
                    try:
                        result["work_branch"] = git(root, "branch", "--show-current")
                        result["image_head"] = git(root, "rev-parse", "refs/heads/image")
                    except EditorError:
                        result["image_head"] = ""
                    self.send_json(200, result)
                except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                    self.send_json(400, {"error": str(exc)})
                return
            if parsed.path == "/api/image":
                query = parse_qs(parsed.query)
                path = query.get("path", [""])[0]
                ref = query.get("ref", [""])[0]
                if not ref:
                    try:
                        ref = git(root, "rev-parse", "HEAD")
                    except EditorError as exc:
                        self.send_json(400, {"error": str(exc)})
                        return
                if not SHA1.fullmatch(ref) or not path or "\\" in path or ".." in PurePosixPath(path).parts:
                    self.send_json(400, {"error": "图片路径无效。"})
                    return
                try:
                    content = git(root, "show", f"{ref}:{PurePosixPath(path).as_posix()}", binary=True)
                except EditorError:
                    self.send_error(404)
                    return
                mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(content)
                return
            relative = "index.html" if parsed.path in {"/", ""} else parsed.path.lstrip("/")
            relative_parts = PurePosixPath(relative).parts
            if ".." in relative_parts or "\\" in relative or relative.startswith("\\"):
                self.send_error(404)
                return
            if relative in {"assets/css/style.css", "assets/js/editor.js"}:
                target = root / relative
            elif relative in ROOT_STATIC or relative.startswith("docs/") or relative == "CONTRIBUTING.md":
                if relative.startswith("docs/") and not (
                    relative.endswith(".md") or relative.startswith("docs/images/") and relative.endswith(".png")
                ):
                    self.send_error(404)
                    return
                target = root / relative
            else:
                target = TOOL_DIR / relative
            target = target.resolve()
            try:
                target.relative_to(root if relative in ROOT_STATIC or relative.startswith("docs/")
                                   or relative in {"CONTRIBUTING.md", "assets/css/style.css", "assets/js/editor.js"}
                                   else TOOL_DIR.resolve())
            except ValueError:
                self.send_error(404)
                return
            if not target.is_file():
                self.send_error(404)
                return
            content = target.read_bytes()
            mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if mime in {"text/html", "text/css", "application/javascript", "text/javascript"}:
                mime += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self):
            if not self.same_origin():
                self.send_json(403, {"error": "本地工具只接受本站页面发出的请求。"})
                return
            try:
                body = self.request_json()
                if not isinstance(body, dict):
                    raise EditorError("请求格式无效。")
                if self.path == "/api/scan":
                    result = with_baseline(root, scan_image_branch(root, body.get("commit_count", 1)))
                    token = secrets.token_urlsafe(24)
                    with lock:
                        scans[token] = result
                        if len(scans) > 8:
                            scans.pop(next(iter(scans)))
                    public = {key: value for key, value in result.items() if key != "baseline"}
                    public["scan_id"] = token
                    self.send_json(200, public)
                    return
                scan_id = str(body.get("scan_id", ""))
                with lock:
                    scan = scans.get(scan_id)
                if scan is None:
                    raise EditorError("扫描已过期，请重新扫描。")
                if self.path == "/api/annotate":
                    result = annotate(
                        root, scan, body.get("item_ids", []), body.get("provider", ""),
                        body.get("api_key", ""), body.get("model", ""),
                        body.get("batch_size", 4), body.get("interval", 1), body.get("retries", 2),
                    )
                    self.send_json(200, result)
                    return
                if self.path == "/api/apply":
                    with lock:
                        result = _apply_locked(root, scan, body.get("decisions", []))
                        scans.pop(scan_id, None)
                    self.send_json(200, {"result": result, "validation": "passed"})
                    return
                self.send_json(404, {"error": "未知的本地 API。"})
            except (EditorError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})

    return Handler


def _apply_locked(root: Path, scan: dict, decisions: list):
    try:
        from .data_editor_core import apply_changes
    except ImportError:
        from data_editor_core import apply_changes
    if not isinstance(decisions, list):
        raise EditorError("变更列表格式无效。")
    return apply_changes(root, scan, decisions)


def serve(data_dir: Path, port: int = 8765, open_browser: bool = True) -> int:
    data_dir = data_dir.expanduser().resolve()
    if not (data_dir / "manifest.json").is_file():
        raise EditorError("数据目录中没有 manifest.json，请传入仓库的 data 文件夹。")
    root = data_dir.parent
    scans = {}
    lock = threading.RLock()
    Handler = create_handler(root, scans, lock)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"奶-hub 数据编辑器：{url}")
    print("仅监听本机；按 Ctrl+C 关闭。API 密钥不会保存到磁盘。")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    data_dir = Path(argv[0]) if argv else Path("data")
    try:
        return serve(data_dir)
    except (EditorError, OSError) as exc:
        print(f"无法启动浏览器编辑器：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
