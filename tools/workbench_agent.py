"""Persistent agent receiver for the local workbench queue (stdlib, backend-agnostic).

The receiver owns everything that is independent of a specific Agent CLI:
claiming bridge requests, lease heartbeats, page approvals, receipts, stale
marking and session bookkeeping. The per-CLI protocol lives in a pluggable
backend (see ``BACKENDS`` / ``register_backend``); ``workbench_agent_codex``
is the first adapter and is registered at the bottom of this module.

Backend contract (duck-typed, no base class required):

- class attributes ``name`` (registry key, e.g. ``"codex"``) and ``label``
  (UI display name, e.g. ``"Codex"``); the bridge claimant identity is derived
  as ``"{name}-workbench"``;
- ``open()`` — spawn/handshake; raises RuntimeError with a Chinese install
  hint when the CLI is unavailable;
- ``begin_session(saved_id=None) -> {"thread_id": str|None, "model": str|None}``
  — resume the saved session or start a new one; ``thread_id`` may be None
  for per-task backends that only learn their session id after the first turn
  (expose it later via a ``session_id`` attribute and the receiver persists it);
- ``run_turn(prompt, hooks) -> str`` — run one request to completion and
  return the final answer text; raise RuntimeError on failure. Must call
  ``hooks.keepalive()`` at least every ~0.5s while working, may call
  ``hooks.progress(message)`` on phase changes and ``hooks.approval(view)``
  for native approvals (backends without an approval channel never do);
- ``alive() -> bool`` — False when the underlying process/session died while
  idling (checked between claims so a dead backend surfaces as an error
  instead of silently waiting forever);
- ``interrupt()`` — best-effort abort of the current turn;
- ``close()``.
"""
import json
import sys
import threading
import time
from pathlib import Path

import runlog

ROOT = Path(__file__).resolve().parents[1]
SESSION_PATH = ROOT / "tools" / "cache" / "workbench_agent_session.json"
DEFAULT_BACKEND = "codex"

BACKENDS = {}


def register_backend(cls):
    BACKENDS[cls.name] = cls
    return cls


def backend_options():
    return [{"name": cls.name, "label": cls.label} for cls in BACKENDS.values()]


def create_receiver(state, backend=DEFAULT_BACKEND, **receiver_kw):
    try:
        cls = BACKENDS[backend]
    except KeyError:
        raise ValueError("未知 Agent 后端：{}（可用：{}）".format(
            backend, "、".join(sorted(BACKENDS)) or "无"))
    return AgentReceiver(state, backend_factory=cls, **receiver_kw)


def parse_answer(text):
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(raw)
    except ValueError:
        raise RuntimeError("Agent 最终答复不是要求的 JSON 对象，未登记为成功")
    if not isinstance(value, dict) or value.get("status") not in ("ok", "error") or \
            not isinstance(value.get("message"), str) or not isinstance(value.get("result"), dict):
        raise RuntimeError("Agent 回执缺少 status/message/result，未登记为成功")
    return value


def build_prompt(request, snapshot, hub_url):
    public_request = {key: value for key, value in request.items() if key != "claim_token"}
    return """你是此仓库工作台的持续 Agent 接收会话，已经由接收端认领当前请求。
先读取 skills/mtg-workbench/SKILL.md 及必要的任务技能；不要再调用 /next 认领，
不要自行提交 /result，接收端负责租约和回执。不要启动子代理。
任务由网页直接提交，不需要人回到 CLI 再提示。完成当前任务后返回一次结果即可。
工作台地址：{hub}
可用 Python 解释器：{python}（Windows 下使用 PowerShell & 调用此完整路径）。
用户请求 JSON：
{request}
本次领取时的快照 JSON（最新状态仍应在操作前查询）：
{snapshot}
规则：只执行请求所需的仓库工具；不要修改项目代码、Git 历史或其他会话。
读取 rules/combo 的请求用对应工具查证，证据必须保留来源和日期。
具体牌名必须用 /api/find 或 mtg_tool search 验证；限制赛候选只能来自已导入牌池，
不能以外部检索为依据增加池外牌。除非请求明确要求修改牌表，给建议与依据即可。
命令或权限需批准时走接收端审批通道，审批将在网页显示；不要绕过审批。
最终只返回 JSON 对象，不用 Markdown：
{{"status":"ok或error","message":"中文结论","result":{{"evidence":["实际证据"],"next_moves":[]}}}}
result 可包含规则解释、候选或完整报告；失败需给出具体原因，不得伪造成功。
""".format(hub=hub_url, python=sys.executable, request=json.dumps(public_request, ensure_ascii=False),
           snapshot=json.dumps(snapshot, ensure_ascii=False))


class SessionLock:
    """OS lock released on process exit, including a crashed hub. Per backend."""
    def __init__(self, session_path, backend):
        path = Path(str(session_path) + "." + backend + ".lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("a+b")
        if path.stat().st_size == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError("工作台会话已由另一个接收端连接，请先断开原连接")

    def close(self):
        self.stream.close()


class TurnHooks:
    """Per-request callbacks handed to the backend's run_turn.

    keepalive() renews the bridge lease and raises RuntimeError when the turn
    must abort (lease lost / receiver disconnecting / deadline exceeded);
    backends call it periodically inside their event loop.
    """
    def __init__(self, receiver, request_id, claim_token, deadline):
        self.receiver = receiver
        self.request_id = request_id
        self.claim_token = claim_token
        self.deadline = deadline
        self._next_heartbeat = 0

    def keepalive(self):
        now = time.monotonic()
        if now >= self._next_heartbeat:
            outcome = self.receiver.state.bridge.heartbeat(
                self.request_id, self.receiver.agent_name, self.claim_token)
            if outcome != "ok":
                raise RuntimeError("请求租约已丢失，停止当前任务")
            self._next_heartbeat = now + self.receiver.heartbeat_interval
        if self.receiver._stop.is_set():
            raise RuntimeError("接收端已断开")
        if now >= self.deadline:
            raise RuntimeError("Agent 执行超时")

    def progress(self, message):
        self.receiver._update(message=message)

    def approval(self, view):
        """Blocking page round-trip; returns "accept"/"decline". Aborts raise."""
        receiver = self.receiver
        with receiver._lock:
            receiver._approval_counter += 1
            view = dict(view, id="approval-{}".format(receiver._approval_counter))
            receiver._approval = {"decision": None, "view": view}
        receiver._update(status="approval", message="等待网页批准 Agent 操作")
        try:
            while True:
                self.keepalive()
                with receiver._lock:
                    decision = receiver._approval["decision"]
                if decision:
                    receiver._update(status="busy", message="继续处理请求")
                    return decision
                receiver._stop.wait(.2)
        finally:
            with receiver._lock:
                receiver._approval = None


class AgentReceiver:
    def __init__(self, state, backend_factory=None, session_path=SESSION_PATH, heartbeat_interval=15):
        if backend_factory is None:
            backend_factory = BACKENDS[DEFAULT_BACKEND]
        self.state = state
        self.backend_factory = backend_factory
        self.backend_name = backend_factory.name
        self.backend_label = backend_factory.label
        self.agent_name = "{}-workbench".format(self.backend_name)
        self.session_path = Path(session_path)
        self.heartbeat_interval = heartbeat_interval
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._backend = None
        self._approval = None
        self._approval_counter = 0
        self._task_started = None
        self._status = {"status": "offline", "agent": self.agent_name,
                        "backend": self.backend_name, "backend_label": self.backend_label,
                        "message": "尚未连接",
                        "thread_id": None, "request_id": None, "model": None, "approval": None}

    def status(self):
        with self._lock:
            view = dict(self._status)
            view["approval"] = dict(self._approval["view"]) if self._approval else None
            view["elapsed_sec"] = round(time.monotonic() - self._task_started) if self._task_started and \
                view["status"] in ("busy", "approval") else 0
            return view

    def _update(self, **values):
        with self._lock:
            self._status.update(values)

    def connect(self, hub_url, thread_id=None):
        with self._lock:
            if self._thread and self._thread.is_alive():
                if self._stop.is_set():
                    raise ValueError("正在断开，请稍后重新连接")
                return dict(self._status)
            self._stop.clear()
            self._status.update(status="connecting",
                                message="启动 {} 并恢复工作台会话".format(self.backend_label),
                                request_id=None)
            self._thread = threading.Thread(target=self._run, args=(hub_url, thread_id), daemon=True)
            self._thread.start()
            return dict(self._status)

    def disconnect(self):
        self._stop.set()
        self._update(status="stopping", message="正在断开接收端")
        return self.status()

    def close(self):
        self._stop.set()
        backend = self._backend
        if backend:
            backend.close()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=5)

    def answer_approval(self, approval_id, decision):
        if decision not in ("accept", "decline"):
            raise ValueError("decision 只接受 accept/decline")
        with self._lock:
            if not self._approval or self._approval["view"]["id"] != approval_id:
                raise ValueError("审批已过期或不存在")
            self._approval["decision"] = decision
        return {"status": "ok"}

    def _saved_thread_id(self):
        try:
            saved = json.loads(self.session_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise RuntimeError("无法读取工作台会话记录：{}".format(exc))
        if not isinstance(saved, dict):
            raise RuntimeError("保存的工作台会话记录损坏，请修复 {}".format(self.session_path))
        if saved.get("backend", "codex") != self.backend_name or saved.get("cwd") != str(ROOT):
            return None
        if not isinstance(saved.get("thread_id"), str):
            raise RuntimeError("保存的工作台会话记录损坏，请修复 {}".format(self.session_path))
        return saved["thread_id"]

    def _save_thread_id(self, thread_id):
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_path.write_text(json.dumps(
            {"cwd": str(ROOT), "backend": self.backend_name, "thread_id": thread_id}),
            encoding="utf-8")

    def _execute(self, request, hub_url):
        rid = request["request_id"]
        timeout = min(max(request.get("timeout_sec") or 300, 1), 1800)
        deadline = time.monotonic() + timeout
        hooks = TurnHooks(self, rid, request.get("claim_token"), deadline)
        hooks.keepalive()
        self._task_started = time.monotonic()
        self._update(status="busy", request_id=rid, message="已自动领取，正在启动任务")
        snapshot = self.state.snapshot()
        try:
            answer = parse_answer(self._backend.run_turn(
                build_prompt(request, snapshot, hub_url), hooks))
        except Exception:
            try:
                self._backend.interrupt()
            except Exception:
                pass
            raise
        execution = {"thread_id": self.status()["thread_id"]}
        turn_id = getattr(self._backend, "last_turn_id", None)
        if turn_id:
            execution["turn_id"] = turn_id
        answer["result"]["execution"] = execution
        session_id = getattr(self._backend, "session_id", None)
        if session_id and session_id != execution["thread_id"]:
            self._save_thread_id(session_id)
            self._update(thread_id=session_id)
        current = self.state.snapshot()
        if current["sections"] != snapshot["sections"] or current["pool"]["entries"] != snapshot["pool"]["entries"]:
            answer["result"]["stale"] = True
            answer["message"] += "（处理期间牌表或牌池已变化，本回执基于领取时状态。）"
        return answer

    def _run(self, hub_url, thread_id):
        session_lock = None
        try:
            session_lock = SessionLock(self.session_path, self.backend_name)
            self._backend = self.backend_factory()
            self._backend.open()
            if not thread_id:
                thread_id = self._saved_thread_id()
            started = self._backend.begin_session(thread_id)
            thread_id = started.get("thread_id")
            if thread_id:
                self._save_thread_id(thread_id)
            self._update(status="idle", thread_id=thread_id, model=started.get("model"),
                         message="已连接，持续等待网页任务")
            runlog.log_run("workbench_agent", "connected",
                           "{} {}".format(self.backend_name, thread_id))
            while not self._stop.is_set():
                if not self._backend.alive():
                    raise RuntimeError("{} 后端进程已退出，请重新连接".format(self.backend_label))
                claimed = self.state.bridge.next_request(self.agent_name, wait=True, poll_max=1)
                if claimed["status"] == "wait":
                    continue
                request = claimed["request"]
                if self._stop.is_set():
                    self.state.bridge.complete(request["request_id"], "error", {}, "接收端已断开",
                                               agent=self.agent_name,
                                               claim_token=request.get("claim_token"))
                    break
                try:
                    answer = self._execute(request, hub_url)
                except Exception as exc:
                    answer = {"status": "error", "result": {}, "message": str(exc)}
                outcome = self.state.bridge.complete(request["request_id"], answer["status"],
                                                     answer["result"], answer["message"],
                                                     agent=self.agent_name,
                                                     claim_token=request.get("claim_token"))
                runlog.log_run("workbench_agent", answer["status"],
                               request["request_id"] + " " + outcome)
                self._task_started = None
                self._update(status="idle", request_id=None,
                             message="回执已提交，继续等待网页任务" if answer["status"] == "ok"
                             else "本次任务失败（原因见回执），继续等待网页任务")
        except Exception as exc:
            self._update(status="error", message=str(exc), request_id=None)
            runlog.log_run("workbench_agent", "error", str(exc))
        finally:
            if self._backend:
                self._backend.close()
            self._backend = None
            if session_lock:
                session_lock.close()
            if self._stop.is_set():
                self._update(status="offline", message="已断开", request_id=None)


from workbench_agent_codex import CodexBackend  # noqa: E402 注册默认后端
from workbench_agent_kimi import KimiBackend  # noqa: E402

register_backend(CodexBackend)
register_backend(KimiBackend)
