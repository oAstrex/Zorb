import time
import re
import secrets
from urllib.parse import parse_qs, urlparse, unquote
from flask import Blueprint, request, jsonify, make_response, session, render_template
from config import cfg, state_store, categories_store
from models import Job, JobState
from torbox_client import TorBoxClient
from strm_generator import generate_strm_files
from organizer import MediaOrganizer

qb_api = Blueprint("qb_api", __name__)
web_ui = Blueprint("web_ui", __name__)
client = TorBoxClient()
organizer = MediaOrganizer()


def _require_auth():
    # Accept either Flask session or qBittorrent-like SID cookie
    if session.get("authenticated"):
        return True
    if request.cookies.get("SID"):
        return True
    return False


def _auth_required_response():
    return make_response("Fails.", 403)


@qb_api.route("/auth/login", methods=["POST"])
def auth_login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    if username == cfg.AUTH_USERNAME and password == cfg.AUTH_PASSWORD:
        session["authenticated"] = True
        resp = make_response("Ok.")
        # Mimic qBittorrent: set SID cookie
        sid = secrets.token_hex(16)
        resp.set_cookie(
            "SID",
            sid,
            httponly=True,
            samesite="Lax",
            path="/",
        )
        return resp
    return make_response("Fails.", 403)


@qb_api.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    resp = make_response("Ok.")
    resp.delete_cookie("SID", path="/")
    return resp


@qb_api.route("/app/version", methods=["GET"])
def app_version():
    # qBittorrent returns text/plain
    resp = make_response("4.6.0")
    resp.headers["Content-Type"] = "text/plain; charset=UTF-8"
    return resp


@qb_api.route("/app/webapiVersion", methods=["GET"])
def app_webapi_version():
    # Many Radarr/Sonarr builds call this during Test
    resp = make_response("2.8.19")
    resp.headers["Content-Type"] = "text/plain; charset=UTF-8"
    return resp


@qb_api.route("/app/buildInfo", methods=["GET"])
def app_build_info():
    return jsonify({
        "qt": "5.15.2",
        "libtorrent": "2.0",
        "boost": "1.82",
        "openssl": "3.0",
        "bitness": 64
    })


@qb_api.route("/app/defaultSavePath", methods=["GET"])
def app_default_save_path():
    # qBittorrent returns a plain text path; not auth-protected
    # Use movies path as a harmless default (Radarr mostly checks this exists syntactically)
    path = organizer.get_save_path_for_category(cfg.CATEGORY_MOVIES)
    resp = make_response(path)
    resp.headers["Content-Type"] = "text/plain; charset=UTF-8"
    return resp


@qb_api.route("/app/preferences", methods=["GET"])
def app_preferences():
    # Minimal preferences structure Radarr/Sonarr sometimes inspect
    return jsonify({
        "locale": "en_US",
        "save_path": organizer.get_save_path_for_category(cfg.CATEGORY_MOVIES),
        "save_path_enabled": True,
        "temp_path_enabled": False,
        "append_extension": False,
        "autorun_enabled": False,
        "use_https": False,
        "web_ui_username": cfg.AUTH_USERNAME,
        "web_ui_password_less": False
    })


@qb_api.route("/torrents/categories", methods=["GET"])
def torrents_categories():
    if not _require_auth():
        return _auth_required_response()
    cats = categories_store.load()
    # qBittorrent returns a dict of {name: {name, savePath}}
    result = {}
    for name, meta in cats.items():
        result[name] = {
            "name": name,
            "savePath": meta.get("savePath", organizer.get_save_path_for_category(name))
        }
    return jsonify(result)


@qb_api.route("/torrents/createCategory", methods=["POST"])
def torrents_create_category():
    if not _require_auth():
        return _auth_required_response()
    name = request.form.get("category")
    save_path = request.form.get("savePath") or organizer.get_save_path_for_category(name)
    if not name:
        return make_response("Missing category", 400)
    categories = categories_store.load()
    categories[name] = {"savePath": save_path}
    categories_store.save(categories)
    return "Ok."


def _magnet_display_name(magnet: str) -> str:
    try:
        q = parse_qs(urlparse(magnet).query)
        dn = q.get("dn", [""])[0]
        if dn:
            return unquote(dn)
    except Exception:
        pass
    return magnet[:70]


def _guess_category(cat: str | None, name: str) -> str:
    if cat:
        return cat
    if re.search(r"S\d{2}E\d{2}", name, re.IGNORECASE):
        return cfg.CATEGORY_TV
    return cfg.CATEGORY_MOVIES


@qb_api.route("/torrents/add", methods=["POST"])
def torrents_add():
    if not _require_auth():
        return _auth_required_response()

    category = request.form.get("category")
    urls = request.form.get("urls")  # magnet(s), newline-separated
    upload = request.files.get("torrents")  # .torrent file
    tags = request.form.get("tags", "")

    jobs = state_store.load_jobs()
    created_any = False

    if urls:
        for line in urls.splitlines():
            line = line.strip()
            if not line:
                continue
            name = _magnet_display_name(line)
            cat = _guess_category(category, name)
            job = Job.new(name=name, category=cat, input_type="magnet", input_value=line)
            task_id = client.submit_magnet(line, name=name, category=cat, tags=tags)
            job.torbox_task_id = task_id
            jobs[job.hash] = job.to_dict()
            created_any = True

    if upload:
        data = upload.read()
        name = upload.filename or "torrent.torrent"
        cat = _guess_category(category, name)
        job = Job.new(name=name, category=cat, input_type="torrent", input_value="")
        task_id = client.submit_torrent_file(data, name=name, category=cat, tags=tags)
        job.torbox_task_id = task_id
        jobs[job.hash] = job.to_dict()
        created_any = True

    if not created_any:
        return make_response("No torrents to add", 400)

    state_store.save_jobs(jobs)
    return "Ok."


def _map_state(job_state: str) -> str:
    mapping = {
        "queued": "queuedDL",
        "downloading": "downloading",
        "processing": "stalledDL",
        "ready": "uploading",
        "error": "error",
        "paused": "pausedDL",
        "done": "pausedUP",
        "deleted": "missingFiles",
    }
    return mapping.get(job_state, "unknown")


@qb_api.route("/torrents/info", methods=["GET"])
def torrents_info():
    if not _require_auth():
        return _auth_required_response()
    jobs = state_store.load_jobs()
    result = []
    for h, j in jobs.items():
        progress = j.get("progress", 0.0)
        size = int(j.get("size", 0))
        downloaded = int(progress * size)
        eta = j.get("eta", -1)
        category = j.get("category", "")
        save_path = organizer.get_save_path_for_category(category)
        result.append({
            "hash": h,
            "name": j.get("name"),
            "progress": progress,
            "state": _map_state(j.get("state")),
            "added_on": j.get("added_on"),
            "save_path": save_path,
            "category": category,
            "eta": eta if isinstance(eta, int) else -1,
            "dlspeed": j.get("dlspeed", 0),
            "upspeed": j.get("upspeed", 0),
            "size": size,
            "downloaded": downloaded,
        })
    return jsonify(result)


@qb_api.route("/torrents/delete", methods=["POST"])
def torrents_delete():
    if not _require_auth():
        return _auth_required_response()
    hashes = request.form.get("hashes", "")
    _delete_files = request.form.get("deleteFiles", "false").lower() == "true"
    jobs = state_store.load_jobs()
    for h in hashes.split("|"):
        h = h.strip()
        if not h:
            continue
        j = jobs.get(h)
        if not j:
            continue
        task_id = j.get("torbox_task_id")
        if task_id:
            try:
                client.cancel_task(task_id)
            except Exception:
                pass
        j["state"] = "deleted"
        j["deleted_at"] = int(time.time())
    state_store.save_jobs(jobs)
    return "Ok."


@qb_api.route("/sync/maindata", methods=["GET"])
def sync_maindata():
    if not _require_auth():
        return _auth_required_response()
    jobs = state_store.load_jobs()
    torrents = {}
    for h, j in jobs.items():
        torrents[h] = {
            "name": j.get("name"),
            "progress": j.get("progress", 0.0),
            "state": _map_state(j.get("state")),
            "category": j.get("category"),
        }
    return jsonify({
        "rid": int(time.time()),
        "torrents": torrents,
        "categories": list(categories_store.load().keys()),
    })


# Web UI
@web_ui.route("/dashboard")
def dashboard():
    jobs = state_store.load_jobs()
    sorted_jobs = sorted(jobs.values(), key=lambda j: j.get("added_on", 0), reverse=True)
    return render_template("index.html", jobs=sorted_jobs, cfg=cfg)