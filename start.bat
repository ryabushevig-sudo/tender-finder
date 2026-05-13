@echo off
chcp 65001 > nul
setlocal enableextensions
title Tender Finder

echo ====================================================
echo  Tender Finder - запуск
echo ====================================================
echo.

REM 1. Проверка Docker Desktop
where docker >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Docker Desktop не установлен.
    echo.
    echo Скачайте и установите Docker Desktop:
    echo   https://www.docker.com/products/docker-desktop/
    echo.
    echo После установки запустите Docker Desktop и снова откройте этот файл.
    echo.
    pause
    exit /b 1
)

REM 2. Проверка, что Docker Desktop запущен
docker info >nul 2>&1
if errorlevel 1 (
    echo [!] Docker Desktop не запущен. Пытаюсь запустить...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe" 2>nul
    if errorlevel 1 (
        echo.
        echo Не удалось запустить Docker Desktop автоматически.
        echo Откройте Docker Desktop вручную и подождите, пока кит/иконка
        echo в трее перестанет вращаться, затем снова запустите start.bat.
        echo.
        pause
        exit /b 1
    )
    echo Ожидаю готовность Docker (это занимает 30-60 секунд)...
    set /a tries=0
    :wait_loop
    timeout /t 5 /nobreak >nul
    docker info >nul 2>&1
    if not errorlevel 1 goto docker_ready
    set /a tries+=1
    if %tries% lss 24 goto wait_loop
    echo.
    echo Docker не стартовал за 2 минуты. Откройте Docker Desktop вручную
    echo и убедитесь, что он полностью запустился, затем запустите start.bat снова.
    echo.
    pause
    exit /b 1
    :docker_ready
)

echo [OK] Docker Desktop работает.
echo.

REM 3. Запуск compose
echo ====================================================
echo  Поднимаю контейнеры (первый запуск займёт 5-15 минут
echo  из-за скачивания модели qwen2.5:3b ~2 ГБ)
echo ====================================================
echo.

docker compose up -d --build
if errorlevel 1 (
    echo.
    echo [ОШИБКА] docker compose не отработал. Полные логи:
    docker compose logs
    pause
    exit /b 1
)

echo.
echo Жду готовность backend...
set /a tries=0
:health_loop
timeout /t 3 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:8000/api/system/health > "%TEMP%\tf_health.txt" 2>nul
set /p HEALTH_CODE=<"%TEMP%\tf_health.txt"
del "%TEMP%\tf_health.txt" >nul 2>&1
if "%HEALTH_CODE%"=="200" goto backend_ready
set /a tries+=1
if %tries% lss 60 goto health_loop
echo Backend не отвечает. Проверьте логи: docker compose logs backend
pause
exit /b 1
:backend_ready

echo [OK] Backend готов.
echo.
echo Открываю http://localhost:5173 в браузере...
start "" "http://localhost:5173"

echo.
echo ====================================================
echo  Tender Finder запущен!
echo.
echo  Откройте: http://localhost:5173
echo.
echo  Для остановки: stop.bat
echo  Логи: docker compose logs -f
echo ====================================================
echo.
pause
