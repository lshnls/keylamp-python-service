# ===============================
# KeyLamp User Installer (no admin)
# Using dist\keylamp.exe
# ===============================

param(
    [switch]$Uninstall = $false
)

$ErrorActionPreference = "Stop"

$AppName = "KeyLamp"
$SourceExe = ".\dist\keylamp.exe"
$InstallDir = "$env:LOCALAPPDATA\KeyLamp"
$TargetExe = "$InstallDir\keylamp.exe"
$StartupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$ShortcutPath = Join-Path $StartupFolder "$AppName.lnk"
$LogFile = Join-Path $InstallDir "install.log"

# Функция логирования
function Log {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] $Message"
    Write-Host $LogMessage
    Add-Content -Path $LogFile -Value $LogMessage -ErrorAction SilentlyContinue
}

# ===== UNINSTALL =====
if ($Uninstall) {
    Write-Host "Removing $AppName..."
    
    # Убить процесс
    try {
        Stop-Process -Name "keylamp" -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped $AppName process."
        Start-Sleep -Milliseconds 1000 # Ждем освобождения файлов
    } catch {
        Write-Host "No running process found."
    }
    
    # Удалить ярлык из автозагрузки
    if (Test-Path $ShortcutPath) {
        try {
            Remove-Item $ShortcutPath -Force -ErrorAction Stop
            Write-Host "Removed Startup shortcut."
        } catch {
            Write-Host "WARNING: Could not remove shortcut: $_" -ForegroundColor Yellow
        }
    }
    
    # Удалить установочную папку с повторными попытками
    if (Test-Path $InstallDir) {
        $MaxRetries = 5
        $RetryCount = 0
        $RemovalSuccess = $false
        
        while ($RetryCount -lt $MaxRetries -and -not $RemovalSuccess) {
            try {
                Remove-Item $InstallDir -Recurse -Force -ErrorAction Stop
                Write-Host "Removed installation directory."
                $RemovalSuccess = $true
            } catch {
                $RetryCount++
                if ($RetryCount -lt $MaxRetries) {
                    Write-Host "Attempt $RetryCount failed, retrying in 1 second..." -ForegroundColor Yellow
                    Start-Sleep -Seconds 1
                } else {
                    Write-Host "ERROR: Could not remove directory after $MaxRetries attempts: $_" -ForegroundColor Red
                    exit 1
                }
            }
        }
    }
    
    Write-Host "Uninstallation complete."
    exit 0
}

# ===== INSTALL =====
Write-Host "Installing $AppName for current user..."

# Проверка существования исходного exe
if (!(Test-Path $SourceExe)) {
    Write-Host "ERROR: $SourceExe not found!" -ForegroundColor Red
    Write-Host "Please ensure you are running this script from the project root directory."
    exit 1
}

# Создать папку установки, если не существует
if (!(Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
    Log "Created installation directory: $InstallDir"
} else {
    Log "Installation directory already exists."
}

# Убить существующий процесс перед обновлением
try {
    $ProcessToKill = Get-Process -Name "keylamp" -ErrorAction SilentlyContinue
    if ($ProcessToKill) {
        Stop-Process -InputObject $ProcessToKill -Force
        Log "Stopped running $AppName process."
        Start-Sleep -Milliseconds 500 # небольшая задержка для освобождения файла
    }
} catch {
    Log "No running process to stop."
}

# Копировать exe из dist
try {
    Copy-Item $SourceExe $TargetExe -Force
    Log "Copied executable to $InstallDir"
} catch {
    Write-Host "ERROR: Failed to copy executable: $_" -ForegroundColor Red
    exit 1
}

# Создать ярлык в автозагрузке
try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $TargetExe
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Save()
    Log "Shortcut created in Startup folder."
} catch {
    Write-Host "ERROR: Failed to create shortcut: $_" -ForegroundColor Red
    exit 1
}

# Запустить приложение в скрытом окне
try {
    Start-Process -FilePath $TargetExe `
                  -WorkingDirectory $InstallDir `
                  -WindowStyle Hidden `
                  -ErrorAction Stop
    Log "Started $AppName (hidden)."
    Write-Host "Started $AppName." -ForegroundColor Green
} catch {
    Write-Host "WARNING: Failed to start $AppName\: $_" -ForegroundColor Yellow
    Log "Failed to start $AppName\: $_"
}

Write-Host "Installation complete. The app will start automatically on next login." -ForegroundColor Green
Write-Host "Log file: $LogFile" -ForegroundColor Gray
Write-Host ""
Write-Host "To uninstall, run: powershell.exe -ExecutionPolicy Bypass -File install_windows.ps1 -Uninstall" -ForegroundColor Gray