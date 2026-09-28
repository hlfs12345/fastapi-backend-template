@echo off
setlocal

cd /d "%~dp0.."

echo.
echo ========================================
echo   ENCERRANDO AMBIENTE DE DESENVOLVIMENTO
echo ========================================
echo.

docker compose down

if errorlevel 1 (
    echo.
    echo Ocorreu um erro ao encerrar os containers.
    pause
    exit /b 1
)

echo.
echo Ambiente encerrado.
echo Volumes foram preservados.
echo.

pause