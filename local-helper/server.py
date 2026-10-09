#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
獺祭 Ollama ヘルパー（標準ライブラリのみ・追加インストール不要）

【認証】
- ログインID:   環境変数 DASSAI_LOGIN_ID        （既定: dassai）
- パスワード:   環境変数 DASSAI_LOGIN_PASSWORD   （未設定の間はログイン不可）
- ログイン成功でトークンを発行。/start /stop /models /chat はトークン必須。
- 失敗が連続すると一定時間ロックします。

【API】
- GET  /status   状態確認（認証不要）
- POST /login    {"id","pw"} -> {"token"}
- POST /logout   トークンを破棄
- GET  /me       トークンの有効確認（200 / 401）
- POST /start    ollama serve を起動（要トークン）
- POST /stop     起動した ollama を終了（要トークン）
- GET  /models   インストール済みモデル一覧（要トークン）
- POST /chat     Ollama /api/chat をストリーミング中継（要トークン）

【その他の環境変数】
- HELPER_PORT     既定 8765
- OLLAMA_CMD      既定 ollama
- OLLAMA_API      既定 http://127.0.0.1:11434
- ALLOWED_ORIGINS 追加で許可するページのオリジン（カンマ区切り）
- DASSAI_TOKEN_TTL トークンの有効秒数（既定 28800 = 8時間）
"""
import hmac
import json
import os
import platform
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HELPER_HOST = "127.0.0.1"
HELPER_PORT = int(os.environ.get("HELPER_PORT", "8765"))
OLLAMA_API = os.environ.get("OLLAMA_API", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_CMD = os.environ.get("OLLAMA_CMD", "ollama")
LOGIN_ID = os.environ.get("DASSAI_LOGIN_ID", "dassai")
LOGIN_PASSWORD = os.environ.get("DASSAI_LOGIN_PASSWORD", "")
TOKEN_TTL = int(os.environ.get("DASSAI_TOKEN_TTL", str(8 * 3600)))
MAX_FAILS = 5
LOCK_SECONDS = 300
MAX_BODY = 25 * 1024 * 1024
EXTRA_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
LOCAL_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")
LOCAL_HOST_RE = re.compile(r"^(localhost|127\.0\.0\.1)(:\d+)?$")
IS_WINDOWS = platform.system() == "Windows"
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ollama_serve.log")

_ctl_lock = threading.Lock()    # Ollama プロセス制御用
_auth_lock = threading.Lock()   # トークン・ロック状態用
_tokens = {}                    # token -> 失効時刻(epoch)
_fail_count = 0
_locked_until = 0.0
_proc = None                    # このヘルパーが起動した ollama serve


# ---------------- Ollama 制御 ----------------
def ollama_up(timeout=2.0):
    try:
        with urllib.request.urlopen(OLLAMA_API + "/api/tags", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def managed_alive():
    return _proc is not None and _proc.poll() is None


def do_status():
    up = ollama_up()
    alive = managed_alive()
    return {
        "ok": True,
        "helper": True,
        "running": up,
        "managed": alive,
        "pid": _proc.pid if alive else None,
    }


def do_start():
    global _proc
    with _ctl_lock:
        if ollama_up():
            return {"ok": True, "running": True, "message": "Ollama は既に起動しています"}
        if not managed_alive():
            kwargs = {"stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT}
            if IS_WINDOWS:
                kwargs["creationflags"] = 0x00000200 | 0x08000000  # NEW_PROCESS_GROUP | NO_WINDOW
            else:
                kwargs["start_new_session"] = True
            log = open(LOG_PATH, "ab")
            try:
                _proc = subprocess.Popen([OLLAMA_CMD, "serve"], stdout=log, **kwargs)
            except FileNotFoundError:
                return {"ok": False, "running": False,
                        "message": "ollama コマンドが見つかりません。インストールと PATH を確認してください"}
            finally:
                log.close()

    deadline = time.time() + 20
    while time.time() < deadline:
        if ollama_up():
            return {"ok": True, "running": True, "message": "Ollama を起動しました"}
        if _proc is not None and _proc.poll() is not None:
            return {"ok": False, "running": False,
                    "message": "ollama serve が起動直後に終了しました。ollama_serve.log を確認してください"}
        time.sleep(0.5)
    return {"ok": False, "running": ollama_up(),
            "message": "起動待ちがタイムアウトしました（ollama_serve.log を確認してください）"}


def _kill_managed():
    global _proc
    pid = _proc.pid
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        _proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if not IS_WINDOWS:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        _proc.wait(timeout=5)
    _proc = None


def do_stop():
    global _proc
    with _ctl_lock:
        if managed_alive():
            _kill_managed()
        else:
            _proc = None
        if ollama_up():
            # 別経路で起動された Ollama も含めて終了を試みる
            try:
                if IS_WINDOWS:
                    subprocess.run(["taskkill", "/IM", "ollama.exe", "/F"], capture_output=True, text=True)
                else:
                    subprocess.run(["pkill", "-f", "ollama serve"], capture_output=True, text=True)
            except FileNotFoundError:
                pass
        deadline = time.time() + 5
        while time.time() < deadline and ollama_up():
            time.sleep(0.3)
        still = ollama_up()
    if still:
        return {"ok": False, "running": True, "message": "Ollama を終了できませんでした。手動で確認してください"}
    return {"ok": True, "running": False, "message": "Ollama を終了しました"}


def list_models():
    with urllib.request.urlopen(OLLAMA_API + "/api/tags", timeout=5) as r:
        data = json.loads(r.read().decode("utf-8"))
    return [m["name"] for m in data.get("models", []) if m.get("name")]


# ---------------- 認証 ----------------
def issue_token():
    tok = secrets.token_urlsafe(32)
    now = time.time()
    with _auth_lock:
        for t, exp in list(_tokens.items()):
            if exp < now:
                del _tokens[t]
        _tokens[tok] = now + TOKEN_TTL
    return tok


def token_valid(tok):
    if not tok:
        return False
    with _auth_lock:
        exp = _tokens.get(tok)
        if exp is None:
            return False
        if exp < time.time():
            del _tokens[tok]
            return False
        return True


def revoke_token(tok):
    with _auth_lock:
        _tokens.pop(tok, None)


def try_login(uid, pw):
    """戻り値: 'ok' / 'bad' / 'locked' / 'disabled'"""
    global _fail_count, _locked_until
    if not LOGIN_PASSWORD:
        return "disabled"
    with _auth_lock:
        if time.time() < _locked_until:
            return "locked"
    id_ok = hmac.compare_digest(uid.encode("utf-8"), LOGIN_ID.encode("utf-8"))
    pw_ok = hmac.compare_digest(pw.encode("utf-8"), LOGIN_PASSWORD.encode("utf-8"))
    with _auth_lock:
        if id_ok and pw_ok:
            _fail_count = 0
            return "ok"
        _fail_count += 1
        if _fail_count >= MAX_FAILS:
            _locked_until = time.time() + LOCK_SECONDS
            _fail_count = 0
        return "bad"


# ---------------- チャット中継 ----------------
def proxy_chat(handler, body):
    try:
        req = urllib.request.Request(OLLAMA_API + "/api/chat", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        upstream = urllib.request.urlopen(req, timeout=600)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        return handler._send(e.code, {"ok": False, "message": "Ollama エラー: " + detail})
    except Exception:
        return handler._send(502, {"ok": False, "message": "Ollama に接続できません。先に起動してください"})

    with upstream:
        handler.send_response(200)
        handler._cors()
        handler.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()
        try:
            for line in upstream:
                handler.wfile.write(line)
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return  # クライアントが中断
        except Exception as e:
            try:
                handler.wfile.write((json.dumps({"error": str(e)}, ensure_ascii=False) + "\n").encode("utf-8"))
                handler.wfile.flush()
            except Exception:
                pass


# ---------------- HTTP ----------------
class Handler(BaseHTTPRequestHandler):
    server_version = "DassaiOllamaHelper/2.0"
    protocol_version = "HTTP/1.0"

    def _allowed_origin(self):
        o = self.headers.get("Origin")
        if not o:
            return None
        if o == "null" or LOCAL_ORIGIN_RE.match(o) or o in EXTRA_ORIGINS:
            return o
        return False

    def _guard(self):
        if not LOCAL_HOST_RE.match(self.headers.get("Host", "")):  # DNS rebinding 対策
            self._send(403, {"ok": False, "message": "host not allowed"})
            return False
        if self._allowed_origin() is False:
            self._send(403, {"ok": False, "message": "origin not allowed"})
            return False
        return True

    def _cors(self):
        o = self._allowed_origin()
        if o:
            self.send_header("Access-Control-Allow-Origin", o)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Max-Age", "600")
            if self.headers.get("Access-Control-Request-Private-Network"):
                self.send_header("Access-Control-Allow-Private-Network", "true")

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _bearer(self):
        h = self.headers.get("Authorization", "")
        return h[7:].strip() if h.startswith("Bearer ") else ""

    def _require(self):
        if token_valid(self._bearer()):
            return True
        self._send(401, {"ok": False, "message": "ログインが必要です"})
        return False

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return None
        return self.rfile.read(n)

    def do_OPTIONS(self):
        if not self._guard():
            return
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._guard():
            return
        path = self.path.split("?")[0]
        if path == "/status":
            return self._send(200, do_status())
        if path == "/me":
            if not self._require():
                return
            return self._send(200, {"ok": True})
        if path == "/models":
            if not self._require():
                return
            try:
                return self._send(200, {"ok": True, "models": list_models()})
            except Exception:
                return self._send(502, {"ok": False, "message": "Ollama に接続できません。先に起動してください"})
        self._send(404, {"ok": False, "message": "not found"})

    def do_POST(self):
        if not self._guard():
            return
        path = self.path.split("?")[0]

        if path == "/login":
            raw = self._read_body()
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except (ValueError, UnicodeDecodeError):
                return self._send(400, {"ok": False, "message": "リクエストが不正です"})
            result = try_login(str(data.get("id", "")), str(data.get("pw", "")))
            if result == "ok":
                return self._send(200, {"ok": True, "token": issue_token(), "expires_in": TOKEN_TTL})
            if result == "disabled":
                return self._send(503, {"ok": False, "message": "パスワードが未設定です。DASSAI_LOGIN_PASSWORD を設定してヘルパーを再起動してください"})
            if result == "locked":
                return self._send(429, {"ok": False, "message": "失敗が続いたため一時的にロックしています。しばらく待ってください"})
            return self._send(401, {"ok": False, "message": "IDまたはパスワードが違います"})

        if path == "/logout":
            revoke_token(self._bearer())
            return self._send(200, {"ok": True, "message": "ログアウトしました"})

        if path in ("/start", "/stop", "/chat"):
            if not self._require():
                return

        if path == "/start":
            return self._send(200, do_start())
        if path == "/stop":
            return self._send(200, do_stop())
        if path == "/chat":
            raw = self._read_body()
            if raw is None:
                return self._send(400, {"ok": False, "message": "リクエストサイズが不正です"})
            try:
                data = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._send(400, {"ok": False, "message": "JSON が不正です"})
            if not data.get("model") or not isinstance(data.get("messages"), list):
                return self._send(400, {"ok": False, "message": "model と messages が必要です"})
            data["stream"] = True
            return proxy_chat(self, json.dumps(data, ensure_ascii=False).encode("utf-8"))

        self._send(404, {"ok": False, "message": "not found"})

    def log_message(self, fmt, *args):
        # トークンやパスワードはログに出さない（パスとステータスのみ）
        sys.stderr.write("[helper] " + (fmt % args) + "\n")


def main():
    if not LOGIN_PASSWORD:
        print("⚠ DASSAI_LOGIN_PASSWORD が未設定のため、ログインできません。設定してから起動してください。")
    srv = ThreadingHTTPServer((HELPER_HOST, HELPER_PORT), Handler)
    print("獺祭 Ollama ヘルパー起動: http://%s:%d  （停止は Ctrl+C）" % (HELPER_HOST, HELPER_PORT))
    print("ログインID: %s" % LOGIN_ID)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
