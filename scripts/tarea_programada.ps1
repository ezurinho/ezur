<#
.SYNOPSIS
Registra la tarea programada "ezur-paper": arranca start_paper.bat al iniciar
sesion, 30 s mas tarde. El servidor corre sin ventana con pythonw.

.DESCRIPTION
La tarea vive fuera del repo (en el Programador de tareas de Windows), asi que
mover la carpeta o reinstalar el sistema la pierde. Este script la vuelve a
crear con las rutas de la copia actual, sin rutas fijas.

.PARAMETER Borrar
Quita la tarea en vez de crearla.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_programada.ps1

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tarea_programada.ps1 -Borrar
#>

param([switch]$Borrar)

$ErrorActionPreference = 'Stop'
$nombre = 'ezur-paper'

# Raiz del repo: este script vive en scripts\.
$raiz = Split-Path $PSScriptRoot -Parent
$bat = Join-Path $raiz 'start_paper.bat'

if (-not (Test-Path $bat)) {
    throw "No encuentro $bat; ejecuta el script desde el repo."
}

if ($Borrar) {
    schtasks.exe /Delete /TN $nombre /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks no pudo borrar la tarea (codigo $LASTEXITCODE)."
    }
    Write-Host "Tarea '$nombre' borrada."
    return
}

# La tarea lanza el .bat tal cual: el servidor corre con pythonw en segundo
# plano, asi que la consola de la tarea se cierra en cuanto el .bat termina.
$accion = "`"$bat`""

schtasks.exe /Create /TN $nombre /TR $accion /SC ONLOGON /DELAY 0000:30 /RL LIMITED /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "schtasks no pudo crear la tarea (codigo $LASTEXITCODE)."
}

# schtasks puede aceptar la orden y guardar otra cosa (una ruta partida por
# comillas, una tarea vieja que no se sobrescribio). Se lee la accion registrada
# y se compara con esta copia: una tarea que arranca otro fichero es peor que no
# tener tarea, porque parece que esta.
$xml = schtasks.exe /Query /TN $nombre /XML
if ($LASTEXITCODE -ne 0) {
    throw "no se pudo leer la tarea '$nombre' para verificar su accion (codigo $LASTEXITCODE)."
}
# La declaracion XML dice UTF-16 y el texto ya viene decodificado: se quita para
# que el cast a [xml] no intente cambiar de codificacion.
$texto = ($xml -join "`n") -replace '^\s*<\?xml[^>]*\?>', ''
$registrada = ([xml]$texto).Task.Actions.Exec.Command
if ($null -eq $registrada) {
    throw "la tarea '$nombre' no tiene una accion Exec que verificar."
}
$registrada = $registrada.Trim().Trim('"')
if ($registrada -ne $bat) {
    throw "la tarea '$nombre' apunta a '$registrada' y no a '$bat'; no la des por buena."
}

Write-Host "Tarea '$nombre' creada y verificada: la accion apunta a $bat"
Write-Host "  arranca: $bat (30 s tras iniciar sesion; el servidor corre sin ventana)"
Write-Host "  logs:    data\run\start_paper.log y data\run\engine.log"
Write-Host ""
schtasks.exe /Query /TN $nombre /FO LIST
