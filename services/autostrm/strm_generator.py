import os
from typing import List, Dict
from config import cfg
from organizer import MediaOrganizer


def write_text_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    # Apply permissions (best-effort)
    try:
        os.chown(path, cfg.puid, cfg.pgid)
    except Exception:
        pass


def generate_strm_files(job: Dict, files: List[Dict]) -> List[str]:
    """
    Given a job and TorBox files [{path, size, stream_url}], create .strm files.
    Returns list of generated file paths.
    """
    organizer = MediaOrganizer()
    out_paths = []
    for f in files:
        stream_url = f.get("stream_url")
        if not stream_url:
            continue
        rel_path = f.get("path") or os.path.basename(stream_url)
        out_file = organizer.build_output_path(job, rel_path)
        write_text_file(out_file, stream_url.strip() + "\n")
        out_paths.append(out_file)
    return out_paths