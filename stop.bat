@echo off
chcp 65001 > nul
title Tender Finder - остановка

echo Останавливаю Tender Finder...
docker compose down

echo.
echo Готово. Данные документов сохранены в backend\data, модель Ollama — в Docker volume.
echo Чтобы удалить всё включая модель: docker compose down -v
echo.
pause
