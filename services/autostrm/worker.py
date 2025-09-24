import threading
import time
from typing import Dict
from config import state_store, cfg
from models import JobState
from torbox_client import TorBoxClient, TorBoxError
from strm_generator import generate_strm_files

_worker_thread = None
_worker_stop = False


def _update_jobs_loop(interval_initial: int = 5, interval_max: int = 60):
    client = TorBoxClient()
    backoff = interval_initial

    while not _worker_stop:
        try:
            jobs = state_store.load_jobs()
            changed = False
            for h, j in list(jobs.items()):
                state = j.get("state", JobState.QUEUED.value)

                if state in [JobState.DONE.value, JobState.ERROR.value, JobState.DELETED.value, JobState.PAUSED.value]:
                    continue

                task_id = j.get("torbox_task_id")
                if not task_id:
                    j["state"] = JobState.ERROR.value
                    changed = True
                    continue

                try:
                    status = client.get_status(task_id)
                except TorBoxError:
                    continue

                tor_state = str(status.get("status", "")).lower()
                progress = float(status.get("progress", j.get("progress", 0.0)))

                if tor_state in ("queued", "waiting"):
                    j["state"] = JobState.QUEUED.value
                elif tor_state in ("downloading", "fetching", "transferring"):
                    j["state"] = JobState.DOWNLOADING.value
                elif tor_state in ("processing", "preparing"):
                    j["state"] = JobState.PROCESSING.value
                elif tor_state in ("ready", "complete", "completed", "finished"):
                    j["state"] = JobState.READY.value
                elif tor_state in ("error", "failed"):
                    j["state"] = JobState.ERROR.value

                j["progress"] = max(0.0, min(1.0, progress))

                if j["state"] == JobState.READY.value:
                    try:
                        files = client.list_files(task_id)
                        media_files = [f for f in files if str(f.get("path", "")).lower().endswith((".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv")) or f.get("stream_url")]
                        _generated = generate_strm_files(j, media_files)
                        j["state"] = JobState.DONE.value
                        j["progress"] = 1.0
                    except Exception:
                        j["state"] = JobState.ERROR.value

                changed = True

            if changed:
                state_store.save_jobs(jobs)
                backoff = interval_initial
            else:
                backoff = min(interval_max, int(backoff * 1.5))

        except Exception:
            backoff = min(interval_max, int(backoff * 1.5))

        time.sleep(backoff)


def start_worker():
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    t = threading.Thread(target=_update_jobs_loop, name="autostrm-worker", daemon=True)
    t.start()