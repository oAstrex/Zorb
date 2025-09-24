#!/bin/sh
set -eu

PUID="${PUID:-501}"
PGID="${PGID:-20}"

# Ensure group exists
if ! getent group autostrm >/dev/null 2>&1; then
  if ! getent group "${PGID}" >/dev/null 2>&1; then
    groupadd -g "${PGID}" autostrm
  else
    # If group with PGID exists, reuse its name
    EXISTING_GROUP="$(getent group "${PGID}" | cut -d: -f1)"
    groupadd autostrm || true
    usermod -g "${PGID}" autostrm 2>/dev/null || true
  fi
fi

# Ensure user exists
if ! id -u autostrm >/dev/null 2>&1; then
  useradd -u "${PUID}" -g "${PGID}" -M -d /app -s /usr/sbin/nologin autostrm || true
fi

# Ensure config and media paths exist
mkdir -p /config /data/media/tv /data/media/movies || true
chown -R "${PUID}:${PGID}" /config /data/media || true

# Drop privileges and exec
exec gosu "${PUID}:${PGID}" "$@"