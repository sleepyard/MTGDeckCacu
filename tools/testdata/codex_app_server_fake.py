"""JSONL fixture: deterministic app-server handshake, notification and EOF."""
import json
import sys


for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    method = request["method"]
    if method == "probe/event":
        print(json.dumps({"method": "item/started", "params": {"item": {"type": "commandExecution"}}}), flush=True)
        print(json.dumps({"id": request["id"], "result": {"ok": True}}), flush=True)
    elif method == "probe/error":
        print(json.dumps({"id": request["id"], "error": {"message": "fixture failure"}}), flush=True)
    elif method == "probe/exit":
        sys.exit(0)
    else:
        print(json.dumps({"id": request["id"], "result": {"method": method}}), flush=True)
