<#
Copies the insectoids into a Unity project, under Assets/Insectoids:
  unity/Insectoids/Runtime, Editor        -> Assets/Insectoids/Scripts/Runtime, Editor
  export/<Creature>.fbx (Spider, Spiderling, Broodmother, Wasp, Centipede, SpiderEgg_*) -> Assets/Insectoids/Models
  export/Anims/<Creature>@*.fbx, *.json   -> Assets/Insectoids/Models/Anims
  textures/T_*.png                        -> Assets/Insectoids/Textures
Files are overwritten in place; their .meta files (import settings, prefab references) are kept.
Afterwards, in Unity: Tools > Insectoids > Rebuild Spider / Wasp / Centipede / Spider Eggs / Spiderling / Broodmother
(each runs by itself the first time, if the editor is in the foreground).

Usage:
  powershell -ExecutionPolicy Bypass -File tools\install_to_unity.ps1 -Project E:\Unity\Projects\MedievalSetting
  add -ScriptsOnly to copy only the C# scripts
#>
param(
    [Parameter(Mandatory = $true)][string]$Project,
    [switch]$ScriptsOnly
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$Project = (Resolve-Path $Project).Path
$assets = Join-Path $Project 'Assets'
if (-not (Test-Path $assets)) { throw "No Assets folder in $Project - is it a Unity project?" }
$dst = Join-Path $assets 'Insectoids'

function Copy-Into([string]$from, [string]$filter, [string]$to) {
    New-Item -ItemType Directory -Force -Path $to | Out-Null
    $files = @(Get-ChildItem -Path $from -Filter $filter -File)
    foreach ($f in $files) { Copy-Item -LiteralPath $f.FullName -Destination $to -Force }
    Write-Host ("{0,3} x {1,-16} -> {2}" -f $files.Count, $filter, $to.Substring($Project.Length + 1))
}

Copy-Into (Join-Path $root 'unity\Insectoids\Runtime') '*.cs' (Join-Path $dst 'Scripts\Runtime')
Copy-Into (Join-Path $root 'unity\Insectoids\Editor') '*.cs' (Join-Path $dst 'Scripts\Editor')
if (-not $ScriptsOnly) {
    Copy-Into (Join-Path $root 'export') '*.fbx' (Join-Path $dst 'Models')
    Copy-Into (Join-Path $root 'export\Anims') '*@*.fbx' (Join-Path $dst 'Models\Anims')
    Copy-Into (Join-Path $root 'export\Anims') '*.json' (Join-Path $dst 'Models\Anims')
    Copy-Into (Join-Path $root 'textures') 'T_*.png' (Join-Path $dst 'Textures')
}
Write-Host 'Done. In Unity: Tools > Insectoids > Rebuild Spider Eggs, then Rebuild Spiderling and Rebuild Broodmother (and Spider / Wasp / Centipede)'
