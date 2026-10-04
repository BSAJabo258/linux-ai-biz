# Phase 1: READ-ONLY hardware audit when the laptop currently runs Windows (spec §4).
# Run in an elevated PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\hw-audit-windows.ps1 -Out E:\bau-baselines
# Writes the same BAU-*-BASELINE.json names as hw-audit.sh. Changes nothing else.
# Note: `bau wipe-gate` needs a Linux disk baseline (lsblk). Before wiping, boot a
# Debian live session and run hw-audit.sh too; this file documents the Windows state.
param([Parameter(Mandatory = $true)][string]$Out)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$now = (Get-Date).ToUniversalTime().ToString("o")

function Save($name, $obj) {
    $obj | Add-Member -NotePropertyName captured_at -NotePropertyValue $now -Force
    $obj | Add-Member -NotePropertyName read_only -NotePropertyValue $true -Force
    $obj | Add-Member -NotePropertyName source_os -NotePropertyValue "windows" -Force
    $obj | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $Out "$name.json")
}

$cs  = Get-CimInstance Win32_ComputerSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, VirtualizationFirmwareEnabled
$gpu = Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion
$bios = Get-CimInstance Win32_BIOS | Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate
$tpm = try { Get-Tpm | Select-Object TpmPresent, TpmReady, ManufacturerVersion } catch { $null }
$sb  = try { Confirm-SecureBootUEFI } catch { $null }
$bat = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object Name, EstimatedChargeRemaining, BatteryStatus

Save "BAU-HARDWARE-BASELINE" ([pscustomobject]@{
    cpu = $cpu; memory = @{ total_gib = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1) }
    gpus = $gpu; firmware = @{ bios = $bios; secure_boot = $sb; tpm = $tpm; vendor = $cs.Manufacturer; product = $cs.Model }
    batteries = $bat
    cameras = (Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -in @("Camera", "Image") } | Select-Object -ExpandProperty Name)
})
Save "BAU-DISK-BASELINE" ([pscustomobject]@{
    physical_disks = (Get-PhysicalDisk | Select-Object FriendlyName, SerialNumber, MediaType, BusType, Size, HealthStatus)
    volumes = (Get-Volume | Select-Object DriveLetter, FileSystemLabel, FileSystem, Size, SizeRemaining)
    bitlocker = (try { Get-BitLockerVolume | Select-Object MountPoint, ProtectionStatus, VolumeStatus } catch { "unavailable" })
})
Save "BAU-SYSTEM-BASELINE" ([pscustomobject]@{
    os = (Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber)
})
Save "BAU-NETWORK-BASELINE" ([pscustomobject]@{
    adapters = (Get-NetAdapter | Select-Object Name, InterfaceDescription, Status, LinkSpeed)
})
Write-Host "Baselines written to $Out. If BitLocker is on, record the recovery key OFFLINE before wiping."
