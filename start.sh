#!/bin/sh
# Railway startup wrapper — expands $PORT via shell before exec'ing uvicorn.
# Cannot be replaced with a direct startCommand because Railway passes
# startCommand as argv without shell expansion.
#
# Workers = 2 because prod is on Turso (libSQL HTTP serialises writes
# server-side, so concurrent workers are safe). Drop back to 1 if you
# ever revert to the local SQLite fallback — multiple workers race on
# write locks there and seed fails with 'database is locked'.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 2
