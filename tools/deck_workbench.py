#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网页套牌工作台 hub 骨架（MtgWorkbenchPlan Phase 0，stdlib only）。

分层（决策 B：引擎先行，UI 最薄）：
  引擎纯函数    build_snapshot / serialize_deck —— Deck → 快照 dict / 导出文本
  权威状态      WorkbenchState —— 持锁；import 解析后在锁内替换状态并返回新快照
  HTTP 层       make_handler —— 解析请求 → 调引擎 → 序列化，不含任何牌规则

端点：
  GET  /                    内嵌工作台页面（fetch 轮询 /api/snapshot，3s）
  GET  /api/snapshot        牌表快照：分区条目、counts、total、skipped、会话元数据
  POST /api/builds/import   请求体为牌表文本；deck_model.parse_text 解析并替换状态
  GET  /api/export          标准导出文本（与 deck_model 解析器可往返解析）

错误信封与 mtg_rules_tool 同构：
  {"status": "error", "error": {"type": ..., "message": ...}}
未知路径 404；handler 未捕获异常 500（traceback 只进 stderr，不回浏览器）；
完全解析不出任何条目的导入是业务错误（400），与"成功但带 skipped 警告"
明确分离。Ctrl+C 干净退出；CLI 出口接 runlog 留痕。
"""
import argparse
import json
import sys
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import deck_model
import runlog

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8644
MAX_BODY_BYTES = 1024 * 1024
POLL_INTERVAL_MS = 3000

SECTIONS = deck_model.SECTIONS  # ("commander", "companion", "main", "sideboard")
SECTION_TITLES = {"commander": "Commander", "companion": "Companion",
                  "main": "Deck", "sideboard": "Sideboard"}


class WorkbenchError(Exception):
    """工作台启动/服务级错误（如端口占用），CLI 出口给清晰错误。"""


class EmptyImportError(ValueError):
    """牌表文本未解析出任何条目（业务错误，区别于带警告的成功）。"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ 引擎纯函数

def build_snapshot(deck, session):
    """纯函数：Deck + 会话元数据 → 快照 dict（import 响应与其同构）。"""
    sections, counts = {}, {}
    for sec in SECTIONS:
        cards = getattr(deck, sec)
        sections[sec] = [{"qty": card.qty, "name": card.name} for card in cards]
        counts[sec] = sum(card.qty for card in cards)
    skipped = [{"line_no": item.line_no, "raw": item.raw, "reason": item.reason}
               for item in deck.skipped]
    return {"status": "ok", "sections": sections, "counts": counts,
            "total": sum(counts.values()), "skipped": skipped,
            "warnings": ["第 {} 行已跳过（{}）: {}".format(
                item.line_no, item.reason, item.raw) for item in deck.skipped],
            "session": session}


def serialize_deck(deck):
    """纯函数：Deck → 标准导出文本。分区头部（Deck/Sideboard/Commander/
    Companion）为 deck_model 识别的段头，`数量 牌名` 行可被 _LINE_RE 往返
    解析；空分区不输出段头，blank-line 切备牌规则因此不会干扰再导入。"""
    lines = []
    for sec in SECTIONS:
        cards = getattr(deck, sec)
        if not cards:
            continue
        lines.append(SECTION_TITLES[sec])
        lines.extend("{} {}".format(card.qty, card.name) for card in cards)
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ 权威状态

class WorkbenchState:
    """权威状态：当前 Deck + 会话元数据（导入时间/来源/序号）。

    所有读写持锁，import 的纯解析在锁外完成，锁内只做替换 + 快照构造，
    并发导入因此是安全的串行化（最后一次成功写入获胜）。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._deck = deck_model.Deck()
        self._imported_at = None
        self._source_name = None
        self._import_seq = 0

    def _session_locked(self):
        return {"imported_at": self._imported_at,
                "source_name": self._source_name, "import_seq": self._import_seq}

    def snapshot(self):
        with self._lock:
            return build_snapshot(self._deck, self._session_locked())

    def export_text(self):
        with self._lock:
            return serialize_deck(self._deck)

    def import_text(self, text, source_name=None):
        """解析并替换当前牌表，返回新快照 dict。

        完全解析不出任何条目时抛 EmptyImportError（失败），有 skipped
        行但仍有个体条目时正常返回（成功但带 warnings，见快照）。
        """
        deck = deck_model.parse_text(text)
        if not any(getattr(deck, sec) for sec in SECTIONS):
            raise EmptyImportError(
                "牌表文本未解析出任何条目；期望 '数量 英文名' 行或分区段头")
        with self._lock:
            self._deck = deck
            self._imported_at = _now_iso()
            self._source_name = source_name or None
            self._import_seq += 1
            return build_snapshot(deck, self._session_locked())


# ------------------------------------------------------------------ HTTP 层

def _error_envelope(exc_type, message):
    return {"status": "error", "error": {"type": exc_type, "message": message}}


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def make_handler(state):
    """构造绑定给定状态的 Handler 类。只做请求解析→引擎调用→序列化。"""
    class Handler(BaseHTTPRequestHandler):
        server_version = "DeckWorkbench/0"

        def _send(self, status, body, ctype):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status, payload):
            self._send(status, _json_bytes(payload),
                       "application/json; charset=utf-8")

        def _read_body(self):
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise ValueError("缺少 Content-Length 请求头")
            try:
                length = int(raw_length)
            except ValueError:
                raise ValueError("Content-Length 非法: {!r}".format(raw_length))
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValueError("请求体长度越界: {}".format(length))
            body = self.rfile.read(length)
            try:
                return body.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError("请求体不是合法 UTF-8: {}".format(exc))

        def do_GET(self):
            try:
                path = urlsplit(self.path).path
                if path == "/":
                    self._send(200, PAGE_HTML.encode("utf-8"),
                               "text/html; charset=utf-8")
                elif path == "/api/snapshot":
                    self._send_json(200, state.snapshot())
                elif path == "/api/export":
                    self._send(200, state.export_text().encode("utf-8"),
                               "text/plain; charset=utf-8")
                else:
                    self._send_json(404, _error_envelope(
                        "NotFoundError", "未知路径: {}".format(path)))
            except Exception as exc:
                self._unhandled(exc)

        def do_POST(self):
            try:
                path = urlsplit(self.path).path
                if path != "/api/builds/import":
                    self._send_json(404, _error_envelope(
                        "NotFoundError", "未知路径: {}".format(path)))
                    return
                try:
                    text = self._read_body()
                except ValueError as exc:
                    self._send_json(400, _error_envelope("BadRequest", str(exc)))
                    return
                source_name = self.headers.get("X-Source-Name")
                try:
                    snapshot = state.import_text(text, source_name=source_name)
                except EmptyImportError as exc:
                    envelope = _error_envelope(type(exc).__name__, str(exc))
                    envelope["skipped"] = []   # 无状态可回读，保持信封最小
                    envelope["warnings"] = []
                    self._send_json(400, envelope)
                    return
                self._send_json(200, snapshot)
            except Exception as exc:
                self._unhandled(exc)

        def _unhandled(self, exc):
            traceback.print_exc()   # traceback 进 stderr，不回浏览器
            try:
                self._send_json(500, _error_envelope(
                    type(exc).__name__, "工作台内部错误: {}".format(exc)))
            except OSError:
                pass                # 连接已断，无法回写

        def log_message(self, *args):
            pass                    # 静音访问日志

    return Handler


# ------------------------------------------------------------------ 内嵌页面

PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>MTG 套牌工作台</title>
<style>
  body { background:#0d1117; color:#c9d1d9; font-family:Consolas,'Microsoft YaHei',monospace;
         margin:0; padding:16px; }
  h1 { font-size:18px; color:#58a6ff; margin:0 0 12px; }
  .panel { background:#161b22; border:1px solid #30363d; border-radius:6px;
           padding:12px 16px; margin-bottom:12px; }
  .panel h2 { font-size:13px; color:#8b949e; margin:0 0 8px; font-weight:normal; }
  #session { font-size:13px; color:#8b949e; }
  .zone { margin-bottom:10px; }
  .zone b { color:#3fb950; }
  .zone ul { margin:4px 0 0; padding-left:20px; line-height:1.7; font-size:14px; }
  #pool { width:100%; height:120px; background:#0d1117; color:#c9d1d9;
          border:1px solid #30363d; border-radius:4px; font-family:inherit; }
  #srcname { width:240px; background:#0d1117; color:#c9d1d9;
             border:1px solid #30363d; border-radius:4px; font-family:inherit; }
  button { background:#21262d; color:#c9d1d9; border:1px solid #30363d;
           border-radius:6px; padding:5px 14px; margin-top:8px; cursor:pointer; }
  button:hover { border-color:#58a6ff; }
  #warnings { color:#e3b341; white-space:pre-wrap; font-size:13px; }
  #errors { color:#f85149; white-space:pre-wrap; font-size:13px; }
  .ts { color:#484f58; }
</style>
</head>
<body>
<h1>MTG 套牌工作台（Phase 0 hub）</h1>
<div class="panel"><h2>会话</h2><div id="session">尚未导入牌表</div></div>
<div class="panel"><h2>牌表分区</h2><div id="zones">—</div></div>
<div class="panel"><h2>导入牌表</h2>
  <textarea id="pool" placeholder="粘贴牌表文本（数量 英文名，可用 Deck/Sideboard/Commander/Companion 段头）"></textarea>
  <div>来源文件名（可选）：<input id="srcname" type="text"></div>
  <button id="importBtn">导入</button>
  <button id="exportBtn">导出当前牌表</button>
</div>
<div class="panel"><h2>警告</h2><div id="warnings">—</div></div>
<div class="panel"><h2>错误</h2><div id="errors">—</div></div>
<script>
const ZONES = ['commander', 'companion', 'main', 'sideboard'];
const ZH = {commander:'指挥官', companion:'伴侣', main:'主牌', sideboard:'备牌'};
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                                  .replace(/>/g,'&gt;'); }
function showErrors(msg) { document.getElementById('errors').textContent = msg || '—'; }
async function tick() {
  try {
    const r = await fetch('/api/snapshot');
    const d = await r.json();
    showErrors('');
    const s = d.session || {};
    document.getElementById('session').textContent = s.import_seq
      ? '导入 #' + s.import_seq + '　' + (s.source_name ? '来源 ' + s.source_name + '　' : '')
        + '时间 ' + s.imported_at
      : '尚未导入牌表';
    let html = '';
    for (const z of ZONES) {
      const items = (d.sections && d.sections[z]) || [];
      const count = (d.counts && d.counts[z]) || 0;
      html += '<div class="zone"><b>' + ZH[z] + '</b>（' + count + ' 张）<ul>'
        + items.map(c => '<li>' + c.qty + ' × ' + esc(c.name) + '</li>').join('')
        + (items.length ? '' : '<li class="ts">（空）</li>') + '</ul></div>';
    }
    html += '<div class="zone"><b>合计</b>：' + d.total + ' 张</div>';
    document.getElementById('zones').innerHTML = html;
    document.getElementById('warnings').textContent =
      (d.warnings && d.warnings.length) ? d.warnings.join('\\n') : '—';
  } catch (e) { showErrors('轮询失败: ' + e); }
}
document.getElementById('importBtn').onclick = async () => {
  try {
    const r = await fetch('/api/builds/import', {
      method: 'POST',
      headers: {'Content-Type': 'text/plain; charset=utf-8',
                'X-Source-Name': document.getElementById('srcname').value},
      body: document.getElementById('pool').value});
    const d = await r.json();
    if (!r.ok) {
      showErrors('导入失败（HTTP ' + r.status + '）: '
        + (d.error ? d.error.type + ': ' + d.error.message : JSON.stringify(d)));
    } else { showErrors(''); }
    tick();
  } catch (e) { showErrors('导入请求失败: ' + e); }
};
document.getElementById('exportBtn').onclick = () => { window.open('/api/export'); };
setInterval(tick, """ + str(POLL_INTERVAL_MS) + """); tick();
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ serve/CLI

def serve(host, port):
    """启动工作台（前台阻塞）。端口占用等启动失败抛 WorkbenchError。"""
    state = WorkbenchState()
    try:
        server = ThreadingHTTPServer((host, port), make_handler(state))
    except OSError as exc:
        raise WorkbenchError(
            "无法在 {}:{} 启动工作台（端口被占用或地址非法）: {}".format(
                host, port, exc)) from exc
    actual_port = server.server_address[1]
    print("MTG 套牌工作台: http://{}:{}/  （Ctrl+C 退出）".format(host, actual_port),
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    child = sub.add_parser("serve", help="启动网页工作台 hub（前台阻塞）")
    child.add_argument("--host", default=DEFAULT_HOST)
    child.add_argument("--port", type=int, default=DEFAULT_PORT,
                       help="默认 {}（避开 8642 对局监控 / 8643 轮抓面板）".format(DEFAULT_PORT))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return serve(args.host, args.port)
    except WorkbenchError as exc:
        print("[error] " + str(exc), file=sys.stderr)
        runlog.log_run("deck_workbench", "error", "serve " + str(exc))
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(runlog.run_logged("deck_workbench", main))
