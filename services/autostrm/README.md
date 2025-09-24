# AutoStrm (RDTClient Replacement)

AutoStrm is a lightweight service that presents a qBittorrent-compatible API to Sonarr/Radarr, forwards magnets/torrents to TorBox, and generates `.strm` files for Jellyfin instead of downloading full media.

## Features

- qBittorrent API compatibility (minimal endpoints used by Sonarr/Radarr)
- TorBox integration for magnet/torrent processing
- Automatic `.strm` generation organized for Jellyfin
- Simple web dashboard
- Dockerized with PUID/PGID support

## Endpoints (qBittorrent-compatible)

- POST `/api/v2/auth/login`
- POST `/api/v2/auth/logout`
- GET `/api/v2/app/version`
- GET `/api/v2/app/buildInfo`
- POST `/api/v2/torrents/add`
- GET `/api/v2/torrents/info`
- POST `/api/v2/torrents/delete`
- GET `/api/v2/torrents/categories`
- POST `/api/v2/torrents/createCategory`
- GET `/api/v2/sync/maindata` (optional aggregate)

## Configuration

Environment variables:

- `PUID` (default: 501)
- `PGID` (default: 20)
- `TZ` (default: UTC)
- `AUTOSTRM_BIND` (default: 0.0.0.0)
- `AUTOSTRM_PORT` (default: 6500)
- `AUTH_USERNAME` (default: autostrm)
- `AUTH_PASSWORD` (default: autostrm)
- `TORBOX_BASE_URL` (required)
- `TORBOX_API_KEY` (required)
- `MEDIA_TV_PATH` (default: /data/media/tv)
- `MEDIA_MOVIES_PATH` (default: /data/media/movies)
- `CATEGORY_TV` (default: tv)
- `CATEGORY_MOVIES` (default: movies)
- `LOG_LEVEL` (default: info)

Volumes:

- `/config` for state and categories JSON
- `/data/media/tv` and `/data/media/movies` for output `.strm` files

## Sonarr/Radarr Setup

- Add a Download Client of type “qBittorrent”.
- Host: `autostrm`
- Port: `6500`
- Username: `AUTH_USERNAME`
- Password: `AUTH_PASSWORD`
- Optional: Set categories in Sonarr/Radarr to `tv` or `movies` (or your configured values) for better organization.

## Notes

- The TorBox API path assumptions may need adjustment. The client expects:
  - POST `${TORBOX_BASE_URL}/api/torrents/add` to return `{ "task_id": "..." }`
  - GET `${TORBOX_BASE_URL}/api/torrents/status/{task_id}` returns `{ "status": "...", "progress": 0.42 }`
  - GET `${TORBOX_BASE_URL}/api/torrents/files/{task_id}` returns `[{"path":"...", "size":123, "stream_url":"..."}]`
- If your TorBox API differs, update `torbox_client.py` accordingly.

## Development

Local run:

```bash
export TORBOX_BASE_URL="https://api.torbox.example"
export TORBOX_API_KEY="YOUR_KEY"
export AUTH_USERNAME="autostrm"
export AUTH_PASSWORD="autostrm"
python -m services.autostrm.app
```

Docker build:

```bash
docker build -t autostrm:local services/autostrm
docker run --rm -p 6500:6500 -e PUID=501 -e PGID=20 -e TORBOX_BASE_URL=... -e TORBOX_API_KEY=... -v $(pwd)/config/autostrm:/config -v $(pwd)/data/media/tv:/data/media/tv -v $(pwd)/data/media/movies:/data/media/movies autostrm:local
```