"""Fake `kimi` print-mode CLI for workbench_agent_kimi tests (stdio only).

Reads one JSONL user message from stdin, then emits stream-json lines.
Controlled by env vars:
  KIMI_FAKE_MODE   ok (default) / meta / empty / fail1 / fail75 / slow
  KIMI_FAKE_HELP   full (default) / limited (omit --input-format)
  KIMI_FAKE_LOG    append {"argv", "stdin"} JSON lines to this file
  KIMI_FAKE_DELAY  seconds to sleep in slow mode (default 5)
"""
import json
import os
import sys
import time

HELP_FULL = """usage: kimi [options]
  --print
  -p, --prompt
  --input-format
  --output-format
  --session
  --continue
"""


def main():
    if "--help" in sys.argv:
        sys.stdout.write("" if os.environ.get("KIMI_FAKE_HELP") == "limited" else HELP_FULL)
        return 0
    mode = os.environ.get("KIMI_FAKE_MODE", "ok")
    line = sys.stdin.readline()
    log = os.environ.get("KIMI_FAKE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"argv": sys.argv[1:], "stdin": line.strip()},
                                ensure_ascii=False) + "\n")
    if mode == "fail1":
        sys.stderr.write("authentication failed\n")
        return 1
    if mode == "fail75":
        sys.stderr.write("rate limited by provider\n")
        return 75
    if mode == "meta":
        sys.stdout.write(json.dumps({"meta": {"session_id": "kimi-fake-session"}}) + "\n")
    if mode == "slow":
        time.sleep(float(os.environ.get("KIMI_FAKE_DELAY", "5")))
    if mode != "empty":
        sys.stdout.write(json.dumps({
            "role": "assistant", "content": "我先查一下。",
            "tool_calls": [{"type": "function", "id": "tc_1",
                            "function": {"name": "Shell", "arguments": "{}"}}]}) + "\n")
        sys.stdout.write(json.dumps({"role": "tool", "tool_call_id": "tc_1",
                                     "content": "ok"}) + "\n")
        sys.stdout.write(json.dumps({"role": "assistant", "content": json.dumps(
            {"status": "ok", "message": "完成", "result": {"evidence": ["e1"]}},
            ensure_ascii=False)}) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
