param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$pythonPath = Join-Path $projectDir '.venv\Scripts\python.exe'
$desktopDir = [Environment]::GetFolderPath('Desktop')
$desktopExe = Join-Path $desktopDir 'Saint Bait.exe'
Push-Location -LiteralPath $projectDir
try {
    if (-not $SkipTests) {
        & $pythonPath -m unittest discover -s tests
        if ($LASTEXITCODE -ne 0) { throw 'Tests failed; desktop build was not changed.' }
    }
    $workDir = Join-Path (Split-Path -Parent $projectDir) '.build-check\saint-bait-memory'
    $outputDir = Join-Path $projectDir 'release-build'
    & $pythonPath -m PyInstaller 'Podust.spec' --noconfirm --distpath $outputDir --workpath $workDir
    if ($LASTEXITCODE -ne 0) { throw 'Build failed; desktop build was not changed.' }
    Copy-Item -LiteralPath (Join-Path $outputDir 'Podust.exe') -Destination $desktopExe -Force
    if ((Get-FileHash -LiteralPath $desktopExe).Hash -ne (Get-FileHash -LiteralPath (Join-Path $outputDir 'Podust.exe')).Hash) {
        throw 'Desktop copy verification failed.'
    }
    Write-Output "Updated: $desktopExe"
} finally {
    Pop-Location
}
