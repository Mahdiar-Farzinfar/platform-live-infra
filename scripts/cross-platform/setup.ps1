<#
.SYNOPSIS
    Windows wrapper for scripts/cross-platform/setup.py.

.DESCRIPTION
    This file is intentionally limited to Windows-specific bootstrapping:
    repository/path resolution, Python discovery/installation, platform
    context, and argument pass-through. Repository validation, Go setup, and
    installer routing remain in setup.py.

    Python is selected using the pinned value in tooling/.tool-versions.
    Existing interpreters satisfying the repository's >= pin policy are reused.
    If none is usable, the wrapper tries exact-version installs through mise,
    pyenv-win, winget, and Chocolatey, then verifies the resulting interpreter.

.EXAMPLE
    powershell -NoProfile -File .\scripts\cross-platform\setup.ps1 --dry-run

.EXAMPLE
    powershell -NoProfile -File .\scripts\cross-platform\setup.ps1 --verbose --non-interactive
#>

[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:WrapperName = 'cross-platform:setup.ps1'
$script:WrapperCodeValidation = 2
$script:WrapperCodeInstall = 3
$script:WrapperCodeLaunch = 4
$script:WrapperCodeInterrupted = 130
$script:WrapperCodeUnexpected = 99
$script:VerboseMode = $false

function Write-WrapperLog {
    param([Parameter(Mandatory = $true)][string]$Message)
    [Console]::Error.WriteLine("[$script:WrapperName] $Message")
}

function Write-WrapperVerbose {
    param([Parameter(Mandatory = $true)][string]$Message)
    if ($script:VerboseMode) {
        [Console]::Error.WriteLine("[$script:WrapperName][VERBOSE] $Message")
    }
}

function Write-WrapperError {
    param([Parameter(Mandatory = $true)][string]$Message)
    [Console]::Error.WriteLine("[$script:WrapperName][ERROR] $Message")
}

function Throw-WrapperError {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [int]$Code = $script:WrapperCodeValidation
    )
    $exception = New-Object System.Exception $Message
    $exception.Data['WrapperExitCode'] = $Code
    throw $exception
}

function Test-VersionAtLeast {
    param(
        [Parameter(Mandatory = $true)][string]$Actual,
        [Parameter(Mandatory = $true)][string]$Required
    )

    $actualParts = [int[]]($Actual -split '\.')
    $requiredParts = [int[]]($Required -split '\.')
    for ($index = 0; $index -lt 3; $index++) {
        $actualPart = if ($index -lt $actualParts.Count) { $actualParts[$index] } else { 0 }
        $requiredPart = if ($index -lt $requiredParts.Count) { $requiredParts[$index] } else { 0 }
        if ($actualPart -gt $requiredPart) {
            return $true
        }
        if ($actualPart -lt $requiredPart) {
            return $false
        }
    }
    return $true
}

function Parse-ConcreteVersion {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Source
    )

    $candidate = $Value.Trim()
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        Throw-WrapperError "${Source}: version is empty."
    }
    if ($candidate -match '(?i)^(latest|stable|current|head|master|main|\*)$') {
        Throw-WrapperError "${Source}: floating versions are not supported: '$candidate'."
    }
    if ($candidate -match '[<>=~*|,^/ ]') {
        Throw-WrapperError "${Source}: version ranges are not supported: '$candidate'."
    }
    if ($candidate -notmatch '^(?:v)?([0-9]+)\.([0-9]+)(?:\.([0-9]+))?$') {
        Throw-WrapperError "${Source}: malformed concrete version: '$candidate'."
    }

    try {
        $parts = @([int]$Matches[1], [int]$Matches[2])
        if ($null -ne $Matches[3] -and $Matches[3] -ne '') {
            $parts += [int]$Matches[3]
        }
    }
    catch {
        Throw-WrapperError "${Source}: version contains an invalid numeric component: '$candidate'."
    }

    $normalized = ($parts -join '.')
    [pscustomobject]@{
        Raw        = $candidate
        Parts      = [int[]]$parts
        Normalized = $normalized
    }
}

function Read-ToolVersionsFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Throw-WrapperError "Tool versions file not found: $Path"
    }

    try {
        $lines = @(Get-Content -LiteralPath $Path -Encoding UTF8 -ErrorAction Stop)
    }
    catch {
        Throw-WrapperError "Unable to read tool versions file '$Path': $($_.Exception.Message)"
    }

    $tools = @{}
    $lineNumber = 0
    foreach ($originalLine in $lines) {
        $lineNumber++
        $line = ($originalLine -replace '#.*$', '').Trim()
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $fields = @($line -split '\s+')
        if ($fields.Count -ne 2 -or $fields[0] -notmatch '^[A-Za-z0-9_.-]+$') {
            Throw-WrapperError "${Path}:${lineNumber}: malformed entry; expected '<tool> <version>'."
        }
        $tool = [string]$fields[0]
        if ($tools.ContainsKey($tool)) {
            Throw-WrapperError "${Path}:${lineNumber}: duplicate tool entry '$tool'."
        }
        $tools[$tool] = Parse-ConcreteVersion `
            -Value ([string]$fields[1]) `
            -Source "${Path}:${lineNumber} ($tool)"
    }

    if ($tools.Count -eq 0) {
        Throw-WrapperError "Tool versions file is empty: $Path"
    }
    return ,$tools
}

function Test-Mirror {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Canonical,
        [Parameter(Mandatory = $true)][string]$MirrorPath
    )

    $mirror = Read-ToolVersionsFile -Path $MirrorPath
    foreach ($tool in $Canonical.Keys) {
        if (-not $mirror.ContainsKey($tool)) {
            Throw-WrapperError "Mirror '$MirrorPath' is missing tool '$tool'."
        }
        if (-not (Test-VersionAtLeast `
                    -Actual $mirror[$tool].Normalized `
                    -Required $Canonical[$tool].Normalized) `
                -or -not (Test-VersionAtLeast `
                    -Actual $Canonical[$tool].Normalized `
                    -Required $mirror[$tool].Normalized)) {
            Throw-WrapperError `
                "Mirror version mismatch for '$tool': canonical=$($Canonical[$tool].Normalized), mirror=$($mirror[$tool].Normalized)."
        }
    }
    foreach ($tool in $mirror.Keys) {
        if (-not $Canonical.ContainsKey($tool)) {
            Throw-WrapperError "Mirror '$MirrorPath' contains unexpected tool '$tool'."
        }
    }
    if (-not $mirror.ContainsKey('python')) {
        Throw-WrapperError "Mirror '$MirrorPath' does not contain a python entry."
    }
    return ,$mirror
}

function Get-CommandPaths {
    param([Parameter(Mandatory = $true)][string]$Name)

    $paths = @()
    $seen = @{}
    foreach ($command in @(Get-Command -Name $Name -CommandType Application -All -ErrorAction SilentlyContinue)) {
        $path = if ($command.Path) { [string]$command.Path } else { [string]$command.Source }
        if ($path -and -not $seen.ContainsKey($path)) {
            $seen[$path] = $true
            $paths += $path
        }
    }
    return ,$paths
}

function Get-PythonCandidates {
    $candidates = @()
    $seen = @{}

    foreach ($pyPath in (Get-CommandPaths -Name 'py')) {
        if ($pyPath) {
            $key = "$pyPath|py3"
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                $candidates += [pscustomobject]@{
                    Executable = $pyPath
                    PrefixArgs = @('-3')
                    Label      = "$pyPath -3"
                }
            }
        }
    }

    foreach ($name in @('python', 'python3')) {
        foreach ($path in (Get-CommandPaths -Name $name)) {
            if (-not $path) {
                continue
            }
            $key = "$path|direct"
            if ($seen.ContainsKey($key)) {
                continue
            }
            $seen[$key] = $true
            $candidates += [pscustomobject]@{
                Executable = $path
                PrefixArgs = @()
                Label      = $path
            }
        }
    }
    return ,$candidates
}

function Get-PythonVersion {
    param([Parameter(Mandatory = $true)]$Candidate)

    # Avoid embedded double quotes: Windows PowerShell 5.1 can strip them
    # while marshaling arguments to native executables.
    $probe = 'import sys; print(chr(46).join(map(str, sys.version_info[:3])))'
    try {
        $output = (& $Candidate.Executable @($Candidate.PrefixArgs) -c $probe 2>$null | Out-String).Trim()
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0 -or $output -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
            return $null
        }
        return $output
    }
    catch {
        return $null
    }
}

function Find-SuitablePython {
    param([Parameter(Mandatory = $true)][string]$RequiredVersion)

    foreach ($candidate in (Get-PythonCandidates)) {
        $version = Get-PythonVersion -Candidate $candidate
        if ($version -and (Test-VersionAtLeast -Actual $version -Required $RequiredVersion)) {
            return [pscustomobject]@{
                Candidate = $candidate
                Version   = $version
            }
        }
        if ($version) {
            Write-WrapperVerbose `
                "Skipping $($candidate.Label) (Python $version); requires >= $RequiredVersion."
        }
        else {
            Write-WrapperVerbose "Skipping $($candidate.Label); interpreter probe failed."
        }
    }
    return $null
}

function Refresh-ProcessPath {
    $paths = @()
    foreach ($scope in @('Machine', 'User')) {
        try {
            $value = [Environment]::GetEnvironmentVariable('Path', $scope)
            if ($value) {
                $paths += $value
            }
        }
        catch {
            Write-WrapperVerbose "Unable to read $scope PATH: $($_.Exception.Message)"
        }
    }
    if ($env:Path) {
        $paths += $env:Path
    }
    if ($paths.Count -gt 0) {
        $env:Path = ($paths -join ';')
    }
}

function Set-ResolvedPythonFromCandidate {
    param(
        [Parameter(Mandatory = $true)]$Candidate,
        [Parameter(Mandatory = $true)][string]$RequiredVersion
    )
    $version = Get-PythonVersion -Candidate $Candidate
    if (-not $version -or -not (Test-VersionAtLeast -Actual $version -Required $RequiredVersion)) {
        return $false
    }
    $script:ResolvedPython = $Candidate
    $script:ResolvedPythonVersion = $version
    return $true
}

function Install-WithMise {
    param([Parameter(Mandatory = $true)][string]$RequiredVersion)
    $executable = (Get-CommandPaths -Name 'mise' | Select-Object -First 1)
    if (-not $executable) {
        return $false
    }

    Write-WrapperLog "Installing Python $RequiredVersion via mise."
    $previous = $env:MISE_YES
    try {
        $env:MISE_YES = '1'
        & $executable install "python@$RequiredVersion"
        if ($LASTEXITCODE -ne 0) {
            throw "mise exited with code $LASTEXITCODE."
        }
        $prefix = (& $executable where "python@$RequiredVersion" 2>$null | Out-String).Trim()
    }
    finally {
        if ($null -eq $previous) {
            Remove-Item Env:MISE_YES -ErrorAction SilentlyContinue
        }
        else {
            $env:MISE_YES = $previous
        }
    }
    if (-not $prefix) {
        throw 'mise did not return an installation path.'
    }
    foreach ($path in @(
            (Join-Path $prefix 'python.exe'),
            (Join-Path $prefix 'bin\python.exe')
        )) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $candidate = [pscustomobject]@{
                Executable = $path
                PrefixArgs = @()
                Label      = $path
            }
            if (Set-ResolvedPythonFromCandidate -Candidate $candidate -RequiredVersion $RequiredVersion) {
                return $true
            }
        }
    }
    throw "mise installation path does not contain a usable Python interpreter: $prefix"
}

function Install-WithPyenv {
    param([Parameter(Mandatory = $true)][string]$RequiredVersion)
    $executable = (Get-CommandPaths -Name 'pyenv' | Select-Object -First 1)
    if (-not $executable) {
        return $false
    }

    Write-WrapperLog "Installing Python $RequiredVersion via pyenv."
    & $executable install --skip-existing $RequiredVersion
    if ($LASTEXITCODE -ne 0) {
        throw "pyenv exited with code $LASTEXITCODE."
    }
    $pyenvRoot = (& $executable root 2>$null | Out-String).Trim()
    if (-not $pyenvRoot) {
        throw 'pyenv did not return its root directory.'
    }
    $path = Join-Path (Join-Path (Join-Path $pyenvRoot 'versions') $RequiredVersion) 'python.exe'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "pyenv did not produce the expected interpreter: $path"
    }
    $candidate = [pscustomobject]@{
        Executable = $path
        PrefixArgs = @()
        Label      = $path
    }
    if (Set-ResolvedPythonFromCandidate -Candidate $candidate -RequiredVersion $RequiredVersion) {
        return $true
    }
    throw "Python installed by pyenv failed version verification: $path"
}

function Install-WithWinget {
    param([Parameter(Mandatory = $true)][string]$RequiredVersion)
    $executable = (Get-CommandPaths -Name 'winget' | Select-Object -First 1)
    if (-not $executable) {
        return $false
    }

    $parts = $RequiredVersion -split '\.'
    $packageId = "Python.Python.$($parts[0]).$($parts[1])"
    Write-WrapperLog `
        "Installing exact Python $RequiredVersion via winget package $packageId."
    & $executable install `
        --id $packageId `
        --exact `
        --version $RequiredVersion `
        --silent `
        --accept-package-agreements `
        --accept-source-agreements `
        --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        throw "winget exited with code $LASTEXITCODE while installing $packageId@$RequiredVersion."
    }
    Refresh-ProcessPath
    $resolved = Find-SuitablePython -RequiredVersion $RequiredVersion
    if ($null -ne $resolved) {
        $script:ResolvedPython = $resolved.Candidate
        $script:ResolvedPythonVersion = $resolved.Version
        return $true
    }
    throw "winget completed, but no suitable Python $RequiredVersion interpreter was found."
}

function Install-WithChocolatey {
    param([Parameter(Mandatory = $true)][string]$RequiredVersion)
    $executable = (Get-CommandPaths -Name 'choco' | Select-Object -First 1)
    if (-not $executable) {
        return $false
    }

    Write-WrapperLog "Installing exact Python $RequiredVersion via Chocolatey."
    & $executable install python `
        --version=$RequiredVersion `
        --exact `
        --yes `
        --no-progress
    if ($LASTEXITCODE -ne 0) {
        throw "Chocolatey exited with code $LASTEXITCODE."
    }
    Refresh-ProcessPath
    $resolved = Find-SuitablePython -RequiredVersion $RequiredVersion
    if ($null -ne $resolved) {
        $script:ResolvedPython = $resolved.Candidate
        $script:ResolvedPythonVersion = $resolved.Version
        return $true
    }
    throw "Chocolatey completed, but no suitable Python $RequiredVersion interpreter was found."
}

function Install-Python {
    param([Parameter(Mandatory = $true)][string]$RequiredVersion)

    $failures = @()
    foreach ($installer in @(
            @{ Name = 'mise'; Action = { Install-WithMise -RequiredVersion $RequiredVersion } },
            @{ Name = 'pyenv'; Action = { Install-WithPyenv -RequiredVersion $RequiredVersion } },
            @{ Name = 'winget'; Action = { Install-WithWinget -RequiredVersion $RequiredVersion } },
            @{ Name = 'Chocolatey'; Action = { Install-WithChocolatey -RequiredVersion $RequiredVersion } }
        )) {
        try {
            if (& $installer.Action) {
                return
            }
        }
        catch {
            $failures += "$($installer.Name): $($_.Exception.Message)"
            Write-WrapperVerbose $failures[-1]
        }
    }

    $detail = if ($failures.Count -gt 0) {
        $failures -join '; '
    }
    else {
        'no supported installer was found'
    }
    Throw-WrapperError `
        "Unable to install exact Python $RequiredVersion on Windows ($detail). Install it with mise, pyenv-win, winget, or Chocolatey, then rerun." `
        -Code $script:WrapperCodeInstall
}

try {
    $script:VerboseMode = @($RemainingArgs) -contains '--verbose'
    $invokedScriptPath = $MyInvocation.MyCommand.Path
    if ([string]::IsNullOrWhiteSpace($invokedScriptPath)) {
        Throw-WrapperError 'Unable to determine the PowerShell script path.'
    }

    $scriptPath = (Resolve-Path -LiteralPath $invokedScriptPath -ErrorAction Stop).Path
    $scriptDir = Split-Path -Parent -Path $scriptPath
    $rootDir = (Resolve-Path -LiteralPath (Join-Path $scriptDir '..\..') -ErrorAction Stop).Path
    $setupPyCandidate = Join-Path $scriptDir 'setup.py'
    if (-not (Test-Path -LiteralPath $setupPyCandidate -PathType Leaf)) {
        Throw-WrapperError "Source-of-truth script not found: $setupPyCandidate"
    }
    $setupPy = (Resolve-Path -LiteralPath $setupPyCandidate -ErrorAction Stop).Path
    $toolVersionsPath = Join-Path (Join-Path $rootDir 'tooling') '.tool-versions'
    $mirrorPath = Join-Path (Join-Path (Join-Path $rootDir 'tooling') 'cross-platform') 'asdf-tool-versions'

    $canonical = Read-ToolVersionsFile -Path $toolVersionsPath
    if (-not $canonical.ContainsKey('python')) {
        Throw-WrapperError "No 'python <version>' entry found in: $toolVersionsPath"
    }
    $requiredPython = $canonical['python'].Normalized
    Test-Mirror -Canonical $canonical -MirrorPath $mirrorPath | Out-Null
    Write-WrapperLog "Repository root: $rootDir"
    Write-WrapperLog "Required Python version: $requiredPython"

    $resolved = Find-SuitablePython -RequiredVersion $requiredPython
    if ($null -eq $resolved) {
        if (@($RemainingArgs) -contains '--dry-run') {
            Throw-WrapperError `
                "No usable Python >= $requiredPython was found. --dry-run forbids installation, so install the pinned version and rerun." `
                -Code $script:WrapperCodeInstall
        }
        Write-WrapperLog "No usable Python >= $requiredPython found; attempting exact-version installation."
        Install-Python -RequiredVersion $requiredPython
        Refresh-ProcessPath
        $resolved = Find-SuitablePython -RequiredVersion $requiredPython
        if ($null -eq $resolved) {
            Throw-WrapperError `
                "Python installation completed, but no usable interpreter >= $requiredPython was found." `
                -Code $script:WrapperCodeInstall
        }
    }

    $script:ResolvedPython = $resolved.Candidate
    $script:ResolvedPythonVersion = $resolved.Version
    $env:BOOTSTRAP_WRAPPER_KIND = 'powershell'
    $env:BOOTSTRAP_WRAPPER_OS = 'windows'
    $env:BOOTSTRAP_WRAPPER_OS_RAW = [System.Environment]::OSVersion.VersionString
    $env:BOOTSTRAP_WRAPPER_ARCH = if ([Environment]::Is64BitOperatingSystem) { 'x86_64' } else { 'x86' }
    $env:BOOTSTRAP_WRAPPER_DISTRO = ''
    $env:BOOTSTRAP_WRAPPER_KERNEL = [System.Environment]::OSVersion.Version.ToString()
    $env:BOOTSTRAP_WRAPPER_WSL = '0'
    $env:CROSS_PLATFORM_PLATFORM = 'windows'
    Write-WrapperLog "Using Python: $($script:ResolvedPython.Label) (Python $($script:ResolvedPythonVersion))"
    Write-WrapperLog "Delegating to SoT: $setupPy"

    # Wrapper-owned arguments are appended so a user cannot override the
    # repository root or Windows platform context with duplicate CLI options.
    $pythonArgs = @($setupPy) + @($RemainingArgs) + @(
        '--root', $rootDir,
        '--platform', 'windows'
    )
    & $script:ResolvedPython.Executable @($script:ResolvedPython.PrefixArgs) @pythonArgs
    $setupExitCode = $LASTEXITCODE
    if ($null -eq $setupExitCode) {
        $setupExitCode = 0
    }
    exit ([int]$setupExitCode)
}
catch [System.Management.Automation.PipelineStoppedException] {
    Write-WrapperError 'Interrupted by user.'
    exit $script:WrapperCodeInterrupted
}
catch {
    $code = $script:WrapperCodeUnexpected
    if ($_.Exception.Data.Contains('WrapperExitCode')) {
        $code = [int]$_.Exception.Data['WrapperExitCode']
    }
    Write-WrapperError $_.Exception.Message
    if ($script:VerboseMode) {
        Write-WrapperVerbose $_.ScriptStackTrace
    }
    exit $code
}
