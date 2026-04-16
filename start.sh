#!/bin/sh
# Railway startup wrapper — expands $PORT via shell before exec'ing uvicorn.
# Cannot be replaced with a direct startCommand because Railway passes
# startCommand as argv without shell expansion.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2
