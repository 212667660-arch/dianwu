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

$repositoryPath = [IO.Path]::GetFullPath($RepositoryRoot)
if (-not (Test-Path -LiteralPath $repositoryPath -PathType Container)) {
    throw (New-A3ReleaseError 'A3_RELEASE_SECRET_SCAN_FAILED' 'The repository root is unavailable.')
}
if (-not $PSBoundParameters.ContainsKey('TrackedFiles')) {
    $TrackedFiles = Get-A3TrackedFiles -RepositoryPath $repositoryPath
}

$unsafeExtensions = @('.pfx', '.p12', '.pem', '.key')
$assignmentPattern = [regex]::new(
    '(?im)^\s*(?:-\s*)?(?:export\s+)?(AZURE_CLIENT_SECRET|CSC_LINK|WIN_CSC_LINK|CSC_KEY_PASSWORD|WIN_CSC_KEY_PASSWORD)\s*(?:=|:)\s*(?<value>.+?)\s*$',
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
    try {
        $content = [IO.File]::ReadAllText($path, [Text.UTF8Encoding]::new($false, $true))
    }
    catch {
        continue
    }
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
