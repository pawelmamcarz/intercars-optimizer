#!/bin/sh
# Railway startup wrapper — expands $PORT via shell before exec'ing uvicorn.
# Cannot be replaced with a direct startCommand because Railway passes
# startCommand as argv without shell expansion.
#
# Workers = 1 because the prod deploy currently uses a local SQLite file
# (FLOW_TURSO_DATABASE_URL not set) and 2+ workers race on writes, which
# manifests as "database is locked" mid-seed. Bump back up to 2+ after
# wiring real Turso credentials — the libSQL HTTP layer serialises
# server-side.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
