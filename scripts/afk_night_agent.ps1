[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$stateDir = Join-Path $root 'data\afk\night-agent'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logPath = Join-Path $stateDir "run-$stamp.log"
$lastPath = Join-Path $stateDir 'last-message.md'
$promptPath = Join-Path $root 'scripts\afk_night_agent_prompt.md'
$lockPath = Join-Path $stateDir 'runner.lock'
$failPath = Join-Path $stateDir 'consecutive-failures.txt'

function Write-RunLog {
    param([string]$Message)
    $line = '[{0}] {1}' -f (Get-Date -Format o), $Message
    Add-Content -Path $logPath -Value $line -Encoding UTF8
}

$lock = $null
try {
    $cutoff = (Get-Date).Date.AddHours(8)
    if ((Get-Date) -ge $cutoff) {
        Write-RunLog 'Fuera de la ventana nocturna; no se ejecuta.'
        exit 0
    }

    if (-not (Test-Path $promptPath)) {
        Write-RunLog "Falta el prompt: $promptPath"
        exit 1
    }

    try {
        $lock = [System.IO.File]::Open(
            $lockPath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    }
    catch {
        Write-RunLog 'Otra corrida sigue activa; se omite esta ventana.'
        exit 0
    }

    $codex = (Get-Command codex -ErrorAction SilentlyContinue).Source
    if (-not $codex) {
        $codex = Join-Path $env:LOCALAPPDATA 'Programs\OpenAI\Codex\bin\codex.exe'
    }
    if (-not (Test-Path $codex)) {
        Write-RunLog 'No se encontró el ejecutable de Codex.'
        exit 1
    }

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $auth = & $codex login status 2>&1
        $authCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($authCode -ne 0 -or (($auth -join "`n") -notmatch 'Logged in')) {
        Write-RunLog 'Codex no tiene sesión iniciada; se aborta.'
        exit 1
    }

    $prompt = Get-Content -Path $promptPath -Raw
    if ([string]::IsNullOrWhiteSpace($prompt)) {
        Write-RunLog 'El prompt está vacío; se aborta.'
        exit 1
    }

    Write-RunLog "Inicio del turno. Codex: $codex"
    if ($DryRun) {
        Write-RunLog 'Dry run correcto; no se invoca a Codex.'
        exit 0
    }

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $prompt | & $codex exec `
            --cd $root `
            --dangerously-bypass-approvals-and-sandbox `
            --color never `
            --output-last-message $lastPath `
            - 2>&1 | ForEach-Object {
                Add-Content -Path $logPath -Value $_ -Encoding UTF8
                Write-Output $_
            }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    $fails = 0
    if (Test-Path $failPath) {
        $rawFails = (Get-Content -Path $failPath -Raw).Trim()
        if ($rawFails -match '^\d+$') {
            $fails = [int]$rawFails
        }
    }

    if ($exitCode -eq 0) {
        Set-Content -Path $failPath -Value '0' -Encoding ASCII
    }
    else {
        $fails++
        Set-Content -Path $failPath -Value "$fails" -Encoding ASCII
        Write-RunLog "Codex falló con código $exitCode; fallos consecutivos: $fails."
        if ($fails -ge 3) {
            try {
                Disable-ScheduledTask -TaskName 'ezur-night-agent' -ErrorAction Stop | Out-Null
                Write-RunLog 'Tres fallos consecutivos: tarea ezur-night-agent deshabilitada.'
            }
            catch {
                Write-RunLog "No se pudo deshabilitar la tarea: $($_.Exception.Message)"
            }
        }
    }

    $lastText = if (Test-Path $lastPath) {
        Get-Content -Path $lastPath -Raw
    }
    else {
        '(Codex no dejó mensaje final.)'
    }

    $summary = @"
# Turno nocturno — $stamp

- Código de salida: $exitCode
- Fallos consecutivos: $fails
- Log: $logPath
- Prompt: $promptPath

## Mensaje final de Codex

$lastText
"@
    Set-Content -Path (Join-Path $stateDir 'latest.md') -Value $summary -Encoding UTF8
    Add-Content -Path (Join-Path $stateDir 'history.md') -Value $summary -Encoding UTF8

    Write-RunLog "Fin del turno con código $exitCode."
    exit $exitCode
}
catch {
    Write-RunLog "Error no controlado: $($_.Exception.Message)"
    exit 1
}
finally {
    if ($lock) {
        $lock.Dispose()
    }
}
