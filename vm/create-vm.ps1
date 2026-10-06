<#
Build a VirtualBox "test laptop" with both BAU sticks plugged in, so the whole two-stick
install can be rehearsed on this Windows computer before touching the real laptop.

  powershell -ExecutionPolicy Bypass -File vm\create-vm.ps1 [-Usb1 FILE.iso] [-Payload FILE.iso]
                                                     [-Name BAU-Test] [-MemoryMB N] [-Cpus N] [-DiskGB 60]

If the VM already exists, it is resized instead: safe memory and CPUs for this PC, disk first
in the boot order. Its disk and anything installed on it are kept.

Without -Usb1/-Payload it looks for bau-debian-*.iso and BAU-PAYLOAD-*.iso (from the GitHub
release) in the current folder and your Downloads folder, and checks them against
SHA256SUMS.txt when that file sits next to them. Needs VirtualBox 7 (virtualbox.org) and
virtualisation switched on in the BIOS.
#>
param(
  [string]$Usb1 = "",
  [string]$Payload = "",
  [string]$Name = "BAU-Test",
  [int]$MemoryMB = 0,      # 0 = half of this computer's RAM, 4-8 GB
  [int]$Cpus = 0,          # 0 = half of this computer's cores, at most 4
  [int]$DiskGB = 60
)
$ErrorActionPreference = "Stop"

function Die($msg) { Write-Host "create-vm: $msg" -ForegroundColor Red; exit 1 }

# Size the VM from this computer so Windows keeps enough memory: a VM that takes too
# much RAM makes the whole PC swap and freeze.
$hostMB = [int]((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1MB)
# At most 60% of RAM and at least 4 GB left for Windows (8 GB on a 12 GB PC froze it).
$maxMB = [Math]::Max(2048, [int]([Math]::Floor([Math]::Min($hostMB * 0.6, $hostMB - 4096) / 1024) * 1024))
if ($MemoryMB -le 0) { $MemoryMB = [Math]::Max(2048, [Math]::Min([Math]::Min(8192, $maxMB), [int]([Math]::Floor($hostMB / 2048) * 1024))) }
if ($Cpus -le 0) { $Cpus = [Math]::Max(1, [Math]::Min(4, [int][Math]::Floor([Environment]::ProcessorCount / 2))) }
if ($MemoryMB -gt $maxMB) {
  Die "$MemoryMB MB for the VM is too much for this PC's $hostMB MB (Windows would freeze) - use -MemoryMB $maxMB or less"
}

$vbox = (Get-Command VBoxManage -ErrorAction SilentlyContinue).Source
if (-not $vbox) {
  $guess = Join-Path $env:ProgramFiles "Oracle\VirtualBox\VBoxManage.exe"
  if (Test-Path $guess) { $vbox = $guess } else { Die "VirtualBox not found - install it from virtualbox.org" }
}
function VBox { & $vbox @args; if ($LASTEXITCODE -ne 0) { Die "VBoxManage $($args -join ' ') failed" } }
# Windows PowerShell 5.1 turns a native command's error output into a terminating error
# under "Stop", so probes and retries run with "Continue".
function VBoxTry { $ErrorActionPreference = "Continue"; & $vbox @args | Out-Host; return $LASTEXITCODE }
function Ask($question) { return (Read-Host "$question (y/N)") -match '^(y|yes)$' }

$ErrorActionPreference = "Continue"
$exists = (& $vbox list vms) -match ('^"' + [regex]::Escape($Name) + '" ')
$ErrorActionPreference = "Stop"
if ($exists) {
  # Fix the existing VM instead of building a new one; its disk is left alone.
  $ErrorActionPreference = "Continue"
  $state = [string](& $vbox showvminfo $Name --machinereadable | Select-String '^VMState=').Line -replace '^VMState="?([^"]*)"?$', '$1'
  $ErrorActionPreference = "Stop"
  if ($state -in @("running", "paused", "stuck")) {
    if (-not (Ask "$Name is running. Power it off now to fix its memory? Unsaved work inside it is lost")) {
      Die "left $Name as it is - shut it down, then run this again"
    }
    if ((VBoxTry controlvm $Name poweroff) -ne 0) { Die "could not power off $Name - close its window, choose Power off, then run this again" }
  } elseif ($state -eq "saved") {
    if (-not (Ask "$Name was saved while running. Discard that saved moment so its memory can be fixed? (like pulling the plug)")) {
      Die "left $Name as it is - start it, shut it down from inside, then run this again"
    }
    VBox discardstate $Name
  }
  # Right after a power-off VirtualBox keeps the VM locked for a few seconds.
  for ($i = 0; $i -lt 15; $i++) {
    if ((VBoxTry modifyvm $Name --memory $MemoryMB --cpus $Cpus --boot1 disk --boot2 dvd --boot3 none --boot4 none) -eq 0) { break }
    Start-Sleep -Seconds 2
  }
  if ($i -eq 15) { Die "could not change $Name - close VirtualBox completely, then run this again" }
  Write-Host ""
  Write-Host "VM `"$Name`" fixed: $MemoryMB MB RAM, $Cpus CPUs (safe for this PC's $hostMB MB). Its disk and everything installed are kept." -ForegroundColor Green
  Write-Host "Start it: double-click $Name in VirtualBox (or: VBoxManage startvm $Name --type gui)"
  exit 0
}

function Find-One($pattern) {
  $places = @((Get-Location).Path, (Join-Path $env:USERPROFILE "Downloads"))
  $hit = Get-ChildItem -Path $places -Filter $pattern -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $hit) { Die "no $pattern found here or in Downloads - download it from the GitHub release" }
  return $hit.FullName
}
if (-not $Usb1) { $Usb1 = Find-One "bau-debian-*.iso" }
if (-not $Payload) { $Payload = Find-One "BAU-PAYLOAD-*.iso" }
foreach ($img in @($Usb1, $Payload)) { if (-not (Test-Path $img)) { Die "image not found: $img" } }

foreach ($img in @($Usb1, $Payload)) {
  $sums = Join-Path (Split-Path $img) "SHA256SUMS.txt"
  $file = Split-Path $img -Leaf
  if (Test-Path $sums) {
    $line = Select-String -Path $sums -Pattern ([regex]::Escape(" $file") + '$') | Select-Object -First 1
    if (-not $line) { Die "$file is not listed in $sums" }
    $want = ($line.Line -split '\s+')[0].ToLower()
    $got = (Get-FileHash -Algorithm SHA256 -Path $img).Hash.ToLower()
    if ($got -ne $want) { Die "checksum mismatch for $file - download it again" }
    Write-Host "verified $file"
  } else {
    Write-Host "WARNING: no SHA256SUMS.txt next to $file; checksum not verified" -ForegroundColor Yellow
  }
}

$base = ((& $vbox list systemproperties) | Select-String "^Default machine folder:").Line -replace "^Default machine folder:\s*", ""
$disk = Join-Path (Join-Path $base $Name) "$Name.vdi"

VBox createvm --name $Name --ostype Debian_64 --register
VBox modifyvm $Name --memory $MemoryMB --cpus $Cpus --firmware efi64 --graphicscontroller vmsvga `
  --vram 128 --nic1 nat --boot1 disk --boot2 dvd --boot3 none --boot4 none
VBox createmedium disk --filename $disk --size ($DiskGB * 1024) --format VDI
VBox storagectl $Name --name SATA --add sata --controller IntelAhci --portcount 3
VBox storageattach $Name --storagectl SATA --port 0 --device 0 --type hdd --medium $disk
VBox storageattach $Name --storagectl SATA --port 1 --device 0 --type dvddrive --medium $Usb1
VBox storageattach $Name --storagectl SATA --port 2 --device 0 --type dvddrive --medium $Payload

Write-Host ""
Write-Host "VM `"$Name`" is ready: $MemoryMB MB RAM, $Cpus CPUs, $DiskGB GB disk, USB #1 and USB #2 inserted." -ForegroundColor Green
Write-Host "Start it: double-click $Name in VirtualBox (or: VBoxManage startvm $Name --type gui)"
Write-Host "Then follow vm\README.md: install from USB #1, log in, and run USB #2's install.sh."
