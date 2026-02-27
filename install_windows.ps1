# ===============================
# KeyLamp User Installer (no admin)
# Using dist\keylamp.exe
# ===============================
# Убить все процессы keylamp.exe
#Stop-Process -Name "keylamp" -Force


$ErrorActionPreference = "Stop"

$AppName = "KeyLamp"
$SourceExe = ".\dist\keylamp.exe"
$InstallDir = "$env:LOCALAPPDATA\KeyLamp"
$TargetExe = "$InstallDir\keylamp.exe"
$StartupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$ShortcutPath = Join-Path $StartupFolder "$AppName.lnk"

Write-Host "Installing $AppName for current user..."

# Создать папку установки, если не существует
if (!(Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
}

# Копировать exe из dist
Copy-Item $SourceExe $TargetExe -Force
Write-Host "Copied to $InstallDir"

# Создать ярлык в автозагрузке
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetExe
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Save()

Write-Host "Shortcut created in Startup folder."
# Запустить приложение прямо сейчас
try {
    Start-Process -FilePath $TargetExe -WorkingDirectory $InstallDir
    Write-Host "Started $AppName."
} catch {
    Write-Host "Failed to start $AppName : $_"
}

Write-Host "Installation complete. The app will start automatically on next login."