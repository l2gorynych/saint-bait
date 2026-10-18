param([Parameter(Mandatory=$true)][string]$Version, [string]$Executable = '')
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Use a version such as 1.1.0' }
$projectDir = $PSScriptRoot
$versionSource = Get-Content -LiteralPath (Join-Path $projectDir 'saint_bait\version.py') -Raw
if ($versionSource -notmatch "VERSION\s*=\s*['`"]$([regex]::Escape($Version))['`"]") { throw 'Bump saint_bait/version.py and rebuild first.' }
$source = if ($Executable) { (Resolve-Path -LiteralPath $Executable).Path } else { Join-Path $projectDir 'Podust.exe' }
$releaseDir = Join-Path $projectDir "releases\$Version"
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
$target = Join-Path $releaseDir 'Saint Bait.exe'
Copy-Item -LiteralPath $source -Destination $target -Force
$manifest = @{
    version = $Version
    file = 'Saint Bait.exe'
    sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    size = (Get-Item -LiteralPath $target).Length
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $releaseDir 'update.json') -Encoding utf8
Write-Output "Prepared: $releaseDir"
