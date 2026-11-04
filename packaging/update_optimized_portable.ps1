param([string]$Destination)
$ErrorActionPreference = 'Stop'
$xrayPackage = [IO.Path]::GetFullPath($PSScriptRoot)
if (-not $Destination) {
    Add-Type -AssemblyName System.Windows.Forms
    $xrayPicker = New-Object System.Windows.Forms.FolderBrowserDialog
    $xrayPicker.Description = 'Select the existing XRayReview portable folder'
    if ($xrayPicker.ShowDialog() -ne 'OK') { return }
    $Destination = $xrayPicker.SelectedPath
}
$xrayTarget = (Resolve-Path -LiteralPath $Destination).Path
if ($xrayTarget -eq $xrayPackage -or -not (Test-Path -LiteralPath (Join-Path $xrayTarget 'XRayReview.exe')) -or -not (Test-Path -LiteralPath (Join-Path $xrayTarget 'workspace'))) {
    throw 'Select an existing portable installation, different from this new package.'
}
$xrayRunning = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($xrayTarget + '\',[StringComparison]::OrdinalIgnoreCase) })
if ($xrayRunning.Count) { throw 'Close the existing portable app first. No files were updated.' }
$xrayModel = 'dino-paired-optimized-47-20261104-r3'
$xrayModelTarget = Join-Path $xrayTarget "models\$xrayModel"
if (Test-Path -LiteralPath $xrayModelTarget) {
    $xrayModelSource = Join-Path $xrayPackage "models\$xrayModel"
    foreach ($xrayFile in Get-ChildItem -LiteralPath $xrayModelSource -File -Recurse) {
        $xrayRelative = $xrayFile.FullName.Substring($xrayModelSource.Length + 1)
        $xrayExisting = Join-Path $xrayModelTarget $xrayRelative
        if (-not (Test-Path -LiteralPath $xrayExisting) -or (Get-FileHash -LiteralPath $xrayExisting).Hash -ne (Get-FileHash -LiteralPath $xrayFile.FullName).Hash) { throw 'Existing r3 model differs; preserve it and choose another destination.' }
    }
}
$xrayBefore = @{}
foreach ($xrayFile in Get-ChildItem -LiteralPath (Join-Path $xrayTarget 'workspace') -File -Recurse) {
    $xrayBefore[$xrayFile.FullName] = (Get-FileHash -LiteralPath $xrayFile.FullName -Algorithm SHA256).Hash
}
$xrayBackup = Join-Path $xrayTarget ('_upgrade-backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $xrayBackup | Out-Null
foreach ($xrayName in @('XRayReview.exe','_internal','runtime-gpu','models\active.json','config','BUILD-MANIFEST.json')) {
    $xrayOld = Join-Path $xrayTarget $xrayName
    if (Test-Path -LiteralPath $xrayOld) {
        $xrayBackupParent = Split-Path -Parent (Join-Path $xrayBackup $xrayName)
        New-Item -ItemType Directory -Path $xrayBackupParent -Force | Out-Null
        Copy-Item -LiteralPath $xrayOld -Destination (Join-Path $xrayBackup $xrayName) -Recurse
    }
}
foreach ($xrayName in @('XRayReview.exe','_internal','runtime-gpu','licenses')) {
    $xrayNew = Join-Path $xrayPackage $xrayName
    $xrayExisting = Join-Path $xrayTarget $xrayName
    if ((Get-Item -LiteralPath $xrayNew).PSIsContainer) {
        New-Item -ItemType Directory -Path $xrayExisting -Force | Out-Null
        foreach ($xrayChild in Get-ChildItem -LiteralPath $xrayNew) {
            Copy-Item -LiteralPath $xrayChild.FullName -Destination $xrayExisting -Recurse -Force
        }
    } else { Copy-Item -LiteralPath $xrayNew -Destination $xrayExisting -Force }
}
if (-not (Test-Path -LiteralPath $xrayModelTarget)) { Copy-Item -LiteralPath (Join-Path $xrayPackage "models\$xrayModel") -Destination $xrayModelTarget -Recurse }
Copy-Item -LiteralPath (Join-Path $xrayPackage 'models\active.json') -Destination (Join-Path $xrayTarget 'models\active.json') -Force
Copy-Item -LiteralPath (Join-Path $xrayPackage 'BUILD-MANIFEST.json') -Destination (Join-Path $xrayTarget 'BUILD-MANIFEST.json') -Force
foreach ($xrayPath in $xrayBefore.Keys) {
    if ((Get-FileHash -LiteralPath $xrayPath -Algorithm SHA256).Hash -ne $xrayBefore[$xrayPath]) { throw "Workspace changed unexpectedly: $xrayPath" }
}
Write-Host "Updated to r3; workspace and settings preserved. Previous program backup: $xrayBackup"
