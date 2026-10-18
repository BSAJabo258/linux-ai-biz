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
    @{ Id = "qwen3.5-4b"; File = "Qwen3.5-4B-Q4_K_M.gguf"; Url = "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf"; Size = 2740937888; Sha256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"; Role = "the boss: runs Jarvis and the agents" },
    @{ Id = "qwen3-4b-heretic-content"; File = "Qwen3-4B-Instruct-2507-heretic.Q4_K_M.gguf"; Url = "https://huggingface.co/mradermacher/Qwen3-4B-Instruct-2507-heretic-GGUF/resolve/main/Qwen3-4B-Instruct-2507-heretic.Q4_K_M.gguf"; Size = 2497279584; Sha256 = "5d38e532cf33a5b56760bc7803aaabffb240d0604f1e389e4db148830c2bb747"; Role = "the thinker: uncensored ideas, sealed" },
    @{ Id = "qwen2.5-1.5b-instruct"; File = "qwen2.5-1.5b-instruct-q4_k_m.gguf"; Url = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"; Size = 1117320736; Sha256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"; Role = "the backup: small and fast" }
)

function Get-BauSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
}

function Select-BauStick {
    $drives = @([IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq "Removable" -and $_.IsReady })
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

function Write-BauReadme([string]$Pack) {
    $text = @"
BAU PACK
========
This folder holds the BAU laptop's local AI models (models\) and, if you made one,
your locked keys file (BAU-KEYS.enc). Every model was checked against its pinned
SHA-256 when it was downloaded, and is checked again on the laptop.

On the BAU laptop:
  1. Plug in this stick and open it once in the file manager.
  2. Open a terminal and type:   sudo bau pack install
  3. Answer yes or no to each question. Nothing changes without your yes.
  4. Bring the stick back: laptop-report.txt on it describes the laptop's Wi-Fi card
     and firmware (addresses and Wi-Fi names hidden), so the Wi-Fi can be fixed.

Nothing on this stick runs by itself when you plug it in.
"@
    [IO.File]::WriteAllText((Join-Path $Pack "README.txt"), $text.Replace("`r`n", "`n"))
}

if ($MyInvocation.InvocationName -ne ".") {
    $models = $BauModels
    if ($Manifest) {
        $models = @()
        foreach ($m in (ConvertFrom-Json (Get-Content -Raw -LiteralPath $Manifest))) { $models += $m }
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

    $need = [long]0
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
        $final = Join-Path $dir $m.File
        $part = "$final.part"
        if (Test-Path -LiteralPath $final) {
            if ((Get-BauSha256 $final) -eq $m.Sha256) { Write-Host "$($m.Id): already on the stick, checked."; continue }
            Remove-Item -LiteralPath $final
        }
        Write-Host "$($m.Id): downloading..."
        & $curl -L --fail --retry 3 -C - -o $part $m.Url
        if ($LASTEXITCODE -ne 0) {
            Write-Host "$($m.Id): download stopped. Run this again to resume." -ForegroundColor Yellow
            $failed++
            continue
        }
        if ((Get-BauSha256 $part) -ne $m.Sha256) {
            Remove-Item -LiteralPath $part
            Write-Host "$($m.Id): the file does not match its pinned SHA-256, so it was deleted." -ForegroundColor Red
            $failed++
            continue
        }
        Move-Item -LiteralPath $part -Destination $final -Force
        Write-Host "$($m.Id): downloaded and checked." -ForegroundColor Green
    }

    $keys = Join-Path $PSScriptRoot "BAU-KEYS.enc"
    if (Test-Path -LiteralPath $keys) {
        Copy-Item -LiteralPath $keys -Destination (Join-Path $pack "BAU-KEYS.enc") -Force
        Write-Host "BAU-KEYS.enc: copied (it stays locked with your passphrase)."
    }
    Write-BauReadme $pack

    Write-Host ""
    if ($failed) {
        Write-Host "$failed model(s) are not on the stick yet. Run this again." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "The BAU Pack is ready." -ForegroundColor Green
    Write-Host "On the laptop: plug it in, open it once in the file manager, then: sudo bau pack install"
    exit 0
}
