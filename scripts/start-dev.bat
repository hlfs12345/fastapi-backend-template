@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0.."

set "DOCKER_DESKTOP=C:\Program Files\Docker\Docker\Docker Desktop.exe"
set "DOCKER_ATTEMPTS=0"
set "MAX_DOCKER_ATTEMPTS=60"
set "BAO_STATUS_FILE=%TEMP%\edisk-openbao-status-%RANDOM%.txt"

echo.
echo ========================================
echo   INICIANDO INFRAESTRUTURA DE DESENVOLVIMENTO
echo ========================================
echo.

echo [1] Verificando Docker Engine...
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready

if not exist "%DOCKER_DESKTOP%" (
    echo.
    echo Docker Desktop nao foi encontrado em:
    echo %DOCKER_DESKTOP%
    goto error
)

echo Docker Engine indisponivel. Abrindo Docker Desktop...
start "" "%DOCKER_DESKTOP%"

echo.
echo [2] Aguardando Docker Engine...

:wait_docker
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready

set /a DOCKER_ATTEMPTS+=1
if !DOCKER_ATTEMPTS! GEQ %MAX_DOCKER_ATTEMPTS% (
    echo.
    echo Docker Engine nao ficou disponivel dentro do tempo esperado.
    goto error
)

timeout /t 2 /nobreak >nul
goto wait_docker

:docker_ready
echo Docker Engine disponivel.

echo.
echo [3] Subindo containers e aguardando os servicos...
docker compose up -d --wait --wait-timeout 120

if errorlevel 1 (
    echo.
    echo Falha ao iniciar ou aguardar os containers.
    goto error
)

echo.
echo [4] Containers:
docker compose ps
if errorlevel 1 goto error

echo.
echo [5] Verificando OpenBao...

set "BAO_INITIALIZED="
set "BAO_SEALED="

docker compose exec -T openbao bao status >"%BAO_STATUS_FILE%" 2>&1
set "BAO_STATUS_EXIT=!ERRORLEVEL!"

if not "!BAO_STATUS_EXIT!"=="0" if not "!BAO_STATUS_EXIT!"=="2" (
    type "%BAO_STATUS_FILE%"
    echo.
    echo Nao foi possivel consultar o status do OpenBao.
    goto error
)

for /f "tokens=2" %%A in ('findstr /B "Initialized" "%BAO_STATUS_FILE%"') do set "BAO_INITIALIZED=%%A"
for /f "tokens=2" %%A in ('findstr /B "Sealed" "%BAO_STATUS_FILE%"') do set "BAO_SEALED=%%A"
del /q "%BAO_STATUS_FILE%" >nul 2>&1

if not defined BAO_INITIALIZED (
    echo Nao foi possivel interpretar o estado de inicializacao do OpenBao.
    goto error
)

if /I not "!BAO_INITIALIZED!"=="true" (
    echo.
    echo OpenBao nao esta inicializado. Nao tente usar uma Unseal Key antiga.
    echo Verifique o volume configurado antes de inicializar um novo armazenamento.
    goto error
)

if not defined BAO_SEALED (
    echo Nao foi possivel interpretar o estado de selagem do OpenBao.
    goto error
)

if /I "!BAO_SEALED!"=="true" (
    echo.
    echo OpenBao esta SEALED.
    echo Digite a Unseal Key. Ela ficara oculta:
    echo.

    docker compose exec openbao bao operator unseal

    if errorlevel 1 (
        echo.
        echo Nao foi possivel desbloquear o OpenBao.
        goto error
    )

) else if /I "!BAO_SEALED!"=="false" (
    echo OpenBao ja esta unsealed.
) else (
    echo Estado de selagem inesperado: !BAO_SEALED!
    goto error
)

echo.
echo [6] Status final:
docker compose ps
if errorlevel 1 goto error

echo.
echo ========================================
echo   INFRAESTRUTURA PRONTA
echo ========================================
echo.
echo Para iniciar a API em outro terminal, execute:
echo powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-api.ps1"
echo.
echo O Flutter deve ser iniciado separadamente em apps\edisk.
echo.

pause
exit /b 0

:error
if exist "%BAO_STATUS_FILE%" del /q "%BAO_STATUS_FILE%" >nul 2>&1
echo.
echo ========================================
echo   ERRO AO INICIAR A INFRAESTRUTURA
echo ========================================
echo.
pause
exit /b 1
