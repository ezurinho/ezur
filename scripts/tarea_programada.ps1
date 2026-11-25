<#
.SYNOPSIS
Registra las tareas programadas "ezur-paper" y "ezur-watchdog": arrancan el
motor y su vigilante al iniciar sesion, 30 y 60 s mas tarde.

.DESCRIPTION
Las tareas viven fuera del repo (en el Programador de tareas de Windows), asi
que mover la carpeta o reinstalar el sistema las pierde. Este script las vuelve
a crear con las rutas de la copia actual, sin rutas fijas.

"ezur-paper" lanza start_paper.bat (el motor, sin ventana con pythonw).
"ezur-watchdog" lanza scripts\watchdog.py: si el motor deja de responder,
mata solo el proceso que escucha en 8765 y lo relanza.

.PARAMETER Borrar
Quita las dos tareas en vez de crearlas.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_programada.ps1

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_programada.ps1 -Borrar
#>

param([switch]$Borrar)

$ErrorActionPreference = 'Stop'

# Raiz del repo: este script vive en scripts\.
$raiz = Split-Path $PSScriptRoot -Parent
$bat = Join-Path $raiz 'start_paper.bat'
$pythonw = Join-Path $raiz '.venv\Scripts\pythonw.exe'
$watchdog = Join-Path $raiz 'scripts\watchdog.py'

if (-not (Test-Path $bat)) {
    throw "No encuentro $bat; ejecuta el script desde el repo."
}
if (-not (Test-Path $pythonw)) {
    throw "No encuentro $pythonw; crea el entorno con start.bat."
}
if (-not (Test-Path $watchdog)) {
    throw "No encuentro $watchdog."
}

# El motor primero; el vigilante un minuto despues, cuando el arranque ya tuvo
# tiempo de responder. Si el motor tarda mas, el watchdog lo relanza.
$tareas = @(
    @{ Nombre = 'ezur-paper';    Accion = "`"$bat`"";                   Retraso = '0000:30'; Comando = $bat;     Argumentos = '' },
    @{ Nombre = 'ezur-watchdog'; Accion = "`"$pythonw`" `"$watchdog`""; Retraso = '0001:00'; Comando = $pythonw; Argumentos = $watchdog }
)

if ($Borrar) {
    foreach ($t in $tareas) {
        schtasks.exe /Query /TN $t.Nombre *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Tarea '$($t.Nombre)' no existe."
            continue
        }
        schtasks.exe /Delete /TN $t.Nombre /F | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "schtasks no pudo borrar la tarea '$($t.Nombre)' (codigo $LASTEXITCODE)."
        }
        Write-Host "Tarea '$($t.Nombre)' borrada."
    }
    return
}

foreach ($t in $tareas) {
    schtasks.exe /Create /TN $t.Nombre /TR $t.Accion /SC ONLOGON /DELAY $t.Retraso /RL LIMITED /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks no pudo crear la tarea '$($t.Nombre)' (codigo $LASTEXITCODE)."
    }
}

# schtasks puede aceptar la orden y guardar otra cosa (una ruta partida por
# comillas, una tarea vieja que no se sobrescribio). Se lee la accion registrada
# y se compara con esta copia: una tarea que arranca otro fichero es peor que no
# tener tarea, porque parece que esta.
foreach ($t in $tareas) {
    $xml = schtasks.exe /Query /TN $t.Nombre /XML
    if ($LASTEXITCODE -ne 0) {
        throw "no se pudo leer la tarea '$($t.Nombre)' para verificar su accion (codigo $LASTEXITCODE)."
    }
    # La declaracion XML dice UTF-16 y el texto ya viene decodificado: se quita
    # para que el cast a [xml] no intente cambiar de codificacion.
    $texto = ($xml -join "`n") -replace '^\s*<\?xml[^>]*\?>', ''
    $accion = ([xml]$texto).Task.Actions.Exec
    if ($null -eq $accion) {
        throw "la tarea '$($t.Nombre)' no tiene una accion Exec que verificar."
    }
    $comando = "$($accion.Command)".Trim().Trim('"')
    $argumentos = "$($accion.Arguments)".Trim()
    if ($comando -ne $t.Comando) {
        throw "la tarea '$($t.Nombre)' apunta a '$comando' y no a '$($t.Comando)'; no la des por buena."
    }
    if ($t.Argumentos -and $argumentos -notlike "*$($t.Argumentos)*") {
        throw "la tarea '$($t.Nombre)' no pasa '$($t.Argumentos)' (argumentos: '$argumentos')."
    }
    Write-Host "Tarea '$($t.Nombre)' creada y verificada: $comando $argumentos"
}

Write-Host ""
Write-Host "  motor:    $bat (30 s tras iniciar sesion; corre sin ventana)"
Write-Host "  vigilante: $pythonw $watchdog (60 s tras iniciar sesion)"
Write-Host "  logs:     data\run\start_paper.log, data\run\engine.log, data\watchdog.log"
Write-Host ""
schtasks.exe /Query /TN ezur-paper /FO LIST
schtasks.exe /Query /TN ezur-watchdog /FO LIST
