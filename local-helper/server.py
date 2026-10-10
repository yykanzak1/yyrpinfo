#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
獺祭 OpenCode ヘルパー（標準ライブラリのみ・追加インストール不要）

Ollama の代わりに opencode を操作します。
- opencode serve を起動・終了
- 利用可能なモデル一覧（opencode の /config/providers から取得）
- opencode のセッションを作成し、プロンプトを送って応答をストリーミング中継

【認証】
- ログインID:   環境変数 DASSAI_LOGIN_ID        （既定: dassai）
- パスワード:   環境変数 DASSAI_LOGIN_PASSWORD   （未設定の間はログイン不可）
- ログイン成功でトークンを発行。/start /stop /models /new /chat はトークン必須。
- 失敗が連続すると一定時間ロックします。

【API】
- GET  /status   状態確認（認証不要）
- POST /login    {"id","pw"} -> {"token"}
- POST /logout   トークンを破棄
- GET  /me       トークンの有効確認（200 / 401）
- POST /start    opencode serve を起動（要トークン）  body: {"directory"?}
- POST /stop     起動した opencode を終了（要トークン）
- GET  /models   利用可能なモデル一覧（要トークン）
- POST /new      新しいチャット（セッション）を開始（要トークン）
- POST /chat     opencode セッションへ送信し応答を NDJSON で中継（要トークン）

【その他の環境変数】
- HELPER_PORT      既定 8765
- OPENCODE_CMD     既定 opencode（見つからなければ PATH から解決）
- OPENCODE_API     既定 http://127.0.0.1:4096（opencode serve の待受）
- OPENCODE_CWD     opencode を起動する作業ディレクトリ（既定: 実行ユーザーのホーム）
- OPENCODE_SERVER_PASSWORD  設定時は opencode サーバへ Basic 認証で接続
- OPENCODE_SERVER_USERNAME  既定 opencode
- ALLOWED_ORIGINS  追加で許可するページのオリジン（カンマ区切り）
- DASSAI_TOKEN_TTL トークンの有効秒数（既定 28800 = 8時間）
"""
import base64
import hmac
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HELPER_HOST = "127.0.0.1"
HELPER_PORT = int(os.environ.get("HELPER_PORT", "8765"))
OPENCODE_API = os.environ.get("OPENCODE_API", "http://127.0.0.1:4096").rstrip("/")
OPENCODE_CMD = os.environ.get("OPENCODE_CMD", "opencode")
DEFAULT_CWD = os.environ.get("OPENCODE_CWD", os.path.expanduser("~"))
LOGIN_ID = os.environ.get("DASSAI_LOGIN_ID", "dassai")
LOGIN_PASSWORD = os.environ.get("DASSAI_LOGIN_PASSWORD", "")
SRV_USER = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
SRV_PASSWORD = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
TOKEN_TTL = int(os.environ.get("DASSAI_TOKEN_TTL", str(8 * 3600)))
MAX_FAILS = 5
LOCK_SECONDS = 300
MAX_BODY = 25 * 1024 * 1024
CHAT_TIMEOUT = 1800
EXTRA_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
LOCAL_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")
LOCAL_HOST_RE = re.compile(r"^(localhost|127\.0\.0\.1)(:\d+)?$")
IS_WINDOWS = platform.system() == "Windows"
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opencode_serve.log")

_ctl_lock = threading.Lock()    # opencode プロセス制御用
_auth_lock = threading.Lock()   # トークン・ロック状態用
_tokens = {}                    # token -> 失効時刻(epoch)
_fail_count = 0
_locked_until = 0.0
_proc = None                    # このヘルパーが起動した opencode serve
_session_id = None              # 現在のチャットセッション
_session_lock = threading.Lock()


# ---------------- opencode 制御 ----------------
def _auth_header():
    if SRV_PASSWORD:
        raw = ("%s:%s" % (SRV_USER, SRV_PASSWORD)).encode("utf-8")
        return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
    return {}


def upstream(method, path, body=None, timeout=30, stream=False):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    headers.update(_auth_header())
    req = urllib.request.Request(OPENCODE_API + path, data=data, headers=headers, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def server_up(timeout=2.0):
    try:
        with upstream("GET", "/global/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def managed_alive():
    return _proc is not None and _proc.poll() is None


def _resolve_cmd():
    for cand in (OPENCODE_CMD, "opencode.cmd", "opencode.exe", "opencode"):
        p = shutil.which(cand)
        if p:
            return p
    return OPENCODE_CMD


def do_status():
    up = server_up()
    alive = managed_alive()
    return {
        "ok": True,
        "helper": True,
        "running": up,
        "managed": alive,
        "pid": _proc.pid if alive else None,
        "directory": _current_cwd(),
    }


def _current_cwd():
    return getattr(_proc, "_dassai_cwd", DEFAULT_CWD) if _proc is not None else DEFAULT_CWD


def do_start(directory=None):
    global _proc
    cwd = directory or DEFAULT_CWD
    with _ctl_lock:
        if server_up():
            return {"ok": True, "running": True, "managed": managed_alive(),
                    "directory": _current_cwd(), "message": "opencode サーバは既に起動しています"}
        if not os.path.isdir(cwd):
            return {"ok": False, "running": False, "message": "作業ディレクトリが見つかりません: " + cwd}
        if not managed_alive():
            parsed = urllib.parse.urlparse(OPENCODE_API)
            host = parsed.hostname or "127.0.0.1"
            port = str(parsed.port or 4096)
            exe = _resolve_cmd()
            args = [exe, "serve", "--hostname", host, "--port", port]
            if IS_WINDOWS and exe.lower().endswith((".cmd", ".bat")):
                args = [os.environ.get("COMSPEC", "cmd.exe"), "/c"] + args
            kwargs = {"stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT, "cwd": cwd}
            if IS_WINDOWS:
                kwargs["creationflags"] = 0x00000200 | 0x08000000  # NEW_PROCESS_GROUP | NO_WINDOW
            else:
                kwargs["start_new_session"] = True
            log = open(LOG_PATH, "ab")
            try:
                _proc = subprocess.Popen(args, stdout=log, **kwargs)
                _proc._dassai_cwd = cwd
            except FileNotFoundError:
                return {"ok": False, "running": False,
                        "message": "opencode コマンドが見つかりません。インストールと PATH を確認してください"}
            finally:
                log.close()

    deadline = time.time() + 30
    while time.time() < deadline:
        if server_up():
            return {"ok": True, "running": True, "managed": True, "directory": cwd,
                    "message": "opencode サーバを起動しました"}
        if _proc is not None and _proc.poll() is not None:
            return {"ok": False, "running": False,
                    "message": "opencode serve が起動直後に終了しました。opencode_serve.log を確認してください"}
        time.sleep(0.5)
    return {"ok": False, "running": server_up(),
            "message": "起動待ちがタイムアウトしました（opencode_serve.log を確認してください）"}


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
    global _proc, _session_id
    with _ctl_lock:
        if managed_alive():
            _kill_managed()
        else:
            _proc = None
        if server_up():
            try:
                if IS_WINDOWS:
                    subprocess.run(["taskkill", "/IM", "opencode.exe", "/F"], capture_output=True, text=True)
                else:
                    subprocess.run(["pkill", "-f", "opencode serve"], capture_output=True, text=True)
            except FileNotFoundError:
                pass
        deadline = time.time() + 5
        while time.time() < deadline and server_up():
            time.sleep(0.3)
        still = server_up()
    with _session_lock:
        _session_id = None
    if still:
        return {"ok": False, "running": True, "message": "opencode サーバを終了できませんでした。手動で確認してください"}
    return {"ok": True, "running": False, "message": "opencode サーバを終了しました"}


def list_models():
    with upstream("GET", "/config/providers", timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    models = []
    for p in data.get("providers", []):
        pid = p.get("id")
        for mid in (p.get("models") or {}):
            if pid and mid:
                models.append(pid + "/" + mid)
    default = ""
    for pid, mid in (data.get("default") or {}).items():
        if pid and mid:
            default = pid + "/" + mid
            break
    return sorted(set(models)), default


def _get_or_create_session():
    global _session_id
    with _session_lock:
        if _session_id:
            return _session_id
        with upstream("POST", "/session", {"title": "dassai-console"}, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        _session_id = data.get("id")
        return _session_id


def new_session():
    global _session_id
    with _session_lock:
        old = _session_id
        _session_id = None
    if old:
        try:
            upstream("DELETE", "/session/" + old, timeout=10).close()
        except Exception:
            pass
    return True


def _parse_model(s):
    if "/" in s:
        pid, mid = s.split("/", 1)
        return {"providerID": pid, "modelID": mid}
    return {"providerID": "opencode", "modelID": s}


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
def proxy_chat(handler, model, text, system):
    # 1) セッション作成
    try:
        sid = _get_or_create_session()
    except Exception:
        return handler._send(502, {"ok": False, "message": "opencode に接続できません。先に起動してください"})
    if not sid:
        return handler._send(502, {"ok": False, "message": "セッションを作成できませんでした"})

    # 2) 応答ヘッダ（NDJSON ストリーム）
    handler.send_response(200)
    handler._cors()
    handler.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()

    def emit(obj):
        handler.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        handler.wfile.flush()

    # 3) イベントストリームを開く
    try:
        ev = upstream("GET", "/event", timeout=CHAT_TIMEOUT, stream=True)
    except Exception:
        try:
            emit({"error": "opencode のイベントストリームに接続できません"})
        except Exception:
            pass
        return

    # 4) プロンプト送信
    body = {"model": _parse_model(model), "parts": [{"type": "text", "text": text}]}
    if system:
        body["system"] = system
    try:
        upstream("POST", "/session/%s/prompt_async" % sid, body, timeout=30).close()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        try:
            emit({"error": "opencode エラー: " + detail})
        except Exception:
            pass
        ev.close()
        return
    except Exception:
        try:
            emit({"error": "プロンプトの送信に失敗しました"})
        except Exception:
            pass
        ev.close()
        return

    # 5) イベントを中継
    assistant_ids = set()
    text_parts = {}     # partID -> 送信済み文字数
    tool_state = {}     # partID -> 最後に通知した status
    deadline = time.time() + CHAT_TIMEOUT
    aborted = False
    try:
        for raw in ev:
            if time.time() > deadline:
                emit({"error": "応答がタイムアウトしました"})
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                o = json.loads(line[5:].strip())
            except Exception:
                continue
            t = o.get("type")
            p = o.get("properties", {}) or {}

            if t == "message.updated":
                info = p.get("info", {}) or {}
                if info.get("sessionID") == sid and info.get("role") == "assistant" and info.get("id"):
                    assistant_ids.add(info["id"])
                continue

            if t == "message.part.updated":
                part = p.get("part", {}) or {}
                if part.get("sessionID") != sid or part.get("messageID") not in assistant_ids:
                    continue
                ptype = part.get("type")
                pid_ = part.get("id")
                if ptype == "text":
                    full = part.get("text") or ""
                    sent = text_parts.get(pid_, 0)
                    if len(full) > sent:
                        emit({"message": {"content": full[sent:]}})
                        text_parts[pid_] = len(full)
                elif ptype == "tool":
                    st = (part.get("state") or {}).get("status")
                    if st and tool_state.get(pid_) != st:
                        tool_state[pid_] = st
                        name = part.get("tool") or "tool"
                        emit({"message": {"content": "\n> 🔧 %s (%s)\n" % (name, st)}})
                continue

            if t == "session.error" and p.get("sessionID") == sid:
                err = p.get("error") or {}
                msg = (err.get("data") or {}).get("message") or err.get("name") or "不明なエラー"
                try:
                    emit({"error": str(msg)})
                except Exception:
                    pass
                break

            if t == "session.idle" and p.get("sessionID") == sid:
                emit({"done": True})
                break
    except (BrokenPipeError, ConnectionResetError):
        aborted = True
    except Exception as e:
        try:
            emit({"error": str(e)})
        except Exception:
            pass
    finally:
        try:
            ev.close()
        except Exception:
            pass
    if aborted:
        try:
            upstream("POST", "/session/%s/abort" % sid, timeout=10).close()
        except Exception:
            pass


# ---------------- HTTP ----------------
class Handler(BaseHTTPRequestHandler):
    server_version = "DassaiOpenCodeHelper/1.0"
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

    def _read_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return None
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return False

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
                models, default = list_models()
                return self._send(200, {"ok": True, "models": models, "default": default})
            except Exception:
                return self._send(502, {"ok": False, "message": "opencode に接続できません。先に起動してください"})
        self._send(404, {"ok": False, "message": "not found"})

    def do_POST(self):
        if not self._guard():
            return
        path = self.path.split("?")[0]

        if path == "/login":
            data = self._read_json()
            if data is False or not isinstance(data, dict):
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

        if path in ("/start", "/stop", "/models", "/new", "/chat"):
            if not self._require():
                return

        if path == "/start":
            data = self._read_json()
            directory = None
            if isinstance(data, dict):
                directory = (data.get("directory") or "").strip() or None
            return self._send(200, do_start(directory if directory else None))
        if path == "/stop":
            return self._send(200, do_stop())
        if path == "/new":
            new_session()
            return self._send(200, {"ok": True, "message": "新しいチャットを開始しました"})
        if path == "/chat":
            data = self._read_json()
            if not isinstance(data, dict):
                return self._send(400, {"ok": False, "message": "JSON が不正です"})
            model = str(data.get("model") or "")
            text = str(data.get("text") or "")
            system = str(data.get("system") or "")
            if not model or not text:
                return self._send(400, {"ok": False, "message": "model と text が必要です"})
            return proxy_chat(self, model, text, system)

        self._send(404, {"ok": False, "message": "not found"})

    def log_message(self, fmt, *args):
        # トークンやパスワードはログに出さない（パスとステータスのみ）
        sys.stderr.write("[helper] " + (fmt % args) + "\n")


def main():
    if not LOGIN_PASSWORD:
        print("⚠ DASSAI_LOGIN_PASSWORD が未設定のため、ログインできません。設定してから起動してください。")
    print("opencode: %s" % OPENCODE_API)
    print("作業ディレクトリ（既定）: %s" % DEFAULT_CWD)
    srv = ThreadingHTTPServer((HELPER_HOST, HELPER_PORT), Handler)
    print("獺祭 OpenCode ヘルパー起動: http://%s:%d  （停止は Ctrl+C）" % (HELPER_HOST, HELPER_PORT))
    print("ログインID: %s" % LOGIN_ID)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
