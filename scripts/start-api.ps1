[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$apiDirectory = Join-Path $repositoryRoot "services\api"
$composeEnvPath = Join-Path $repositoryRoot ".env"
$postgresPasswordPath = Join-Path $repositoryRoot ".secrets\postgres_password.txt"
$redisPasswordPath = Join-Path $repositoryRoot ".secrets\redis_password.txt"
$jwtSecretPath = Join-Path $repositoryRoot ".secrets\jwt_secret.txt"
$openBaoRoleIdPath = Join-Path $repositoryRoot ".secrets\openbao_role_id.txt"
$openBaoSecretIdPath = Join-Path $repositoryRoot ".secrets\openbao_secret_id.txt"
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
    $openBaoRoleIdPath,
    $openBaoSecretIdPath,
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
$openBaoRoleId = (Get-Content -LiteralPath $openBaoRoleIdPath -Raw).Trim()
$openBaoSecretId = (Get-Content -LiteralPath $openBaoSecretIdPath -Raw).Trim()

if (Test-Path -LiteralPath $jwtSecretPath -PathType Leaf) {
    $jwtSecret = (Get-Content -LiteralPath $jwtSecretPath -Raw).Trim()
} else {
    $jwtSecretBytes = New-Object byte[] 48
    $randomNumberGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $randomNumberGenerator.GetBytes($jwtSecretBytes)
    }
    finally {
        $randomNumberGenerator.Dispose()
    }
    $jwtSecret = [Convert]::ToBase64String($jwtSecretBytes)
    Set-Content -LiteralPath $jwtSecretPath -Value $jwtSecret -Encoding Ascii -NoNewline
    Write-Host "Segredo JWT local criado em .secrets\jwt_secret.txt."
}

if (-not $postgresPassword) {
    throw "O arquivo da senha do PostgreSQL esta vazio."
}

if (-not $redisPassword) {
    throw "O arquivo da senha do Redis esta vazio."
}

if (-not $openBaoRoleId -or -not $openBaoSecretId) {
    throw "As credenciais AppRole do OpenBao nao podem estar vazias."
}

if ($jwtSecret.Length -lt 32) {
    throw "O segredo JWT deve conter pelo menos 32 caracteres."
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
$env:EDISK_OPENBAO_ROLE_ID = $openBaoRoleId
$env:EDISK_OPENBAO_SECRET_ID = $openBaoSecretId
$env:EDISK_AUTH_JWT_SECRET = $jwtSecret

Push-Location $apiDirectory
try {
    & $pythonPath -m uvicorn app.main:app --reload --app-dir src
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
