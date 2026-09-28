@echo off
setlocal EnableExtensions

cd /d "%~dp0.."

echo.
echo === DOCKER ===
echo.

docker compose ps

if errorlevel 1 (
    echo.
    echo Nao foi possivel consultar o Docker Compose.
    goto error
)

echo.
echo === OPENBAO ===
echo.

docker compose exec -T openbao bao status
set "BAO_STATUS_EXIT=%ERRORLEVEL%"

if "%BAO_STATUS_EXIT%"=="0" goto api_status
if "%BAO_STATUS_EXIT%"=="2" (
    echo.
    echo OpenBao esta inicializado, mas permanece sealed.
    goto api_status
)

echo.
echo Nao foi possivel consultar o OpenBao.
goto error

:api_status
echo.
echo === API ===
echo.

powershell.exe -NoProfile -Command "try { $response = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/ready' -TimeoutSec 3; $response | ConvertTo-Json -Depth 5 } catch { Write-Output 'API indisponivel ou nao iniciada.' }"

echo.
pause
exit /b 0

:error
echo.
pause
exit /b 1
