"""Bounded background jobs and cached card art for the stdlib workbench."""
import mimetypes
import threading
import time
from pathlib import Path


class JobRegistry:
    def __init__(self, ttl=600, clock=time.monotonic):
        self._lock = threading.Lock()
        self._jobs = {}
        self._counter = 0
        self._ttl = ttl
        self._clock = clock

    def _sweep(self):
        for key, job in list(self._jobs.items()):
            if job.get("finished") is not None and self._clock() - job["finished"] > self._ttl:
                del self._jobs[key]

    def _view(self, job):
        result = job.get("result")
        if result is not None:
            result = {key: value for key, value in result.items() if not key.startswith("_")}
        return {"job_id": job["job_id"], "kind": job["kind"], "status": job["status"],
                "message": job["message"], "current": job["current"], "total": job["total"],
                "elapsed_sec": round((job.get("finished") or self._clock()) - job["started"], 1),
                "source": job["source"], "result": result, "error": job.get("error")}

    def start(self, kind, source, worker):
        with self._lock:
            self._sweep()
            for job in self._jobs.values():
                if job["kind"] == kind and job["status"] == "running":
                    if job["source"] != source:
                        raise ValueError("同类任务仍在运行，请等待完成后重试")
                    return self._view(job)
            finished = [job for job in self._jobs.values() if job["status"] != "running"]
            for job in sorted(finished, key=lambda item: item["started"])[:-7]:
                del self._jobs[job["job_id"]]
            self._counter += 1
            key = "job-{}".format(self._counter)
            job = {"job_id": key, "kind": kind, "source": source, "status": "running",
                   "started": self._clock(), "message": "准备任务", "current": 0, "total": None}
            self._jobs[key] = job
            initial = self._view(job)

        def progress(message, current=0, total=None):
            with self._lock:
                job.update(message=message, current=current, total=total)

        def run():
            try:
                result = worker(progress, key)
                with self._lock:
                    job.update(status="done", result=result, message="完成", finished=self._clock())
            except Exception as exc:
                with self._lock:
                    job.update(status="error", error={"type": type(exc).__name__, "message": str(exc)},
                               message="任务失败", finished=self._clock())

        threading.Thread(target=run, daemon=True).start()
        return initial

    def get(self, key):
        with self._lock:
            self._sweep()
            job = self._jobs.get(key)
            return self._view(job) if job else None

    def image(self, key):
        with self._lock:
            self._sweep()
            job = self._jobs.get(key)
            return (job.get("result") or {}).get("_image") if job else None


_ART_LOCK = threading.Lock()


def card_image(name, download=True):
    """Reuse deck_image's Chinese-first cache; never manufacture a card image."""
    import deck_image

    def cached():
        for prefix in ("mtgch_", "zhs_", ""):
            for ext in (".webp", ".png", ".jpg", ".jpeg"):
                path = Path(deck_image.CACHE_DIR) / (prefix + deck_image._cache_key(name) + ext)
                if path.is_file():
                    return path
        return None

    hit = cached()
    if hit or not download:
        return hit
    with _ART_LOCK:
        hit = cached()
        if hit:
            return hit
        sources = ((deck_image.mtgch_card_info, "mtgch_"),
                   (deck_image.zhs_card_info, "zhs_"),
                   (lambda card: (deck_image.card_info(card)[0], None), ""))
        for fetcher, prefix in sources:
            url, _name = fetcher(name)
            if not url:
                continue
            try:
                return Path(deck_image.fetch_image(url, prefix + deck_image._cache_key(name)))
            except (OSError, ValueError):
                continue
    return None


def image_content_type(path):
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"
