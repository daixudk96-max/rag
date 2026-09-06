param(
  [string]$ProjectKey = "rag-local",
  [string]$ProjectName = "rag-local",
  [string]$HostUrl = "http://host.docker.internal:19000",
  [string]$Sources = "llamaindex_runtime,tests,verification",
  [string]$Exclusions = "**/__pycache__/**,.claude/**,docs/**",
  [string]$PythonVersion = "3.11"
)

if (-not $env:SONAR_TOKEN) {
  throw "SONAR_TOKEN is not set in the environment."
}

$repoRoot = Split-Path -Parent $PSScriptRoot

rtk docker run --rm `
  -v "${repoRoot}:/usr/src" `
  -e SONAR_HOST_URL="$HostUrl" `
  -e SONAR_TOKEN="$env:SONAR_TOKEN" `
  sonarsource/sonar-scanner-cli `
  --define sonar.projectKey=$ProjectKey `
  --define sonar.projectName=$ProjectName `
  --define sonar.sources=$Sources `
  --define sonar.exclusions=$Exclusions `
  --define sonar.python.version=$PythonVersion
