<#
BAU laptop check (Windows). Collects everything needed to decide whether BAU can go on
this laptop, and changes nothing: no drivers, settings, disks or BitLocker are touched.
No Python needed.

Run it in PowerShell "as administrator" (BitLocker, Secure Boot and TPM need that):

    powershell -ExecutionPolicy Bypass -File .\bau-laptop-check.ps1

It writes two files in .\BAU-Laptop-Check (or -Out FOLDER):
  BAU-LAPTOP-SUMMARY.txt  short, safe to share: no computer name, user name, network
                          addresses or serial numbers. Send this one.
  BAU-LAPTOP-FULL.json    everything, including those private details. Keep it.

On the My Jarvis stick, bau-laptop-check.sh does the same from Linux and shows which
drivers really load.
#>
param([string]$Out = (Join-Path (Get-Location) "BAU-Laptop-Check"))

# PCI vendor ids -> name, and what Debian 13 on the stick does with them.
$BauVendors = @{
    "8086" = "Intel"; "8087" = "Intel"; "10EC" = "Realtek"; "168C" = "Qualcomm Atheros"
    "17CB" = "Qualcomm"; "14C3" = "MediaTek"; "14E4" = "Broadcom"; "10DE" = "NVIDIA"
    "1002" = "AMD"; "1022" = "AMD"; "1217" = "O2 Micro"
}

function Get-BauDeviceId([string]$InstanceId) {
    if ($InstanceId -match "(VEN_[0-9A-F]{4}&DEV_[0-9A-F]{4})") { return $Matches[1] }
    if ($InstanceId -match "(VID_[0-9A-F]{4}&PID_[0-9A-F]{4})") { return $Matches[1] }
    return ""
}

function Get-BauLinuxSupport([string]$Class, [string]$Vendor, [string]$Name = "") {
    switch ($Class) {
        "Net" {
            switch ($Vendor) {
                "Intel" { return "works (Intel drivers and firmware are on the stick)" }
                "Realtek" { return "works (Realtek firmware is on the stick)" }
                "Qualcomm Atheros" { return "works (Atheros firmware is on the stick)" }
                "Qualcomm" { return "works (Qualcomm/Atheros firmware is on the stick)" }
                "MediaTek" { return "works (MediaTek firmware is on the stick)" }
                "Broadcom" { return "check: some Broadcom Wi-Fi needs a driver the stick does not carry" }
            }
        }
        "Display" {
            switch ($Vendor) {
                "Intel" { return "works (Intel graphics)" }
                "AMD" { return "works (AMD graphics firmware is on the stick)" }
                "NVIDIA" { return "works with the open driver; if the screen stays black, choose 'safe graphics'" }
            }
        }
        "Bluetooth" {
            if ($Vendor -in @("Intel", "Realtek", "MediaTek") -or $Name -match "Intel|Qualcomm|Atheros|Realtek|MediaTek") {
                return "works (Bluetooth firmware is on the stick)"
            }
        }
        "Camera" { return "usually works (standard USB camera driver)" }
        "Image" { return "usually works (standard USB camera driver)" }
        "Biometric" { return "fingerprint readers often do not work on Linux; not needed by BAU" }
    }
    return "check on the stick: run bau-laptop-check.sh in limited mode"
}

function Get-BauSummary($inv) {
    $blockers = @(); $warnings = @(); $notes = @()
    $ramGb = [math]::Round([double]$inv.computer.TotalPhysicalMemory / 1GB)
    if (-not $inv.computer.TotalPhysicalMemory) {
        $notes += "Memory size could not be read: check it in Settings > System > About."
    } elseif ([double]$inv.computer.TotalPhysicalMemory / 1GB -lt 7.5) {
        $blockers += "Only $ramGb GB of memory: BAU needs 8 GB or more."
    }
    elseif ($ramGb -lt 12) {
        $notes += "$ramGb GB of memory is enough for BAU with Claude; local models: only the small ones (about 4B)."
    }
    if ($inv.os.OSArchitecture -and $inv.os.OSArchitecture -notmatch "64") {
        $blockers += "This is a 32-bit system: BAU needs a 64-bit PC."
    }
    $fw = if ("$($inv.firmware.Type)" -match "uefi") { "UEFI" } elseif ($inv.firmware.Type) { "legacy BIOS" } else { "unknown" }
    if ($fw -eq "legacy BIOS") {
        $warnings += "The PC starts in legacy BIOS mode. The stick still boots, but switching the firmware to UEFI before installing is better."
    }
    if ($inv.firmware.SecureBoot -eq $true) {
        $notes += "Secure Boot is on. If the stick does not start, turn Secure Boot off in the firmware settings."
    }
    $volumes = @(@($inv.bitlocker) | Where-Object { $_ })
    foreach ($v in $volumes) {
        if ("$($v.ProtectionStatus)" -match "On" -or ("$($v.VolumeStatus)" -and "$($v.VolumeStatus)" -notmatch "FullyDecrypted")) {
            $warnings += "BitLocker is ON for $($v.MountPoint). Before installing, write down the recovery key (aka.ms/myrecoverykey or Settings > Privacy & security > Device encryption) and back up your files: installing erases the disk you choose."
        }
    }
    if (-not $volumes.Count) {
        $notes += "BitLocker status unknown: run this check as administrator to see it."
    }
    if ($inv.fast_startup -eq $true) {
        $notes += "Windows Fast Startup is on: turn it off before installing (Control Panel > Power Options > Choose what the power buttons do), so Windows really shuts down."
    }
    $cpu = @($inv.cpu)[0]
    if ($cpu -and $cpu.VirtualizationFirmwareEnabled -eq $false) {
        $notes += "CPU virtualization is off in the firmware. BAU does not need it; virtual machines would."
    }

    $disks = @()
    foreach ($d in @($inv.disks)) {
        if (-not $d) { continue }
        $gb = [math]::Round([double]$d.Size / 1GB)
        $note = if ("$($d.BusType)" -eq "USB") { "USB stick or drive: not this one" } else { "" }
        $disks += [ordered]@{ name = "$($d.FriendlyName)"; bus = "$($d.BusType)"; type = "$($d.MediaType)"
                              size_gb = $gb; partition_style = "$($d.PartitionStyle)"; note = $note }
        if ("$($d.BusType)" -eq "RAID") {
            $warnings += "The internal disk ($($d.FriendlyName)) is behind Intel RST (firmware setting 'SATA Operation: RAID On'); the installer usually cannot see it. Switch that setting to AHCI before installing. If Windows must still start afterwards, set Windows to start in Safe Mode once before switching (docs/LAPTOP-CHECK.md has the steps)."
        }
    }
    $internal = @($disks | Where-Object { $_.bus -ne "USB" })
    if ($internal.Count -and -not @($internal | Where-Object { $_.size_gb -ge 64 }).Count) {
        $blockers += "No internal disk of 64 GB or more to install on."
    }

    $devices = @()
    foreach ($p in @($inv.pci)) {
        if (-not $p -or "$($p.Class)" -notin @("Net", "Display", "Media", "Bluetooth", "Camera", "Image", "Biometric")) { continue }
        $id = Get-BauDeviceId "$($p.InstanceId)"
        if (-not $id) { continue }      # VPN, WAN Miniport, Bluetooth profiles: software, not hardware
        $vendor = ""
        if ($id -match "(VEN|VID)_([0-9A-F]{4})") { $vendor = $BauVendors[$Matches[2]] }
        $linux = Get-BauLinuxSupport "$($p.Class)" "$vendor" "$($p.FriendlyName)"
        if ($linux -like "check: some Broadcom*") {
            $warnings += "Broadcom Wi-Fi ($($p.FriendlyName)): it may not work from the stick. Have a USB Wi-Fi adapter or an Ethernet cable ready for the install."
        }
        if ($vendor -eq "NVIDIA" -and "$($p.Class)" -eq "Display") {
            $notes += "NVIDIA graphics: if the screen stays black at start, choose 'safe graphics' in the stick's menu."
        }
        $devices += [ordered]@{ class = "$($p.Class)"; name = "$($p.FriendlyName)"; vendor = "$vendor"
                                id = $id; linux = $linux }
    }
    $problems = @(@($inv.problem_devices) | Where-Object { $_ })
    if ($problems.Count) {
        $names = ($problems | ForEach-Object { "$($_.Name) [$(Get-BauDeviceId "$($_.InstanceId)")]" }) -join "; "
        $notes += "$($problems.Count) device(s) report a problem in Windows too: $names"
    }
    $health = $null
    $bat = @($inv.battery)[0]
    if ($bat -and $bat.DesignCapacity) {
        $health = [math]::Round(100 * [double]$bat.FullChargeCapacity / [double]$bat.DesignCapacity)
    }

    $verdict = if ($blockers.Count) { "NOT READY" } elseif ($warnings.Count) { "READY, AFTER THESE STEPS" } else { "READY" }
    return [ordered]@{
        verdict = $verdict; blockers = @($blockers); warnings = @($warnings); notes = @($notes)
        model = "$($inv.computer.Manufacturer) $($inv.computer.Model)".Trim()
        windows = "$($inv.os.Caption) $($inv.os.OSArchitecture)".Trim()
        cpu = "$($cpu.Name)"; cores = $cpu.NumberOfCores; threads = $cpu.NumberOfLogicalProcessors
        ram_gb = $ramGb; firmware = $fw; secure_boot = $inv.firmware.SecureBoot
        tpm = if ($inv.tpm.TpmPresent) { "present $($inv.tpm.SpecVersion)".Trim() } else { "not found" }
        disks = @($disks); devices = @($devices); battery_health_percent = $health
    }
}

function ConvertTo-BauText($s) {
    $l = @("BAU LAPTOP CHECK - safe to share (no names, network addresses or serial numbers)",
           "", "VERDICT: $($s.verdict)", "")
    foreach ($x in $s.blockers) { $l += "  BLOCKER: $x" }
    foreach ($x in $s.warnings) { $l += "  DO FIRST: $x" }
    foreach ($x in $s.notes) { $l += "  NOTE: $x" }
    $l += "", "Laptop:   $($s.model)", "Windows:  $($s.windows)",
          "CPU:      $($s.cpu) ($($s.cores) cores, $($s.threads) threads)",
          "Memory:   $($s.ram_gb) GB", "Firmware: $($s.firmware), Secure Boot $($s.secure_boot), TPM $($s.tpm)"
    if ($null -ne $s.battery_health_percent) { $l += "Battery:  $($s.battery_health_percent)% of its original capacity" }
    $l += "", "Disks:"
    foreach ($d in $s.disks) {
        $extra = if ($d.note) { " ($($d.note))" } else { "" }
        $l += "  $($d.name): $($d.size_gb) GB $($d.type) on $($d.bus), $($d.partition_style)$extra"
    }
    $l += "", "Devices and Linux:"
    foreach ($d in $s.devices) { $l += "  [$($d.class)] $($d.name) $($d.id): $($d.linux)" }
    return ($l -join [Environment]::NewLine)
}

function Get-BauInventory {
    # Anything this PC cannot answer (no BitLocker, no battery, not admin) becomes empty,
    # quietly: no red error text in the owner's window.
    function Invoke-BauSafe($block) {
        $ErrorActionPreference = "Stop"
        try { & $block 2>$null } catch { $null }
    }
    $inv = [ordered]@{ collected_at = (Get-Date).ToUniversalTime().ToString("o"); read_only = $true }
    $inv.os = Invoke-BauSafe { Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture, CSName }
    $inv.user = $env:USERNAME
    $inv.computer = Invoke-BauSafe {
        $cs = Get-CimInstance Win32_ComputerSystem
        [ordered]@{ Manufacturer = $cs.Manufacturer; Model = $cs.Model; SystemFamily = $cs.SystemFamily
                    TotalPhysicalMemory = $cs.TotalPhysicalMemory
                    SerialNumber = (Get-CimInstance Win32_BIOS).SerialNumber }
    }
    $inv.bios = Invoke-BauSafe { Get-CimInstance Win32_BIOS | Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate }
    $inv.cpu = @(Invoke-BauSafe { Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, VirtualizationFirmwareEnabled, SecondLevelAddressTranslationExtensions })
    $inv.memory_modules = @(Invoke-BauSafe { Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, Speed, Manufacturer, PartNumber })
    $inv.firmware = [ordered]@{ Type = $env:firmware_type; SecureBoot = (Invoke-BauSafe { Confirm-SecureBootUEFI }) }
    $inv.tpm = Invoke-BauSafe {
        $t = Get-CimInstance -Namespace root\cimv2\Security\MicrosoftTpm -ClassName Win32_Tpm
        [ordered]@{ TpmPresent = [bool]$t; SpecVersion = ("$($t.SpecVersion)" -split ",")[0] }
    }
    $inv.bitlocker = @(Invoke-BauSafe { Get-BitLockerVolume | ForEach-Object {
        [ordered]@{ MountPoint = $_.MountPoint; ProtectionStatus = "$($_.ProtectionStatus)"; VolumeStatus = "$($_.VolumeStatus)" } } })
    $inv.disks = @(Invoke-BauSafe { Get-PhysicalDisk | ForEach-Object {
        $n = $_.DeviceId
        $style = Invoke-BauSafe { (Get-Disk -Number $n).PartitionStyle }
        [ordered]@{ FriendlyName = $_.FriendlyName; BusType = "$($_.BusType)"; MediaType = "$($_.MediaType)"
                    Size = $_.Size; SerialNumber = $_.SerialNumber; PartitionStyle = "$style" } } })
    $inv.volumes = @(Invoke-BauSafe { Get-Volume | Select-Object DriveLetter, FileSystemLabel, FileSystem, Size, SizeRemaining })
    $inv.pci = @(Invoke-BauSafe { Get-PnpDevice -PresentOnly | Where-Object {
            $_.InstanceId -like "PCI\*" -or $_.Class -in @("Net", "Bluetooth", "Camera", "Image", "Biometric") } |
        Select-Object Class, FriendlyName, Manufacturer, Status, InstanceId })
    $inv.network = @(Invoke-BauSafe { Get-NetAdapter -IncludeHidden:$false | Select-Object Name, InterfaceDescription, MacAddress, Status, LinkSpeed })
    $inv.problem_devices = @(Invoke-BauSafe { Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 } |
        ForEach-Object { [ordered]@{ Name = $_.Name; InstanceId = $_.PNPDeviceID; ErrorCode = $_.ConfigManagerErrorCode } } })
    $inv.fast_startup = Invoke-BauSafe { (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power").HiberbootEnabled -eq 1 }
    $inv.battery = @(Invoke-BauSafe {
        $design = Get-CimInstance -Namespace root\wmi -ClassName BatteryStaticData
        $full = Get-CimInstance -Namespace root\wmi -ClassName BatteryFullChargedCapacity
        [ordered]@{ DesignCapacity = $design.DesignedCapacity; FullChargeCapacity = $full.FullChargedCapacity } })
    return $inv
}

if ($MyInvocation.InvocationName -ne ".") {
    $admin = try {
        ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch { $false }
    if (-not $admin) {
        Write-Host "Note: not running as administrator - BitLocker, Secure Boot and TPM may show as unknown." -ForegroundColor Yellow
    }
    Write-Host "Checking this laptop (read only, about a minute)..."
    New-Item -ItemType Directory -Force -Path $Out | Out-Null
    # Round-trip through JSON so the summary sees exactly what the full report holds.
    $json = Get-BauInventory | ConvertTo-Json -Depth 6
    $full = Join-Path $Out "BAU-LAPTOP-FULL.json"
    $sum = Join-Path $Out "BAU-LAPTOP-SUMMARY.txt"
    $json | Set-Content -Encoding UTF8 $full
    $text = ConvertTo-BauText (Get-BauSummary ($json | ConvertFrom-Json))
    $text | Set-Content -Encoding UTF8 $sum
    Write-Host ""
    Write-Host $text
    Write-Host ""
    Write-Host "Share this one:   $sum" -ForegroundColor Green
    Write-Host "Keep this private: $full"
}
