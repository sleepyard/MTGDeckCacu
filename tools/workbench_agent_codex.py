"""Codex app-server backend for the workbench agent receiver (stdlib).

Implements the backend contract documented in ``workbench_agent``: spawns the
installed Codex CLI's ``app-server`` over stdio JSONL, creates/resumes one
dedicated workbench thread and runs bridge requests as turns. Protocol
reference: https://developers.openai.com/codex/app-server (verified locally
against CLI 0.118.0).
"""
import json
import queue
import shutil
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def codex_command():
    executable = shutil.which("codex") or shutil.which("codex.cmd")
    if not executable:
        raise RuntimeError("未找到 Codex CLI；请安装并登录后连接")
    path = Path(executable)
    if path.suffix.lower() in (".cmd", ".bat", ".ps1"):
        package = path.parent / "node_modules" / "@openai" / "codex"
        candidates = list((package / "node_modules" / "@openai").glob("codex-*/vendor/*/codex/codex.exe"))
        if candidates:
            executable = str(candidates[0])
        else:
            launcher = package / "bin" / "codex.js"
            node = shutil.which("node")
            if launcher.is_file() and node:
                return [node, str(launcher), "app-server", "--listen", "stdio://"]
            raise RuntimeError("找不到 Codex 原生程序，请检查 CLI 安装")
    return [executable, "app-server", "--listen", "stdio://"]


class RpcClient:
    """JSONL requests on stdin; one reader routes responses and notifications."""
    def __init__(self, cwd=ROOT):
        self.process = subprocess.Popen(codex_command(), cwd=str(cwd), stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8", bufsize=1,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._counter = 0
        self._pending = {}
        self.events = queue.Queue()
        self.closed = threading.Event()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._stderr_reader = threading.Thread(target=self._drain_stderr, daemon=True)
        self._reader.start()
        self._stderr_reader.start()

    def _drain_stderr(self):
        # Provider diagnostics may contain private config; do not expose raw stderr.
        for _line in self.process.stderr:
            pass

    def _read(self):
        try:
            for line in self.process.stdout:
                message = json.loads(line)
                if "method" in message:
                    self.events.put(message)
                elif "id" in message:
                    with self._lock:
                        pending = self._pending.get(message["id"])
                    if pending:
                        pending.put(message)
        except (OSError, ValueError):
            pass
        finally:
            self.closed.set()
            with self._lock:
                for pending in self._pending.values():
                    pending.put({"error": {"message": "Codex app-server 已断开"}})

    def send(self, message):
        with self._write_lock:
            if self.closed.is_set():
                raise RuntimeError("Codex app-server 已断开")
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()

    def notify(self, method, params=None):
        self.send({"method": method, "params": params or {}})

    def reply(self, request_id, result=None, error=None):
        self.send(dict({"id": request_id}, **({"error": error} if error else {"result": result})))

    def request(self, method, params=None, timeout=30):
        with self._lock:
            self._counter += 1
            key = self._counter
            pending = queue.Queue()
            self._pending[key] = pending
        try:
            self.send({"id": key, "method": method, "params": params or {}})
            try:
                message = pending.get(timeout=timeout)
            except queue.Empty:
                raise RuntimeError("Codex 接口超时：" + method)
            if message.get("error"):
                raise RuntimeError(str(message["error"].get("message") or "Codex 接口失败"))
            return message.get("result") or {}
        finally:
            with self._lock:
                self._pending.pop(key, None)

    def event(self, timeout=1):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            if self.closed.is_set():
                raise RuntimeError("Codex app-server 已退出")
            return None

    def close(self):
        with self._close_lock:
            if self.process.poll() is None:
                try:
                    self.process.stdin.close()
                    self.process.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=3)
            self.closed.set()
            self._reader.join(timeout=1)
            self._stderr_reader.join(timeout=1)
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if not stream.closed:
                    stream.close()


class CodexBackend:
    name = "codex"
    label = "Codex"

    def __init__(self, client_factory=RpcClient):
        self.client_factory = client_factory
        self.client = None
        self.thread_id = None
        self.session_id = None
        self.last_turn_id = None

    def open(self):
        self.client = self.client_factory()
        self.client.request("initialize", {"clientInfo": {"name": "mtg_workbench", "version": "1.0"}})
        self.client.notify("initialized")

    def begin_session(self, saved_id=None):
        params = {"cwd": str(ROOT), "approvalPolicy": "on-request", "sandbox": "workspace-write",
                  "approvalsReviewer": "user", "developerInstructions":
                  "Work only on workbench deck research requests. Do not spawn sub-agents, change project code or Git history."}
        if saved_id:
            params["threadId"] = saved_id
            started = self.client.request("thread/resume", params)
        else:
            started = self.client.request("thread/start", params)
        self.thread_id = started["thread"]["id"]
        self.session_id = self.thread_id
        return {"thread_id": self.thread_id, "model": started.get("model")}

    def alive(self):
        return self.client is not None and not self.client.closed.is_set()

    def _server_request(self, message, hooks):
        method, params = message["method"], message.get("params") or {}
        if method not in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
            self.client.reply(message["id"], error={"code": -32601,
                              "message": "此接收端暂不支持该交互请求；请通过 CLI 处理"})
            raise RuntimeError("Agent 请求了尚不支持的交互：" + method)
        view = {"kind": method,
                "reason": params.get("reason") or "Codex 请求批准操作",
                "detail": params.get("command") or
                json.dumps(params.get("changes") or {}, ensure_ascii=False)}
        try:
            decision = hooks.approval(view)
        except Exception:
            self.client.reply(message["id"], {"decision": "cancel"})
            raise
        self.client.reply(message["id"], {"decision": decision})

    def run_turn(self, prompt, hooks):
        started = self.client.request("turn/start", {"threadId": self.thread_id,
            "input": [{"type": "text", "text": prompt}]})
        turn_id = started["turn"]["id"]
        self.last_turn_id = turn_id
        messages = []
        while True:
            hooks.keepalive()
            event = self.client.event(timeout=.5)
            if not event:
                continue
            params = event.get("params") or {}
            if params.get("threadId") not in (None, self.thread_id) or \
                    params.get("turnId") not in (None, turn_id):
                continue
            if "id" in event:
                self._server_request(event, hooks)
                continue
            method = event.get("method")
            if method == "item/started":
                kind = (params.get("item") or {}).get("type")
                hooks.progress({"commandExecution": "正在执行查证工具", "reasoning": "正在分析",
                                "agentMessage": "正在整理答复", "webSearch": "正在查找来源"}.get(
                                kind, "正在处理任务"))
            elif method == "item/completed":
                item = params.get("item") or {}
                if item.get("type") == "agentMessage":
                    messages.append(item)
            elif method == "turn/completed":
                turn = params["turn"]
                if turn.get("id") != turn_id:
                    continue
                if turn.get("status") != "completed":
                    error = turn.get("error") or {}
                    raise RuntimeError(error.get("message") or "Codex turn " + str(turn.get("status")))
                items = [item for item in turn.get("items", []) if item.get("type") == "agentMessage"] or messages
                finals = [item for item in items if item.get("phase") == "final_answer"]
                return (finals or items)[-1]["text"] if items else ""

    def interrupt(self):
        if self.client and self.thread_id and self.last_turn_id:
            self.client.request("turn/interrupt",
                                {"threadId": self.thread_id, "turnId": self.last_turn_id},
                                timeout=5)

    def close(self):
        if self.client:
            self.client.close()
