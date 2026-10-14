# -*- coding: utf-8 -*-
"""
英语口语精听校对 —— 本地服务器（只用 Python 标准库，不需要 pip install）

启动：双击 start.bat，或在本文件夹运行  python server.py
然后浏览器打开 http://127.0.0.1:8765
所有数据都存在本文件夹下的 data/ 里。
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import socketserver
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import services

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8765"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
DATA_DIR = os.path.join(BASE_DIR, "data")
SESS_DIR = os.path.join(DATA_DIR, "sessions")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
MAX_UPLOAD = 300 * 1024 * 1024

_lock = threading.Lock()

# ---------------------------------------------------------------------------
# 设置（密钥只存在本机 data/settings.json，接口里永远不返回明文）
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "doubao_api_key": "",
    "doubao_app_id": "",
    "doubao_access_token": "",
    "doubao_resource_id": "volc.bigasr.auc_turbo",
    "doubao_language": "",
    "deepseek_api_key": "",
    "deepseek_model": "deepseek-chat",
    "deepseek_base_url": "https://api.deepseek.com",
}
SECRET_FIELDS = ("doubao_api_key", "doubao_access_token", "deepseek_api_key")


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    s.update(read_json(SETTINGS_FILE, {}))
    return s


def public_settings(s: dict) -> dict:
    out = {}
    for k in DEFAULT_SETTINGS:
        v = s.get(k, "")
        if k in SECRET_FIELDS:
            out[k] = {"set": bool(v), "hint": ("…" + v[-4:]) if len(v) >= 8 else ("已填" if v else "")}
        else:
            out[k] = v
    out["asr_ready"] = services.doubao_ready(s)
    out["llm_ready"] = services.deepseek_ready(s)
    return out


def update_settings(body: dict) -> dict:
    with _lock:
        s = load_settings()
        for k in DEFAULT_SETTINGS:
            if k not in body:
                continue
            v = str(body[k] or "").strip()
            if k in SECRET_FIELDS and not v:
                continue  # 空 = 保持不变
            s[k] = v
        for k in body.get("clear") or []:
            if k in DEFAULT_SETTINGS:
                s[k] = DEFAULT_SETTINGS[k] if k not in SECRET_FIELDS else ""
        write_json(SETTINGS_FILE, s)
    return s


# ---------------------------------------------------------------------------
# 练习记录：data/sessions/<id>/session.json + 原始音频
# ---------------------------------------------------------------------------

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
}

ID_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
AUDIO_TYPES = {
    ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".aac": "audio/aac", ".mp3": "audio/mpeg",
    ".wav": "audio/wav", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".webm": "audio/webm",
    ".flac": "audio/flac", ".amr": "audio/amr", ".3gp": "audio/3gpp",
}


def sess_path(sid: str, *parts) -> str:
    if not ID_RE.match(sid or ""):
        raise HttpError(400, "无效的记录 ID")
    return os.path.join(SESS_DIR, sid, *parts)


def load_session(sid: str) -> dict:
    data = read_json(sess_path(sid, "session.json"), None)
    if data is None:
        raise HttpError(404, "找不到这条练习记录")
    return data


def save_session(data: dict):
    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json(sess_path(data["id"], "session.json"), data)


def summarize(d: dict) -> dict:
    rows = [r for r in d.get("rows") or [] if (r.get("en") or "").strip()]
    return {
        "id": d["id"],
        "title": d.get("title", ""),
        "created": d.get("created", ""),
        "updated": d.get("updated", ""),
        "duration": d.get("duration"),
        "n_rows": len(rows),
        "n_checked": sum(1 for r in rows if r.get("match") is not None),
        "n_natural": sum(1 for r in rows if r.get("natural")),
    }


def list_sessions() -> list:
    out = []
    if os.path.isdir(SESS_DIR):
        for sid in os.listdir(SESS_DIR):
            d = read_json(os.path.join(SESS_DIR, sid, "session.json"), None)
            if d:
                out.append(summarize(d))
    out.sort(key=lambda x: x["created"], reverse=True)
    return out


def create_session(filename: str, title: str, body: bytes) -> dict:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in AUDIO_TYPES:
        ext = ".m4a"
    sid = time.strftime("%Y%m%d-%H%M%S")
    with _lock:
        n = 1
        base = sid
        while os.path.exists(os.path.join(SESS_DIR, sid)):
            n += 1
            sid = "%s-%d" % (base, n)
        os.makedirs(os.path.join(SESS_DIR, sid))
    with open(sess_path(sid, "audio" + ext), "wb") as f:
        f.write(body)
    data = {
        "id": sid,
        "title": title or os.path.splitext(filename)[0] or sid,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "audio_file": "audio" + ext,
        "audio_name": filename,
        "duration": None,
        "source": None,  # doubao / silence / paste
        "rows": [],
    }
    save_session(data)
    return data


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class HttpError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status
        self.msg = msg


class Handler(BaseHTTPRequestHandler):
    server_version = "SpeakingCoach/1.0"

    def log_message(self, fmt, *args):  # 只打印出错的请求
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # -- 工具 --
    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            raise HttpError(413, "文件太大（超过 300MB）")
        return self.rfile.read(n) if n else b""

    def read_json_body(self) -> dict:
        try:
            return json.loads(self.read_body().decode("utf-8") or "{}")
        except ValueError:
            raise HttpError(400, "请求格式错误")

    def check_origin(self):
        # 只接受本机页面的请求：防止其他网站借浏览器偷偷调用本地接口
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            raise HttpError(403, "forbidden host")
        if self.command != "GET" and self.headers.get("X-App") != "1":
            raise HttpError(403, "forbidden")

    def handle_any(self):
        try:
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                self.check_origin()
                self.route_api(path)
            elif self.command in ("GET", "HEAD"):
                self.serve_static(path)
            else:
                raise HttpError(405, "method not allowed")
        except HttpError as e:
            self.send_json({"error": e.msg}, e.status)
        except services.ServiceError as e:
            self.send_json({"error": str(e)}, 502)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # 兜底：把错误告诉页面
            import traceback

            traceback.print_exc()
            try:
                self.send_json({"error": "服务器内部错误：%s" % e}, 500)
            except Exception:
                pass

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = handle_any

    # -- 静态文件 --
    def serve_static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.normpath(os.path.join(WEB_DIR, unquote(path).lstrip("/")))
        if not full.startswith(WEB_DIR + os.sep) or not os.path.isfile(full):
            raise HttpError(404, "not found")
        # 不依赖 mimetypes：Windows 注册表里 .js 有时被改成 text/plain
        ext = os.path.splitext(full)[1].lower()
        ctype = STATIC_TYPES.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def serve_audio(self, sid):
        d = load_session(sid)
        full = sess_path(sid, d["audio_file"])
        if not os.path.isfile(full):
            raise HttpError(404, "音频文件不见了")
        size = os.path.getsize(full)
        ctype = AUDIO_TYPES.get(os.path.splitext(full)[1].lower(), "application/octet-stream")
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        else:
            self.send_response(200)
        length = end - start + 1
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(full, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    # -- 接口 --
    def route_api(self, path):
        cmd = self.command
        parts = [p for p in path.split("/") if p][1:]  # 去掉 "api"

        if parts == ["ping"]:
            return self.send_json({"app": "speaking-coach"})

        if parts == ["settings"]:
            if cmd == "GET":
                return self.send_json(public_settings(load_settings()))
            if cmd == "POST":
                return self.send_json(public_settings(update_settings(self.read_json_body())))

        if parts == ["settings", "test"] and cmd == "POST":
            which = self.read_json_body().get("which")
            s = load_settings()
            msg = services.doubao_test(s) if which == "doubao" else services.deepseek_test(s)
            return self.send_json({"ok": True, "message": msg})

        if parts == ["sessions"]:
            if cmd == "GET":
                return self.send_json({"sessions": list_sessions()})
            if cmd == "POST":
                filename = unquote(self.headers.get("X-Filename") or "recording.m4a")
                title = unquote(self.headers.get("X-Title") or "")
                body = self.read_body()
                if not body:
                    raise HttpError(400, "没有收到音频文件")
                return self.send_json({"session": create_session(os.path.basename(filename), title, body)})

        if len(parts) >= 2 and parts[0] == "sessions":
            sid = parts[1]
            rest = parts[2:]
            if not rest:
                if cmd == "GET":
                    return self.send_json({"session": load_session(sid)})
                if cmd == "PUT":
                    body = self.read_json_body()
                    with _lock:
                        d = load_session(sid)
                        for k in ("title", "rows", "duration", "source"):
                            if k in body:
                                d[k] = body[k]
                        save_session(d)
                    return self.send_json({"ok": True, "updated": d["updated"]})
                if cmd == "DELETE":
                    load_session(sid)
                    shutil.rmtree(sess_path(sid), ignore_errors=True)
                    return self.send_json({"ok": True})
            if rest == ["audio"] and cmd in ("GET", "HEAD"):
                return self.serve_audio(sid)
            if rest == ["transcribe"] and cmd == "POST":
                load_session(sid)
                wav = self.read_body()
                segs = services.doubao_transcribe(wav, load_settings())
                return self.send_json({"segments": segs})

        if parts == ["ai", "understand"] and cmd == "POST":
            body = self.read_json_body()
            items = services.understand(load_settings(), body.get("context") or [], body.get("ids") or [])
            return self.send_json({"items": items})

        if parts == ["ai", "improve"] and cmd == "POST":
            body = self.read_json_body()
            return self.send_json({"items": services.improve(load_settings(), body.get("items") or [])})

        raise HttpError(404, "接口不存在")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows 上 SO_REUSEADDR 会让两个程序同时占用同一端口，关掉它，重复启动时才能发现
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        # 跳过 HTTPServer 默认的 getfqdn() 反查，部分 Windows 电脑上会卡好几秒
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def already_running(port) -> bool:
    try:
        with urllib.request.urlopen("http://%s:%d/api/ping" % (HOST, port), timeout=1) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == "speaking-coach"
    except Exception:
        return False


def main():
    os.makedirs(SESS_DIR, exist_ok=True)
    url = "http://%s:%d/" % (HOST, PORT)
    try:
        httpd = Server((HOST, PORT), Handler)
    except OSError:
        if already_running(PORT):
            print("程序已经在运行了，直接打开浏览器：" + url)
            webbrowser.open(url)
            return
        print("端口 %d 被其他程序占用了。可以先关掉占用它的程序，或者换个端口：" % PORT)
        print("    set PORT=8766 && python server.py")
        sys.exit(1)
    print("=" * 56)
    print("  英语口语精听校对 已启动")
    print("  浏览器打开：" + url)
    print("  数据保存在：" + DATA_DIR)
    print("  关闭这个窗口 = 退出程序")
    print("=" * 56)
    if not os.environ.get("NO_BROWSER"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
