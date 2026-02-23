# ===============================
# KeyLamp User Installer
# No admin required
# ===============================

$ErrorActionPreference = "Stop"

$AppName = "KeyLamp"
$SourceExe = ".\dist\keylamp.exe"
$InstallDir = "$env:LOCALAPPDATA\KeyLamp"
$TargetExe = "$InstallDir\keylamp.exe"

Write-Host "Installing $AppName for current user..."

# Создание папки
if (!(Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
}

# Копирование exe
Copy-Item $SourceExe $TargetExe -Force
Write-Host "Copied to $InstallDir"

# Удаление старой задачи если есть
schtasks /delete /tn $AppName /f 2>$null

# Создание задачи для текущего пользователя
schtasks /create `
    /tn $AppName `
    /tr "`"$TargetExe`"" `
    /sc onlogon `
    /RL LIMITED `
    /F

Write-Host "Installation complete."
Write-Host "It will start automatically on next login."


# Убить все процессы keylamp.exe
#Stop-Process -Name "keylamp" -Force