param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot | Split-Path -Parent),
    [string[]]$TrackedFiles
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function New-A3ReleaseError {
    param([string]$Code, [string]$Message)
    $exception = [InvalidOperationException]::new($Message)
    $exception.Data['A3Code'] = $Code
    return $exception
}

function Get-A3TrackedFiles {
    param([string]$RepositoryPath)

    $process = [Diagnostics.Process]::new()
    $process.StartInfo = [Diagnostics.ProcessStartInfo]::new()
    $process.StartInfo.FileName = 'git'
    $process.StartInfo.Arguments = ('-C "{0}" ls-files -z' -f $RepositoryPath.Replace('"', ''))
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    $null = $process.Start()
    $output = $process.StandardOutput.ReadToEnd()
    $errorOutput = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw (New-A3ReleaseError 'A3_RELEASE_SECRET_SCAN_FAILED' 'Unable to obtain the tracked release file list.')
    }
    return @($output -split [char]0 | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Resolve-A3TrackedPath {
    param([string]$RepositoryPath, [string]$RelativePath)

    if ([string]::IsNullOrWhiteSpace($RelativePath) -or [IO.Path]::IsPathRooted($RelativePath) -or
        @($RelativePath -split '[\\/]' | Where-Object { $_ -in @('', '.', '..') }).Count -gt 0) {
        throw (New-A3ReleaseError 'A3_RELEASE_SECRET_SCAN_FAILED' 'A tracked release file path is invalid.')
    }
    $root = $RepositoryPath.TrimEnd('\', '/')
    $path = [IO.Path]::GetFullPath((Join-Path $root $RelativePath))
    if (-not $path.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw (New-A3ReleaseError 'A3_RELEASE_SECRET_SCAN_FAILED' 'A tracked release file is unavailable.')
    }
    return $path
}

function Test-A3KnownBinary {
    param([byte[]]$Bytes)
    if ($Bytes.Length -ge 4) {
        if ($Bytes[0] -eq 0x89 -and $Bytes[1] -eq 0x50 -and $Bytes[2] -eq 0x4E -and $Bytes[3] -eq 0x47) { return $true }
        if ($Bytes[0] -eq 0x50 -and $Bytes[1] -eq 0x4B -and $Bytes[2] -in @(0x03, 0x05, 0x07) -and $Bytes[3] -in @(0x04, 0x06, 0x08)) { return $true }
        if ($Bytes[0] -eq 0x00 -and $Bytes[1] -eq 0x00 -and $Bytes[2] -eq 0x01 -and $Bytes[3] -eq 0x00) { return $true }
    }
    if ($Bytes.Length -ge 12 -and [Text.Encoding]::ASCII.GetString($Bytes, 0, 4) -ceq 'RIFF' -and
        [Text.Encoding]::ASCII.GetString($Bytes, 8, 4) -ceq 'WEBP') { return $true }
    $controlCount = @($Bytes | Where-Object { $_ -eq 0 -or ($_ -lt 9) -or ($_ -gt 13 -and $_ -lt 32) }).Count
    return $Bytes.Length -gt 0 -and ($controlCount / $Bytes.Length) -ge 0.20
}

function Read-A3TrackedText {
    param([string]$LiteralPath)
    $bytes = [IO.File]::ReadAllBytes($LiteralPath)
    if ($bytes.Length -eq 0) { return '' }
    try {
        if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
            return [Text.UTF8Encoding]::new($false, $true).GetString($bytes, 3, $bytes.Length - 3)
        }
        if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
            return [Text.UnicodeEncoding]::new($false, $false, $true).GetString($bytes, 2, $bytes.Length - 2)
        }
        if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
            return [Text.UnicodeEncoding]::new($true, $false, $true).GetString($bytes, 2, $bytes.Length - 2)
        }
        if (($bytes.Length % 2) -eq 0 -and $bytes.Length -ge 4) {
            $evenNulls = 0
            $oddNulls = 0
            for ($index = 0; $index -lt $bytes.Length; $index += 2) {
                if ($bytes[$index] -eq 0) { $evenNulls++ }
                if ($bytes[$index + 1] -eq 0) { $oddNulls++ }
            }
            $pairs = $bytes.Length / 2
            if (($oddNulls / $pairs) -ge 0.30 -and ($evenNulls / $pairs) -le 0.05) {
                return [Text.UnicodeEncoding]::new($false, $false, $true).GetString($bytes)
            }
            if (($evenNulls / $pairs) -ge 0.30 -and ($oddNulls / $pairs) -le 0.05) {
                return [Text.UnicodeEncoding]::new($true, $false, $true).GetString($bytes)
            }
        }
        return [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    }
    catch {
        if (Test-A3KnownBinary -Bytes $bytes) { return $null }
        throw (New-A3ReleaseError 'A3_RELEASE_SECRET_SCAN_FAILED' 'A tracked file cannot be safely classified as text or binary.')
    }
}

$repositoryPath = [IO.Path]::GetFullPath($RepositoryRoot)
if (-not (Test-Path -LiteralPath $repositoryPath -PathType Container)) {
    throw (New-A3ReleaseError 'A3_RELEASE_SECRET_SCAN_FAILED' 'The repository root is unavailable.')
}
if (-not $PSBoundParameters.ContainsKey('TrackedFiles')) {
    $TrackedFiles = Get-A3TrackedFiles -RepositoryPath $repositoryPath
}

$unsafeExtensions = @('.pfx', '.p12', '.pem', '.key')
$assignmentPattern = [regex]::new(
    '(?im)^\s*(?:-\s*)?(?:export\s+)?(?:\$env:)?["'']?(AZURE_CLIENT_SECRET|CSC_LINK|WIN_CSC_LINK|CSC_KEY_PASSWORD|WIN_CSC_KEY_PASSWORD)["'']?\s*(?:=|:)\s*(?<value>.+?)\s*$',
    [Text.RegularExpressions.RegexOptions]::CultureInvariant
)
$placeholderPattern = [regex]::new('^\$\{\{\s*secrets\.[A-Za-z0-9_]+\s*\}\}$', [Text.RegularExpressions.RegexOptions]::CultureInvariant)
$violations = [Collections.Generic.List[string]]::new()

foreach ($relativePath in @($TrackedFiles)) {
    $path = Resolve-A3TrackedPath -RepositoryPath $repositoryPath -RelativePath $relativePath
    if ($unsafeExtensions -contains [IO.Path]::GetExtension($path).ToLowerInvariant()) {
        $violations.Add(('{0} [A3_TRACKED_SECRET_EXTENSION]' -f $relativePath))
        continue
    }
    $content = Read-A3TrackedText -LiteralPath $path
    if ($null -eq $content) { continue }
    if ([regex]::IsMatch($content, '-----BEGIN\s+(?:[A-Z0-9 ]+\s+)?PRIVATE KEY-----', [Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
        $violations.Add(('{0} [A3_PRIVATE_KEY_HEADER]' -f $relativePath))
        continue
    }
    foreach ($match in $assignmentPattern.Matches($content)) {
        $value = $match.Groups['value'].Value.Trim()
        if ($value -ne '<stored-only-in-GitHub-Environment>' -and -not $placeholderPattern.IsMatch($value)) {
            $violations.Add(('{0} [A3_SECRET_ASSIGNMENT]' -f $relativePath))
            break
        }
    }
}

if ($violations.Count -gt 0) {
    $violations | ForEach-Object { [Console]::Error.WriteLine($_) }
    throw (New-A3ReleaseError 'A3_RELEASE_SECRET_DETECTED' 'Tracked release source contains prohibited secret material.')
}
