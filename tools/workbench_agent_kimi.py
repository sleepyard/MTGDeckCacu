"""Kimi Code CLI backend for the workbench agent receiver (stdlib).

Implements the backend contract documented in ``workbench_agent`` using the
CLI's print mode: one ``kimi --print --input-format=stream-json
--output-format=stream-json`` process per workbench request, the prompt sent
as a single ``{"role":"user",...}`` JSONL line on stdin (closing stdin ends
the run, giving a clean turn boundary and avoiding Windows command-line
length limits). Session continuity across requests is provided by
``--session <id>`` resume; the dedicated session id is captured after the
first run from ``session_index.jsonl`` under ``$KIMI_CODE_HOME`` (default
``~/.kimi-code``) or from a meta line when the CLI emits one.

Print mode auto-approves tool calls and never asks interactively, so this
backend never calls ``hooks.approval``. Exit codes: 0 ok, 1 permanent
failure, 75 retryable transient failure.

Protocol references: kimi command reference and print-mode docs
(https://www.kimi.com/code/docs/en/kimi-code-cli/reference/kimi-command.html).
Flag support is probed from ``kimi --help`` at connect time because the
installed version is not pinned.
"""
import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def kimi_command():
    executable = shutil.which("kimi") or shutil.which("kimi.cmd")
    if not executable:
        raise RuntimeError("未找到 Kimi Code CLI；请安装并登录、确认 kimi 在 PATH 中后连接")
    path = Path(executable)
    if path.suffix.lower() in (".cmd", ".bat"):
        return ["cmd.exe", "/c", str(path)]
    if path.suffix.lower() == ".ps1":
        raise RuntimeError("找到的是 PowerShell 封装 kimi.ps1；请将 npm 全局目录中的 kimi.cmd 加入 PATH")
    return [str(path)]


def data_home():
    return Path(os.environ.get("KIMI_CODE_HOME") or Path.home() / ".kimi-code")


def assistant_text(message):
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text") or "" for part in content
                       if isinstance(part, dict) and part.get("type") == "text")
    return ""


def find_session_id(payload):
    """Defensive search for a session id anywhere in a meta line."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in ("session_id", "sessionid") and isinstance(value, str):
                return value
            found = find_session_id(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_session_id(item)
            if found:
                return found
    return None


def latest_session_for(workdir, exclude_ids, index_path=None):
    """Newest session_index.jsonl record for workdir not in exclude_ids."""
    index = index_path or (data_home() / "session_index.jsonl")
    try:
        lines = index.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return None
    best, best_mtime = None, 0
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("workDir") != workdir or not record.get("sessionId") or \
                record["sessionId"] in exclude_ids:
            continue
        try:
            mtime = Path(record.get("sessionDir") or "").stat().st_mtime
        except OSError:
            mtime = 0
        if best is None or mtime >= best_mtime:
            best, best_mtime = record["sessionId"], mtime
    return best


class KimiBackend:
    name = "kimi"
    label = "Kimi Code"

    def __init__(self, command=None, session_index_path=None):
        self._command = command
        self.session_index_path = session_index_path
        self.session_id = None
        self.last_turn_id = None
        self._preexisting_ids = set()
        self._process = None
        self._stderr_tail = []

    # ---------------------------------------------------------- lifecycle

    def _help_text(self, prefix):
        proc = subprocess.run(prefix + ["--help"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode != 0:
            raise RuntimeError("kimi --help 执行失败：" + (proc.stderr or proc.stdout).strip()[:200])
        return proc.stdout

    def open(self):
        prefix = self._command or kimi_command()
        help_text = self._help_text(prefix)
        if "--input-format" not in help_text:
            raise RuntimeError("当前 Kimi Code CLI 不支持 --input-format=stream-json，请升级后连接")
        self._prefix = prefix + (["--print"] if "--print" in help_text else []) + \
            ["--input-format=stream-json", "--output-format=stream-json"]

    def begin_session(self, saved_id=None):
        if saved_id:
            known = self._known_session_ids()
            if known is not None and saved_id not in known:
                raise RuntimeError("保存的 Kimi 工作台会话已不存在，请清除 "
                                   "tools/cache/workbench_agent_session.json 后重新连接")
            self.session_id = saved_id
        else:
            self._preexisting_ids = self._known_session_ids() or set()
        return {"thread_id": self.session_id, "model": None}

    def _known_session_ids(self):
        """All sessionIds from session_index.jsonl; None when the index is unreadable."""
        index = self.session_index_path or (data_home() / "session_index.jsonl")
        try:
            lines = index.read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError):
            return None
        ids = set()
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("sessionId"):
                ids.add(record["sessionId"])
        return ids

    def alive(self):
        return True

    def close(self):
        self.interrupt()

    def interrupt(self):
        process = self._process
        if process and process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass

    # ------------------------------------------------------------- turn

    def _spawn(self, prompt):
        argv = list(self._prefix)
        if self.session_id:
            argv += ["--session", self.session_id]
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        process = subprocess.Popen(argv, cwd=str(ROOT), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", bufsize=1,
                                   env=env,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._stderr_tail = []
        threading.Thread(target=self._drain_stderr, args=(process,), daemon=True).start()
        process.stdin.write(json.dumps({"role": "user", "content": prompt},
                                       ensure_ascii=False) + "\n")
        process.stdin.close()
        return process

    def _drain_stderr(self, process):
        try:
            for line in process.stderr:
                self._stderr_tail.append(line.rstrip())
                del self._stderr_tail[:-20]
        except (OSError, ValueError):
            pass

    def run_turn(self, prompt, hooks):
        process = self._spawn(prompt)
        self._process = process
        lines = queue.Queue()
        threading.Thread(target=self._read_stdout, args=(process, lines), daemon=True).start()
        final_text = ""
        try:
            while True:
                hooks.keepalive()
                try:
                    line = lines.get(timeout=.5)
                except queue.Empty:
                    if process.poll() is not None and lines.empty():
                        break
                    continue
                if line is None:
                    break
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                role = message.get("role")
                if role == "assistant":
                    text = assistant_text(message)
                    if text.strip():
                        final_text = text
                    names = [((call.get("function") or {}).get("name") or "")
                             for call in message.get("tool_calls") or []]
                    hooks.progress("正在调用工具：" + "、".join(n for n in names if n)
                                   if names else "正在整理答复")
                elif role == "tool":
                    hooks.progress("工具已返回，继续分析")
                elif not self.session_id:
                    captured = find_session_id(message)
                    if captured:
                        self.session_id = captured
            code = process.wait(timeout=10)
        except Exception:
            self.interrupt()
            raise
        finally:
            self._process = None
        if not self.session_id:
            self.session_id = latest_session_for(str(ROOT), self._preexisting_ids,
                                                 self.session_index_path)
        self.last_turn_id = None
        if code == 0:
            if not final_text.strip():
                raise RuntimeError("Kimi 未给出最终答复")
            return final_text
        detail = "；".join(self._stderr_tail[-3:])[:300]
        if code == 75:
            raise RuntimeError("Kimi 临时错误（限流/超时，可稍后重试）：" + detail)
        raise RuntimeError("Kimi 执行失败（exit {}）：{}".format(code, detail))

    @staticmethod
    def _read_stdout(process, lines):
        try:
            for line in process.stdout:
                stripped = line.strip()
                if stripped:
                    lines.put(stripped)
        except (OSError, ValueError):
            pass
        finally:
            lines.put(None)
