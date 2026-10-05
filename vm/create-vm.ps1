<#
Build a VirtualBox "test laptop" with both BAU sticks plugged in, so the whole two-stick
install can be rehearsed on this Windows computer before touching the real laptop.

  powershell -ExecutionPolicy Bypass -File vm\create-vm.ps1 [-Usb1 FILE.iso] [-Payload FILE.iso]
                                                     [-Name BAU-Test] [-MemoryMB 8192] [-Cpus 4] [-DiskGB 60]

Without -Usb1/-Payload it looks for bau-debian-*.iso and BAU-PAYLOAD-*.iso (from the GitHub
release) in the current folder and your Downloads folder, and checks them against
SHA256SUMS.txt when that file sits next to them. Needs VirtualBox 7 (virtualbox.org) and
virtualisation switched on in the BIOS.
#>
param(
  [string]$Usb1 = "",
  [string]$Payload = "",
  [string]$Name = "BAU-Test",
  [int]$MemoryMB = 8192,
  [int]$Cpus = 4,
  [int]$DiskGB = 60
)
$ErrorActionPreference = "Stop"

function Die($msg) { Write-Host "create-vm: $msg" -ForegroundColor Red; exit 1 }

$vbox = (Get-Command VBoxManage -ErrorAction SilentlyContinue).Source
if (-not $vbox) {
  $guess = Join-Path $env:ProgramFiles "Oracle\VirtualBox\VBoxManage.exe"
  if (Test-Path $guess) { $vbox = $guess } else { Die "VirtualBox not found - install it from virtualbox.org" }
}
function VBox { & $vbox @args; if ($LASTEXITCODE -ne 0) { Die "VBoxManage $($args -join ' ') failed" } }

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

# Windows PowerShell 5.1 turns a native command's error output into a terminating error
# under "Stop", so this probe runs with "Continue".
$ErrorActionPreference = "Continue"
$exists = (& $vbox list vms) -match ('^"' + [regex]::Escape($Name) + '" ')
$ErrorActionPreference = "Stop"
if ($exists) { Die "a VM called $Name already exists (delete it in VirtualBox or use -Name)" }
$base = ((& $vbox list systemproperties) | Select-String "^Default machine folder:").Line -replace "^Default machine folder:\s*", ""
$disk = Join-Path (Join-Path $base $Name) "$Name.vdi"

VBox createvm --name $Name --ostype Debian_64 --register
VBox modifyvm $Name --memory $MemoryMB --cpus $Cpus --firmware efi64 --graphicscontroller vmsvga `
  --vram 128 --nic1 nat --boot1 dvd --boot2 disk --boot3 none --boot4 none
VBox createmedium disk --filename $disk --size ($DiskGB * 1024) --format VDI
VBox storagectl $Name --name SATA --add sata --controller IntelAhci --portcount 3
VBox storageattach $Name --storagectl SATA --port 0 --device 0 --type hdd --medium $disk
VBox storageattach $Name --storagectl SATA --port 1 --device 0 --type dvddrive --medium $Usb1
VBox storageattach $Name --storagectl SATA --port 2 --device 0 --type dvddrive --medium $Payload

Write-Host ""
Write-Host "VM `"$Name`" is ready: $MemoryMB MB RAM, $Cpus CPUs, $DiskGB GB disk, USB #1 and USB #2 inserted." -ForegroundColor Green
Write-Host "Start it: double-click $Name in VirtualBox (or: VBoxManage startvm $Name --type gui)"
Write-Host "Then follow vm\README.md: install from USB #1, log in, and run USB #2's install.sh."
