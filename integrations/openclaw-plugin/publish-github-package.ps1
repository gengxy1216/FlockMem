Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if ([string]::IsNullOrWhiteSpace($env:NODE_AUTH_TOKEN)) {
  if ([string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
    Write-Error "Missing token. Set NODE_AUTH_TOKEN or GITHUB_TOKEN with a GitHub PAT (write:packages)."
    exit 1
  }
  $env:NODE_AUTH_TOKEN = $env:GITHUB_TOKEN
}

$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$env:npm_config_cache = Join-Path $repoRoot ".tmp_npm_cache_publish"

npm run release:github
