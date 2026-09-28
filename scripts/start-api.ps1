[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$apiDirectory = Join-Path $repositoryRoot "services\api"
$composeEnvPath = Join-Path $repositoryRoot ".env"
$postgresPasswordPath = Join-Path $repositoryRoot ".secrets\postgres_password.txt"
$redisPasswordPath = Join-Path $repositoryRoot ".secrets\redis_password.txt"
$pythonPath = Join-Path $apiDirectory ".venv\Scripts\python.exe"

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Name
    )

    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match "^\s*$([Regex]::Escape($Name))\s*=" } |
        Select-Object -Last 1

    if (-not $line) {
        throw "A configuracao obrigatoria '$Name' nao foi encontrada em $Path."
    }

    $value = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
    if (-not $value) {
        throw "A configuracao obrigatoria '$Name' esta vazia em $Path."
    }

    return $value
}

foreach ($requiredPath in @(
    $composeEnvPath,
    $postgresPasswordPath,
    $redisPasswordPath,
    $pythonPath
)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Arquivo obrigatorio nao encontrado: $requiredPath"
    }
}

$postgresUser = Get-DotEnvValue -Path $composeEnvPath -Name "POSTGRES_USER"
$postgresDatabase = Get-DotEnvValue -Path $composeEnvPath -Name "POSTGRES_DB"
$postgresPassword = (Get-Content -LiteralPath $postgresPasswordPath -Raw).Trim()
$redisPassword = (Get-Content -LiteralPath $redisPasswordPath -Raw).Trim()

if (-not $postgresPassword) {
    throw "O arquivo da senha do PostgreSQL esta vazio."
}

if (-not $redisPassword) {
    throw "O arquivo da senha do Redis esta vazio."
}

$encodedPostgresUser = [Uri]::EscapeDataString($postgresUser)
$encodedPostgresDatabase = [Uri]::EscapeDataString($postgresDatabase)
$encodedPostgresPassword = [Uri]::EscapeDataString($postgresPassword)
$encodedRedisPassword = [Uri]::EscapeDataString($redisPassword)

$env:EDISK_DATABASE_URL = (
    "postgresql+asyncpg://{0}:{1}@127.0.0.1:5432/{2}" -f
    $encodedPostgresUser,
    $encodedPostgresPassword,
    $encodedPostgresDatabase
)
$env:EDISK_REDIS_URL = "redis://:$encodedRedisPassword@127.0.0.1:6379/0"
$env:EDISK_OPENBAO_URL = "http://127.0.0.1:8200"

Push-Location $apiDirectory
try {
    & $pythonPath -m uvicorn app.main:app --reload --app-dir src
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
