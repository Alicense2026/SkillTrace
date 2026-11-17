# Windows PowerShell 5.1+ / PowerShell 7. Python 3.11+.
[CmdletBinding()]
param(
    [string]$InputPath = "aggregate_all_16927\result.csv",
    [string]$OutputDir = "runs\luna-preview",
    [string]$ConfigPath = "configs\experiment.toml",
    [ValidateRange(1,2147483647)][int]$Limit = 1,
    [ValidateRange(0,2147483647)][int]$Offset = 0,
    [switch]$Execute
)
$ErrorActionPreference = "Stop"
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $cliArgs = @("-3", "-m", "license_checker", "experiment", "--input", $InputPath,
        "--output-dir", $OutputDir, "--config", $ConfigPath, "--limit", "$Limit", "--offset", "$Offset")
    if ($Execute) { $cliArgs += "--execute" }
    & py @cliArgs
    if ($LASTEXITCODE -ne 0) { throw "Experiment failed; inspect the run summary/errors." }
} finally {
    Pop-Location
}
