<#
BAU keys export (Windows). Run it on the computer that has your API keys: it finds keys in
your environment variables and in the .env files you give it, shows their NAMES only, and
locks them into one file, BAU-KEYS.enc, with a passphrase you choose. It changes nothing
on this computer. No Python needed.

Easiest: double-click BAU-Keys-Export.cmd (drop .env files onto it to include them), or:

    powershell -ExecutionPolicy Bypass -File .\bau-keys-export.ps1 [path\to\.env ...]

Then carry BAU-KEYS.enc to the BAU laptop and run: sudo bau keys import BAU-KEYS.enc
The file is AES-256 locked in openssl's format (PBKDF2-SHA256, 600000 rounds), so the
laptop opens it with openssl. docs/KEYS.md explains every step.
#>
param(
    [string]$Out = (Join-Path (Get-Location) "BAU-KEYS.enc"),
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$From = @(),
    [switch]$Yes
)

# Same rule as the laptop (src/bau/keys.py): only credential-shaped names.
$BauNameRe = '^[A-Z][A-Z0-9_]*(API_KEY[A-Z0-9_]*|_KEY|_TOKEN|_SECRET|_CLIENT_ID|_KEY_ID)$'

function Test-BauKeyName([string]$Name) {
    return ($Name -cmatch $BauNameRe) -and ($Name -notmatch '^(BAU_|LD_|PYTHON)')
}

function Get-BauKeys([string[]]$Files) {
    $keys = [ordered]@{}
    # Machine, then User, then this window, then the .env files: a later source wins.
    foreach ($scope in @("Machine", "User", "Process")) {
        $vars = [Environment]::GetEnvironmentVariables($scope)
        foreach ($name in @($vars.Keys)) {
            $n = "$name".ToUpper()
            if ((Test-BauKeyName $n) -and "$($vars[$name])") { $keys[$n] = "$($vars[$name])" }
        }
    }
    foreach ($f in $Files) {
        if (-not $f) { continue }
        foreach ($line in (Get-Content -LiteralPath $f -ErrorAction Stop)) {
            $l = $line.Trim()
            if ($l.StartsWith("export ")) { $l = $l.Substring(7).Trim() }
            if (-not $l -or $l.StartsWith("#") -or -not $l.Contains("=")) { continue }
            $i = $l.IndexOf("=")
            $n = $l.Substring(0, $i).Trim().ToUpper()
            $v = $l.Substring($i + 1).Trim()
            if ($v.Length -ge 2 -and ($v[0] -eq '"' -or $v[0] -eq "'") -and $v[-1] -eq $v[0]) {
                $v = $v.Substring(1, $v.Length - 2)
            }
            if ((Test-BauKeyName $n) -and $v) { $keys[$n] = $v }
        }
    }
    return $keys
}

function ConvertTo-BauLocked([string]$Text, [string]$Passphrase) {
    # openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -salt, byte for byte.
    $salt = New-Object byte[] 8
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($salt)
    $kdf = New-Object Security.Cryptography.Rfc2898DeriveBytes -ArgumentList @(
        $Passphrase, $salt, 600000, [Security.Cryptography.HashAlgorithmName]::SHA256)
    $kb = $kdf.GetBytes(48)
    $aes = [Security.Cryptography.Aes]::Create()
    $aes.Mode = [Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
    $aes.Key = [byte[]]$kb[0..31]
    $aes.IV = [byte[]]$kb[32..47]
    $plain = (New-Object Text.UTF8Encoding $false).GetBytes($Text)
    $ct = $aes.CreateEncryptor().TransformFinalBlock($plain, 0, $plain.Length)
    return [byte[]]([Text.Encoding]::ASCII.GetBytes("Salted__") + $salt + $ct)
}

function Read-BauPassphrase {
    if ($env:BAU_KEYS_PASSPHRASE) { return $env:BAU_KEYS_PASSPHRASE }
    while ($true) {
        $a = (New-Object System.Net.NetworkCredential("", (Read-Host "Choose a passphrase (8+ characters)" -AsSecureString))).Password
        $b = (New-Object System.Net.NetworkCredential("", (Read-Host "Type it again" -AsSecureString))).Password
        if ($a -ne $b) { Write-Host "They differ - try again." -ForegroundColor Yellow; continue }
        if ($a.Length -lt 8) { Write-Host "Too short - use 8 or more characters." -ForegroundColor Yellow; continue }
        return $a
    }
}

if ($MyInvocation.InvocationName -ne ".") {
    $keys = Get-BauKeys $From
    if (-not $keys.Count) {
        Write-Host "No API keys found in your environment variables." -ForegroundColor Yellow
        Write-Host "If they are in .env files, drop those files onto BAU-Keys-Export.cmd."
        exit 1
    }
    Write-Host "Keys found (names only):"
    foreach ($n in ($keys.Keys | Sort-Object)) { Write-Host "  $n" }
    if (-not $Yes) {
        $ok = Read-Host "Lock these $($keys.Count) keys into $Out ? [y/N]"
        if ($ok -notmatch '^[yY]') { Write-Host "Nothing written."; exit 0 }
    }
    $lines = @("# BAU-KEYS v1") + @($keys.Keys | Sort-Object | ForEach-Object { "$_=$($keys[$_])" })
    $pass = Read-BauPassphrase
    [IO.File]::WriteAllBytes($Out, (ConvertTo-BauLocked (($lines -join "`n") + "`n") $pass))
    Write-Host ""
    Write-Host "Written: $Out" -ForegroundColor Green
    Write-Host "Carry it to the BAU laptop and run: sudo bau keys import $(Split-Path -Leaf $Out)"
    Write-Host "Remember the passphrase; delete the file once it is imported."
}
