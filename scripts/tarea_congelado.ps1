<#
.SYNOPSIS
Registra la tarea mensual "ezur-freeze-btc-5m": actualiza data\btc_5m.pkl
desde el cache de research y verifica huecos y duplicados.

.DESCRIPTION
La tarea vive fuera del repo (Programador de tareas de Windows). Este script
la vuelve a crear con las rutas de la copia actual. Corre el dia 1 de cada mes
a las 03:00 y llama a research_engine\research\freeze_btc_5m.py --quiet.

El congelador completa los dias que falten con los archivos diarios de Binance
Vision (los mensuales solo existen cuando el mes ha terminado), rellena huecos
con el archivo diario y no escribe si quedan duplicados, huecos u OHLC
invalidas. El resumen queda en data\freeze_btc_5m.log y el manifiesto en
data\btc_5m.freeze.json.

.PARAMETER Borrar
Quita la tarea en vez de crearla.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_congelado.ps1

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_congelado.ps1 -Borrar
#>

param([switch]$Borrar)

$ErrorActionPreference = 'Stop'

$raiz = Split-Path $PSScriptRoot -Parent
$python = Join-Path $raiz '.venv\Scripts\python.exe'
$freeze = Join-Path $raiz 'research_engine\research\freeze_btc_5m.py'
$nombre = 'ezur-freeze-btc-5m'

if (-not (Test-Path $python)) {
    throw "No encuentro $python; crea el entorno con start.bat."
}
if (-not (Test-Path $freeze)) {
    throw "No encuentro $freeze."
}

if ($Borrar) {
    schtasks.exe /Query /TN $nombre *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Tarea '$nombre' no existe."
        return
    }
    schtasks.exe /Delete /TN $nombre /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks no pudo borrar la tarea '$nombre' (codigo $LASTEXITCODE)."
    }
    Write-Host "Tarea '$nombre' borrada."
    return
}

$accion = "`"$python`" `"$freeze`" --quiet"
schtasks.exe /Create /TN $nombre /TR $accion /SC MONTHLY /D 1 /ST 03:00 /RL LIMITED /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "schtasks no pudo crear la tarea '$nombre' (codigo $LASTEXITCODE)."
}

# Leer lo registrado y compararlo: una tarea que apunta a otro fichero es peor
# que no tener tarea, porque parece que esta.
$xml = schtasks.exe /Query /TN $nombre /XML
if ($LASTEXITCODE -ne 0) {
    throw "no se pudo leer la tarea '$nombre' para verificarla (codigo $LASTEXITCODE)."
}
$texto = ($xml -join "`n") -replace '^\s*<\?xml[^>]*\?>', ''
$tarea = [xml]$texto
$exec = $tarea.Task.Actions.Exec
if ($null -eq $exec) {
    throw "la tarea '$nombre' no tiene una accion Exec que verificar."
}
$comando = "$($exec.Command)".Trim().Trim('"')
$argumentos = "$($exec.Arguments)".Trim()
if ($comando -ne $python) {
    throw "la tarea '$nombre' apunta a '$comando' y no a '$python'; no la des por buena."
}
if ($argumentos -notlike "*$freeze*") {
    throw "la tarea '$nombre' no pasa '$freeze' (argumentos: '$argumentos')."
}

$calendario = $tarea.Task.Triggers.CalendarTrigger
if ($null -eq $calendario) {
    throw "la tarea '$nombre' no tiene un disparador mensual."
}
$dia = "$($calendario.ScheduleByMonth.DaysOfMonth.Day)".Trim()
$inicio = "$($calendario.StartBoundary)".Trim()
if ($dia -ne '1') {
    throw "la tarea '$nombre' se dispara el dia '$dia' y no el 1."
}
if ($inicio -notlike '*T03:00:00') {
    throw "la tarea '$nombre' arranca a '$inicio' y no a las 03:00."
}

Write-Host "Tarea '$nombre' creada y verificada: $comando $argumentos"
Write-Host "Disparo: dia 1 de cada mes, 03:00; log: data\freeze_btc_5m.log"
Write-Host ""
schtasks.exe /Query /TN $nombre /V /FO LIST
