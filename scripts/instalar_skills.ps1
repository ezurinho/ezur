# Instala las skills de trading del repo en el directorio personal del agente.
# Uso: pwsh -File scripts/instalar_skills.ps1
$ErrorActionPreference = "Stop"

$source = Join-Path $PSScriptRoot "..\.agents\skills"
$target = Join-Path $env:USERPROFILE ".agents\skills"

if (-not (Test-Path $source)) { throw "No existe $source" }
New-Item -ItemType Directory -Force -Path $target | Out-Null

$skills = Get-ChildItem $source -Directory | Where-Object { $_.Name -like "trading-*" }
if (-not $skills) { throw "No hay skills trading-* en $source" }

foreach ($skill in $skills) {
    $dest = Join-Path $target $skill.Name
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    Copy-Item $skill.FullName $dest -Recurse
    Write-Output "instalada $($skill.Name)"
}