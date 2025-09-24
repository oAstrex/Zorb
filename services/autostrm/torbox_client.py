import os
import time
import typing as t
import logging
import requests

log = logging.getLogger("torbox")
log.setLevel(logging.INFO)


class TorBoxError(Exception):
    pass


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


class TorBoxClient:
    """
    TorBox API client aligned to the provided OpenAPI.

    Auth
    - Use Authorization: Bearer <API_KEY> header for all secured endpoints.
    - Base URL defaults to https://api.torbox.app and can be overridden via TORBOX_BASE_URL.

    Key endpoints used
    - POST /v1/api/torrents/asynccreatetorrent  (multipart/form-data)
    - GET  /v1/api/torrents/mylist              (status/details)
    - POST /v1/api/torrents/controltorrent      (pause/resume/delete)
    - DELETE /v1/api/integration/job/{job_id}   (not used by default here)
    - GET  /v1/api/stream/createstream          (stream tokens)
    - GET  /v1/api/stream/getstreamdata         (resolve streamable URL)
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or _env("TORBOX_BASE_URL") or "https://api.torbox.app").rstrip("/")
        self.api_key = api_key or _env("TORBOX_API_KEY")
        if not self.api_key:
            log.warning("TORBOX_API_KEY not set; TorBox operations will fail.")
        self.timeout = timeout
        self.session = session or requests.Session()

    # --------------- Low-level HTTP helpers ---------------

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _get(self, path: str, params: dict | None = None) -> requests.Response:
        url = self._url(path)
        resp = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        self._raise_for_error(resp, url)
        return resp

    def _post_json(self, path: str, payload: dict) -> requests.Response:
        url = self._url(path)
        resp = self.session.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        self._raise_for_error(resp, url)
        return resp

    def _post_form(self, path: str, data: dict, files: dict | None = None) -> requests.Response:
        url = self._url(path)
        headers = dict(self._headers())
        headers.pop("Accept", None)  # let requests set multipart headers
        resp = self.session.post(url, headers=headers, data=data, files=files, timeout=self.timeout)
        self._raise_for_error(resp, url)
        return resp

    @staticmethod
    def _raise_for_error(resp: requests.Response, url: str) -> None:
        if 200 <= resp.status_code < 300:
            return
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:1000]
        raise TorBoxError(f"HTTP {resp.status_code} for {url}: {body}")

    @staticmethod
    def _json(resp: requests.Response) -> dict | list | None:
        try:
            return resp.json()
        except Exception:
            log.debug("Non-JSON response: %s", resp.text[:500])
            return None

    # --------------- Torrent creation ---------------

    def submit_magnet(
        self,
        magnet: str,
        name: str | None = None,
        seed: int | None = None,
        add_only_if_cached: bool | None = None,
        as_queued: bool | None = None,
        allow_zip: bool | None = None,
        category: str | None = None,  # accepted for compatibility; not used by TorBox API
        tags: str | None = None,      # accepted for compatibility; not used by TorBox API
    ) -> t.Any:
        """
        Create a torrent from a magnet (async).
        Returns a single task identifier suitable for storage (prefers torrent_id, then queued_id, then info_hash).
        """
        if not magnet:
            raise TorBoxError("submit_magnet requires a magnet string")
        data: dict[str, t.Any] = {"magnet": magnet}
        if name is not None:
            data["name"] = name
        if seed is not None:
            data["seed"] = seed
        if add_only_if_cached is not None:
            data["add_only_if_cached"] = bool(add_only_if_cached)
        if as_queued is not None:
            data["as_queued"] = bool(as_queued)
        if allow_zip is not None:
            data["allow_zip"] = bool(allow_zip)

        log.info("TorBox: creating torrent (magnet, async)")
        resp = self._post_form("/v1/api/torrents/asynccreatetorrent", data=data, files=None)
        obj = self._json(resp) or {}
        result = self._extract_creation_result(obj)
        task_id = self._choose_task_id(result)
        if task_id is None:
            log.warning("TorBox: could not determine task id from creation response: %s", result)
        return task_id

    def submit_torrent_file(
        self,
        file_bytes: bytes,
        name: str | None = None,
        seed: int | None = None,
        add_only_if_cached: bool | None = None,
        as_queued: bool | None = None,
        allow_zip: bool | None = None,
        category: str | None = None,  # accepted for compatibility
        tags: str | None = None,      # accepted for compatibility
    ) -> t.Any:
        """
        Create a torrent from a .torrent file (async).
        Returns a single task identifier suitable for storage (prefers torrent_id, then queued_id, then info_hash).
        """
        if not file_bytes:
            raise TorBoxError("submit_torrent_file requires file bytes")
        data: dict[str, t.Any] = {}
        if name is not None:
            data["name"] = name
        if seed is not None:
            data["seed"] = seed
        if add_only_if_cached is not None:
            data["add_only_if_cached"] = bool(add_only_if_cached)
        if as_queued is not None:
            data["as_queued"] = bool(as_queued)
        if allow_zip is not None:
            data["allow_zip"] = bool(allow_zip)

        files = {"file": ("upload.torrent", file_bytes, "application/x-bittorrent")}
        log.info("TorBox: creating torrent (file, async)")
        resp = self._post_form("/v1/api/torrents/asynccreatetorrent", data=data, files=files)
        obj = self._json(resp) or {}
        result = self._extract_creation_result(obj)
        task_id = self._choose_task_id(result)
        if task_id is None:
            log.warning("TorBox: could not determine task id from creation response: %s", result)
        return task_id

    @staticmethod
    def _extract_creation_result(obj: dict) -> dict:
        """
        Extract best-effort identifiers from the creation response.
        """
        tid = None
        qid = None
        ih = None
        status = None

        if isinstance(obj, dict):
            tid = obj.get("torrent_id") or obj.get("id") or obj.get("torrentId")
            qid = obj.get("queued_id") or obj.get("queuedId")
            ih = obj.get("hash") or obj.get("info_hash") or obj.get("infoHash")
            status = obj.get("status") or obj.get("state")

            # Nested common wrappers
            for k in ("torrent", "data", "result"):
                d = obj.get(k)
                if isinstance(d, dict):
                    tid = tid or d.get("torrent_id") or d.get("id") or d.get("torrentId")
                    qid = qid or d.get("queued_id") or d.get("queuedId")
                    ih = ih or d.get("hash") or d.get("info_hash") or d.get("infoHash")
                    status = status or d.get("status") or d.get("state")

        return {"torrent_id": tid, "queued_id": qid, "info_hash": ih, "status": status, "raw": obj}

    @staticmethod
    def _choose_task_id(parsed: dict) -> t.Any:
        """
        Prefer torrent_id, then queued_id, then info_hash.
        """
        for key in ("torrent_id", "queued_id", "info_hash"):
            v = parsed.get(key)
            if v is not None:
                return v
        return None

    # --------------- Status/listing helpers ---------------

    def get_torrents_mylist(
        self, id: int | None = None, bypass_cache: bool | None = None, offset: int | None = None, limit: int | None = None
    ) -> list[dict]:
        params: dict[str, t.Any] = {}
        if id is not None:
            params["id"] = id
        if bypass_cache is not None:
            params["bypass_cache"] = bool(bypass_cache)
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        resp = self._get("/v1/api/torrents/mylist", params=params)
        data = self._json(resp)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("data", "items", "results"):
                if isinstance(data.get(k), list):
                    return data[k]
            return [data]
        return []

    # --------------- Control/cancel (compat with caller) ---------------

    def control_torrent(self, operation: str, torrent_id: int | None = None, all: bool | None = None) -> dict | None:
        payload: dict[str, t.Any] = {"operation": operation}
        if torrent_id is not None:
            payload["torrent_id"] = torrent_id
        if all is not None:
            payload["all"] = bool(all)
        resp = self._post_json("/v1/api/torrents/controltorrent", payload)
        return self._json(resp) or {}

    def cancel_task(self, task_id: t.Any) -> bool:
        """
        Compatibility wrapper: qbittorrent_compat.py expects cancel_task(task_id).
        We try to interpret task_id and delete the torrent via control_torrent.
        """
        torrent_id: int | None = None
        info_hash: str | None = None

        # If it's a parsed dict
        if isinstance(task_id, dict):
            torrent_id = task_id.get("torrent_id") or task_id.get("id")
            info_hash = task_id.get("info_hash") or task_id.get("hash")

        # If it's a string or int
        elif isinstance(task_id, int):
            torrent_id = task_id
        elif isinstance(task_id, str):
            # numeric -> treat as torrent_id
            if task_id.isdigit():
                torrent_id = int(task_id)
            else:
                # hex-ish -> maybe info hash
                s = task_id.strip().lower()
                if 16 <= len(s) <= 64 and all(c in "0123456789abcdef" for c in s):
                    info_hash = s

        # If we only have an info hash, try to resolve to torrent_id
        if torrent_id is None and info_hash:
            try:
                items = self.get_torrents_mylist(bypass_cache=True)
                for it in items:
                    ih = (it.get("hash") or it.get("info_hash") or "").lower()
                    if ih and ih == info_hash:
                        tid = it.get("torrent_id") or it.get("id")
                        if isinstance(tid, int):
                            torrent_id = tid
                            break
            except Exception as e:
                log.warning("TorBox: error resolving info_hash to torrent_id: %s", e)

        if torrent_id is None:
            log.warning("TorBox: cancel_task could not resolve torrent_id from %r", task_id)
            return False

        try:
            self.control_torrent("delete", torrent_id=torrent_id)
            return True
        except Exception as e:
            log.error("TorBox: cancel_task failed for torrent_id=%s: %s", torrent_id, e)
            return False

    # --------------- Stream helpers ---------------

    def create_stream(self, id: int, file_id: int | None = None, type: str | None = None, chosen_subtitle_index: t.Any = None, chosen_audio_index: int | None = None) -> dict:
        params: dict[str, t.Any] = {"id": id}
        if file_id is not None:
            params["file_id"] = file_id
        if type is not None:
            params["type"] = type
        if chosen_subtitle_index is not None:
            params["chosen_subtitle_index"] = chosen_subtitle_index
        if chosen_audio_index is not None:
            params["chosen_audio_index"] = chosen_audio_index
        resp = self._get("/v1/api/stream/createstream", params=params)
        return self._json(resp) or {}

    def get_stream_data(self, token: str, presigned_token: str, chosen_subtitle_index: int | None = None, chosen_audio_index: int | None = None) -> dict:
        params: dict[str, t.Any] = {
            "token": token,
            "presigned_token": presigned_token,
        }
        if chosen_subtitle_index is not None:
            params["chosen_subtitle_index"] = chosen_subtitle_index
        if chosen_audio_index is not None:
            params["chosen_audio_index"] = chosen_audio_index
        resp = self._get("/v1/api/stream/getstreamdata", params=params)
        return self._json(resp) or {}