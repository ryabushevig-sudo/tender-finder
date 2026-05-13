@echo off
setlocal
title Tender Finder - stop
cd /d "%~dp0"

echo Stopping Tender Finder...
docker compose down

echo.
echo Done. Document data is kept in backend\data, model is kept in the
echo Docker volume. To remove everything including the model, run:
echo   docker compose down -v
echo.
pause
