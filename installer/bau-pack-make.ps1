<#
BAU Pack maker (Windows). Run it on a computer with internet: it fills a USB stick you pick
with the BAU laptop's local AI models, each checked against its pinned SHA-256, and your
locked keys file (BAU-KEYS.enc) if it sits next to this script. It never formats or erases
anything; it only writes into a BAU-PACK folder on the stick. No Python needed.

Easiest: double-click BAU-Pack-Make.cmd, or:

    powershell -ExecutionPolicy Bypass -File .\bau-pack-make.ps1

Then plug the stick into the BAU laptop and run: sudo bau pack install
docs/PACK.md explains every step.
#>
param(
    [string]$Target = "",
    [string]$Manifest = "",
    [switch]$Yes
)

# The same files, links and hashes as src/bau/data/registry_defaults.yaml (a test checks).
$BauModels = @(
    @{ Id = "qwen3.5-9b"; File = "Qwen3.5-9B-Q4_K_M.gguf"; Url = "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf"; Size = 5680522464; Sha256 = "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8"; Role = "the desktop boss: runs on the NVIDIA card (docs/DESKTOP.md)" },
    @{ Id = "qwen3.5-4b"; File = "Qwen3.5-4B-Q4_K_M.gguf"; Url = "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf"; Size = 2740937888; Sha256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"; Role = "the boss: runs Jarvis and the agents" },
    @{ Id = "qwen3-4b-heretic-content"; File = "Qwen3-4B-Instruct-2507-heretic.Q4_K_M.gguf"; Url = "https://huggingface.co/mradermacher/Qwen3-4B-Instruct-2507-heretic-GGUF/resolve/main/Qwen3-4B-Instruct-2507-heretic.Q4_K_M.gguf"; Size = 2497279584; Sha256 = "5d38e532cf33a5b56760bc7803aaabffb240d0604f1e389e4db148830c2bb747"; Role = "the thinker: uncensored ideas, sealed" },
    @{ Id = "qwen2.5-1.5b-instruct"; File = "qwen2.5-1.5b-instruct-q4_k_m.gguf"; Url = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"; Size = 1117320736; Sha256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"; Role = "the backup: small and fast" }
)

# The Wi-Fi programs the first stick image left out (the laptop needs them to join any
# Wi-Fi network). Debian trixie amd64; same list as src/bau/pack.py (a test checks).
$BauDebs = @(
    @{ Name = "iw"; File = "iw_6.9-1_amd64.deb"; Pool = "pool/main/i/iw/iw_6.9-1_amd64.deb"; Size = 106300; Sha256 = "61c0848fe4c98718f1f1ad7526ae4858d91f85e3139f0e723bed4bc2aa729422" },
    @{ Name = "libnl-3-200"; File = "libnl-3-200_3.7.0-2_amd64.deb"; Pool = "pool/main/libn/libnl3/libnl-3-200_3.7.0-2_amd64.deb"; Size = 59432; Sha256 = "ce5c153953016be42def7b105f37d55eae07a9608d1dfe6bcb03cc017fc384cb" },
    @{ Name = "libnl-genl-3-200"; File = "libnl-genl-3-200_3.7.0-2_amd64.deb"; Pool = "pool/main/libn/libnl3/libnl-genl-3-200_3.7.0-2_amd64.deb"; Size = 18136; Sha256 = "8f2f81ef4c6f8636f0b0cb2ff40b3c54a497d121f49c485620ae43c94782cd94" },
    @{ Name = "libnl-route-3-200"; File = "libnl-route-3-200_3.7.0-2_amd64.deb"; Pool = "pool/main/libn/libnl3/libnl-route-3-200_3.7.0-2_amd64.deb"; Size = 181704; Sha256 = "1c8c95542688996cff8e954583642b10a3bd78b69954f565fda62144c2bc3897" },
    @{ Name = "libpcsclite1"; File = "libpcsclite1_2.3.3-1_amd64.deb"; Pool = "pool/main/p/pcsc-lite/libpcsclite1_2.3.3-1_amd64.deb"; Size = 55248; Sha256 = "a8bc4725549060d1e696d358e32a3699d947d5381871553a290389830bebccbd" },
    @{ Name = "wireless-regdb"; File = "wireless-regdb_2026.05.30-1~deb13u1_all.deb"; Pool = "pool/main/w/wireless-regdb/wireless-regdb_2026.05.30-1~deb13u1_all.deb"; Size = 12400; Sha256 = "72048ee2f369a8c2df8b5f99f79489d3812d869282038cfe55e23a4748231399" },
    @{ Name = "wpasupplicant"; File = "wpasupplicant_2.10-24_amd64.deb"; Pool = "pool/main/w/wpa/wpasupplicant_2.10-24_amd64.deb"; Size = 1426452; Sha256 = "99f50410baddebd421497703ad9b6d0e05deb3dfda99a96b2814f630d9b84498" }
)
$BauDebMirrors = @("https://deb.debian.org/debian/", "https://snapshot.debian.org/archive/debian/20261018T000000Z/")
# The latest BAU, so a laptop installed from an older stick gets `bau pack` too.
$BauZip = "https://github.com/BSAJabo258/linux-ai-biz/archive/refs/heads/main.zip"

function Get-BauSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
}

function Select-BauStick {
    # Bigger USB sticks and USB SSDs often call themselves "Fixed": also take any drive
    # on a USB disk. Never the Windows drive (that is not on USB).
    $usb = @(Get-Disk -ErrorAction SilentlyContinue | Where-Object { $_.BusType -eq "USB" } |
        Get-Partition -ErrorAction SilentlyContinue | Where-Object { $_.DriveLetter } |
        ForEach-Object { "$($_.DriveLetter):\" })
    $drives = @([IO.DriveInfo]::GetDrives() | Where-Object {
        $_.IsReady -and ($_.DriveType -eq "Removable" -or $usb -contains $_.Name) })
    if (-not $drives.Count) {
        Write-Host "No USB stick found. Plug one in (8 GB or more) and run this again." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "USB sticks on this computer:"
    foreach ($d in $drives) {
        $gb = [math]::Round($d.TotalSize / 1GB, 1)
        $free = [math]::Round($d.AvailableFreeSpace / 1GB, 1)
        Write-Host ("  {0}  {1}  {2} GB, {3} GB free" -f $d.Name.Substring(0, 2), $d.VolumeLabel, $gb, $free)
    }
    $letter = (Read-Host "Type the letter of the stick to fill (for example E)").Trim().TrimEnd(":", "\").ToUpper()
    foreach ($d in $drives) {
        if ($d.Name.Substring(0, 1).ToUpper() -eq $letter -and $letter.Length -eq 1) { return $d.Name }
    }
    Write-Host "$letter is not one of the USB sticks above. Nothing written." -ForegroundColor Yellow
    exit 1
}

function Get-BauCurl {
    # The real curl program, never PowerShell's "curl" alias for Invoke-WebRequest.
    $c = Get-Command curl.exe -CommandType Application -ErrorAction SilentlyContinue
    if (-not $c) { $c = Get-Command curl -CommandType Application -ErrorAction SilentlyContinue }
    if (-not $c) {
        Write-Host "curl.exe was not found (Windows 10 and 11 include it)." -ForegroundColor Yellow
        exit 1
    }
    return @($c)[0].Source
}

function Get-BauFile([string]$Curl, [string[]]$Urls, [string]$Final, [string]$Sha256, [string]$Label) {
    # Returns $true when $Final is in place and matches its pinned SHA-256.
    if (Test-Path -LiteralPath $Final) {
        if ((Get-BauSha256 $Final) -eq $Sha256) { Write-Host "${Label}: already on the stick, checked."; return $true }
        Remove-Item -LiteralPath $Final
    }
    $part = "$Final.part"
    foreach ($url in $Urls) {
        Write-Host "${Label}: downloading..."
        & $Curl -L --fail --retry 3 -C - -o $part $url
        if ($LASTEXITCODE -ne 0) { continue }
        if ((Get-BauSha256 $part) -ne $Sha256) {
            Remove-Item -LiteralPath $part
            Write-Host "${Label}: the file does not match its pinned SHA-256, so it was deleted." -ForegroundColor Red
            return $false
        }
        Move-Item -LiteralPath $part -Destination $Final -Force
        Write-Host "${Label}: downloaded and checked." -ForegroundColor Green
        return $true
    }
    Write-Host "${Label}: download stopped. Run this again to carry on." -ForegroundColor Yellow
    return $false
}

function Write-BauReadme([string]$Pack) {
    $text = @"
BAU PACK
========
This folder holds the BAU laptop's local AI models (models\) and, if you made one,
your locked keys file (BAU-KEYS.enc). Every model was checked against its pinned
SHA-256 when it was downloaded, and is checked again on the laptop.

On the BAU laptop, plug in this stick and open it once in the file manager.

If the laptop has no Wi-Fi (laptops installed from a stick made before 18 October
2026), first open a terminal and type these four lines:
  cd /media/`$USER/*/BAU-PACK/wifi
  sha256sum -c SHA256SUMS
  sudo apt install ./*.deb
  sudo systemctl restart NetworkManager
Then pick your Wi-Fi from the network icon. Once it is connected, bring BAU up to date:
  sudo /opt/bau/venv/bin/pip install --no-deps --upgrade /media/`$USER/*/BAU-PACK/bau-main.zip

Then, in the terminal:
  sudo bau pack install
Answer yes or no to each question. Nothing changes without your yes. At the end it
writes laptop-report.txt onto this stick (the laptop's network card and firmware,
with addresses and Wi-Fi names hidden).

Nothing on this stick runs by itself when you plug it in.
"@
    [IO.File]::WriteAllText((Join-Path $Pack "README.txt"), $text.Replace("`r`n", "`n"))
}

if ($MyInvocation.InvocationName -ne ".") {
    $models = $BauModels
    $debs = @()
    foreach ($d in $BauDebs) {
        $urls = @(); foreach ($mirror in $BauDebMirrors) { $urls += ($mirror + $d.Pool) }
        $debs += @{ Name = $d.Name; File = $d.File; Size = $d.Size; Sha256 = $d.Sha256; Urls = $urls }
    }
    $zip = $BauZip
    if ($Manifest) {
        # Tests: the same lists with local links.
        $j = ConvertFrom-Json (Get-Content -Raw -LiteralPath $Manifest)
        $models = @(); foreach ($m in $j.Models) { $models += $m }
        $debs = @(); foreach ($d in $j.Debs) { $debs += $d }
        $zip = $j.BauZip
    }
    if (-not $Target) { $Target = Select-BauStick }
    $pack = Join-Path $Target "BAU-PACK"
    $dir = Join-Path $pack "models"

    try {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $probe = Join-Path $pack ".bau-write-test"
        [IO.File]::WriteAllText($probe, "ok")
        Remove-Item -LiteralPath $probe
    } catch {
        Write-Host "Cannot write to $Target. If it still holds a BAU installer image, format it" -ForegroundColor Yellow
        Write-Host "first in File Explorer (right-click the drive, Format, exFAT) - that erases it."
        exit 1
    }

    $need = [long]50MB
    foreach ($m in $models) {
        $f = Join-Path $dir $m.File
        if (-not (Test-Path -LiteralPath $f)) { $need += [long]$m.Size }
    }
    try {
        $free = (New-Object IO.DriveInfo ([IO.Path]::GetPathRoot((Resolve-Path $Target).Path))).AvailableFreeSpace
        if ($free -lt $need) {
            Write-Host ("Not enough space: {0:N1} GB needed, {1:N1} GB free." -f ($need / 1GB), ($free / 1GB)) -ForegroundColor Yellow
            exit 1
        }
    } catch { }

    Write-Host "This fills $pack with:"
    foreach ($m in $models) { Write-Host ("  {0}  ({1:N1} GB) {2}" -f $m.Id, ($m.Size / 1GB), $m.Role) }
    if (-not $Yes) {
        $ok = Read-Host "Go ahead? [y/N]"
        if ($ok -notmatch '^[yY]') { Write-Host "Nothing downloaded."; exit 0 }
    }

    $curl = Get-BauCurl
    $failed = 0
    foreach ($m in $models) {
        if (-not (Get-BauFile $curl @($m.Url) (Join-Path $dir $m.File) $m.Sha256 $m.Id)) { $failed++ }
    }

    $wifi = Join-Path $pack "wifi"
    New-Item -ItemType Directory -Force -Path $wifi | Out-Null
    $sums = @()
    foreach ($d in $debs) {
        if (Get-BauFile $curl @($d.Urls) (Join-Path $wifi $d.File) $d.Sha256 $d.Name) {
            $sums += "$($d.Sha256)  $($d.File)"
        } else { $failed++ }
    }
    [IO.File]::WriteAllText((Join-Path $wifi "SHA256SUMS"), (($sums -join "`n") + "`n"))

    # Not pinned (it changes with every update): it comes from your own GitHub repository.
    $zipFile = Join-Path $pack "bau-main.zip"
    Write-Host "BAU (latest): downloading..."
    & $curl -L --fail --retry 3 -o "$zipFile.part" $zip
    if ($LASTEXITCODE -eq 0) {
        Move-Item -LiteralPath "$zipFile.part" -Destination $zipFile -Force
    } else {
        if (Test-Path -LiteralPath "$zipFile.part") { Remove-Item -LiteralPath "$zipFile.part" }
        Write-Host "BAU (latest): download stopped. Run this again." -ForegroundColor Yellow
        $failed++
    }

    $keys = Join-Path $PSScriptRoot "BAU-KEYS.enc"
    if (Test-Path -LiteralPath $keys) {
        Copy-Item -LiteralPath $keys -Destination (Join-Path $pack "BAU-KEYS.enc") -Force
        Write-Host "BAU-KEYS.enc: copied (it stays locked with your passphrase)."
    }
    Write-BauReadme $pack

    Write-Host ""
    if ($failed) {
        Write-Host "$failed file(s) are not on the stick yet. Run this again." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "The BAU Pack is ready." -ForegroundColor Green
    Write-Host "On the laptop: plug it in, open it once in the file manager, then: sudo bau pack install"
    exit 0
}
