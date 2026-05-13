@echo off
setlocal
title Tender Finder
cd /d "%~dp0"

echo ====================================================
echo  Tender Finder - launcher
echo  Working dir: %CD%
echo ====================================================
echo.

REM Step 1: Docker installed?
where docker >nul 2>&1
if errorlevel 1 goto no_docker

REM Step 2: Docker daemon running?
docker info >nul 2>&1
if errorlevel 1 goto try_start_docker
goto docker_ready

:try_start_docker
echo Docker Desktop is not running. Trying to launch it...
if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
) else (
    echo Could not find Docker Desktop at the standard path.
    echo Please open Docker Desktop manually, wait until the whale icon
    echo in the tray stops animating, then run start.bat again.
    echo.
    pause
    exit /b 1
)
echo Waiting for Docker to become ready (30-90 seconds)...
set /a tries=0
:wait_docker
timeout /t 5 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
set /a tries+=1
if %tries% lss 24 goto wait_docker
echo Docker did not become ready in 2 minutes.
echo Please open Docker Desktop manually and run start.bat again.
echo.
pause
exit /b 1

:docker_ready
echo [OK] Docker is running.
echo.

REM Step 3: Compose file present?
if not exist "docker-compose.yml" (
    echo [ERROR] docker-compose.yml not found in this folder.
    echo Make sure start.bat is in the unpacked tender-finder folder
    echo alongside docker-compose.yml.
    echo Current folder: %CD%
    echo.
    pause
    exit /b 1
)

echo ====================================================
echo  Building and starting containers...
echo  First run downloads qwen2.5:3b (~2 GB), takes 5-15 min.
echo  Subsequent runs are fast.
echo ====================================================
echo.

docker compose up -d --build
if errorlevel 1 goto compose_failed

echo.
echo Waiting for backend health check...
set /a tries=0
:wait_backend
timeout /t 3 /nobreak >nul
curl -s -o NUL -w "%%{http_code}" http://localhost:8000/api/system/health > "%TEMP%\tf_health.txt" 2>NUL
set /p HTTP_CODE=<"%TEMP%\tf_health.txt"
del "%TEMP%\tf_health.txt" >nul 2>&1
if "%HTTP_CODE%"=="200" goto backend_ready
set /a tries+=1
if %tries% lss 100 goto wait_backend
echo Backend did not respond in 5 minutes. Showing recent logs:
docker compose logs --tail=50 backend
echo.
pause
exit /b 1

:backend_ready
echo [OK] Backend is up.
echo.
echo Opening http://localhost:5173 in your default browser...
start "" "http://localhost:5173"

echo.
echo ====================================================
echo  Tender Finder is running.
echo.
echo  URL:    http://localhost:5173
echo  Stop:   double-click stop.bat
echo  Logs:   docker compose logs -f
echo ====================================================
echo.
pause
exit /b 0

:no_docker
echo [ERROR] Docker Desktop is not installed (or not on PATH).
echo.
echo Install Docker Desktop:
echo   https://www.docker.com/products/docker-desktop/
echo.
echo After installation, launch Docker Desktop, wait until it is fully
echo started, then run start.bat again.
echo.
pause
exit /b 1

:compose_failed
echo.
echo [ERROR] docker compose failed. Recent logs:
docker compose logs --tail=80
echo.
pause
exit /b 1
