# Netcup-only systemd overrides

Hostinger and Netcup have inverted Python environment conventions, confirmed live
2026-09-06:

- **Hostinger**: dependencies installed directly into system `/usr/bin/python3`
  (works — no PEP 668 `externally-managed-environment` restriction encountered there).
  `.venv-core` exists but is empty/unused for these services.
- **Netcup**: Debian 13 enforces PEP 668 — `pip install` into `/usr/bin/python3` fails
  with `externally-managed-environment`. Dependencies live in `.venv-core` instead.

The versioned unit files under `infrastructure/systemd/` (one level up) hard-code
`ExecStart=/usr/bin/python3 ...`, matching Hostinger's real, current production
behavior. Copying them as-is to Netcup makes every service fail immediately
(`FastAPI not installed`) even though the packages ARE installed — just in the wrong
interpreter — and previously drove `dq-dashboard.service` into `start-limit-hit`.

These drop-ins are Netcup-only. Do not merge them into the base unit files (that would
break Hostinger, which has no working `.venv-core`) and do not install them anywhere
except Netcup. Install path is the same as the base drop-ins:
`/etc/systemd/system/<unit>.d/netcup-venv.conf`.

`dq-dashboard.service.d/netcup-venv.conf` also clears and replaces `ExecStartPre` — the
base hardening drop-in's `fuser -k -TERM 8080/tcp` targets Hostinger's dashboard port.
On Netcup the dashboard runs on 8090 (`DQIII8_DASHBOARD_PORT` in `.env` — port 8080 is
`crowdsec`, unrelated to dqiii8). Confirmed live: with the base `ExecStartPre` still in
place, every failed start attempt (and `dq-dashboard.service` failed repeatedly here
before this override existed) sent `fuser -k -TERM` at 8080/tcp and hit crowdsec,
which auto-restarted via its own systemd policy but should never have been targeted at
all.
