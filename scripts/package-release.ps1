param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputDirectory = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$Label = "beta"
)

$ErrorActionPreference = "Stop"

$projectFile = Join-Path $ProjectRoot "pyproject.toml"
$versionLine = Select-String -LiteralPath $projectFile -Pattern '^version = "([^"]+)"$' | Select-Object -First 1
if (-not $versionLine) {
    throw "Unable to read the project version from pyproject.toml"
}
$version = $versionLine.Matches[0].Groups[1].Value
$baseName = "UltraSkellyAdvanced-$version-$Label"
$destination = Join-Path $OutputDirectory "$baseName.zip"
$checksumPath = "$destination.sha256"
$staging = Join-Path ([IO.Path]::GetTempPath()) ("usa-release-" + [guid]::NewGuid().ToString("N"))

try {
    New-Item -ItemType Directory -Path $staging | Out-Null

    foreach ($directory in @("deploy", "docs", "image", "releases", "scripts", "tests")) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $directory) -Destination $staging -Recurse
    }
    New-Item -ItemType Directory -Path (Join-Path $staging "src") | Out-Null
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "src\skelly_ai") -Destination (Join-Path $staging "src") -Recurse

    foreach ($file in @(
        ".gitignore",
        "Banner Image.png",
        "DISTRIBUTION.md",
        "NOTICE.md",
        "pyproject.toml",
        "QUICK_START.md",
        "README.md",
        "RELEASE_NOTES.md"
    )) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $file) -Destination $staging
    }

    Get-ChildItem -LiteralPath $staging -Directory -Recurse -Force |
        Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") } |
        Sort-Object FullName -Descending |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $staging -File -Recurse -Force |
        Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
        Remove-Item -Force

    Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $destination -CompressionLevel Optimal -Force
    $hash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
    Set-Content -LiteralPath $checksumPath -Encoding ascii -NoNewline -Value "$hash  $baseName.zip`n"

    Write-Output "Archive: $destination"
    Write-Output "Checksum: $checksumPath"
    Write-Output "SHA-256: $hash"
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}
