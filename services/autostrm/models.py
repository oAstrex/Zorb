import time
import hashlib
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional


class JobState(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    READY = "ready"
    DONE = "done"
    ERROR = "error"
    PAUSED = "paused"
    DELETED = "deleted"


@dataclass
class Job:
    hash: str
    name: str
    category: str
    input_type: str  # magnet|torrent
    input_value: str
    torbox_task_id: str | None
    state: str
    progress: float
    size: int
    added_on: int
    eta: int
    dlspeed: int
    upspeed: int

    @staticmethod
    def new(name: str, category: str, input_type: str, input_value: str) -> "Job":
        now = int(time.time())
        seed = f"{name}-{category}-{now}-{input_type}".encode("utf-8")
        h = hashlib.sha1(seed).hexdigest()
        return Job(
            hash=h,
            name=name,
            category=category,
            input_type=input_type,
            input_value=input_value,
            torbox_task_id=None,
            state=JobState.QUEUED.value,
            progress=0.0,
            size=0,
            added_on=now,
            eta=-1,
            dlspeed=0,
            upspeed=0,
        )

    def to_dict(self) -> dict:
        return asdict(self)