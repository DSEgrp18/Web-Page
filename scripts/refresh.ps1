<#
.SYNOPSIS
    Bring the running reader up to date with the code in this folder.

.DESCRIPTION
    Pulls the current branch, rebuilds the images one at a time, recreates only
    the containers whose image changed, and waits until the API is healthy.
    Books, reading positions, and bookmarks live in the database volume and are
    kept.

    It works out the settings rather than asking for them:

    - The real voice is used when models/xtts_si_female/model.pth exists, and
      the placeholder tone otherwise.
    - Written (Gemini) study answers are used when .env sets GEMINI_API_KEY, and
      extracts from the book otherwise. The key itself is never printed.

    Images are built one at a time on purpose. Built together, next to a loaded
    voice model, they have run Docker out of memory on an 8 GB allowance.

.PARAMETER NoPull
    Rebuild what is in this folder now, without fetching from GitHub.

.PARAMETER NoVoice
    Use the placeholder tone even if the model is present. Saves several
    gigabytes of memory and a few minutes of loading.

.PARAMETER Only
    Rebuild only these services, for example -Only web, or -Only api,worker.

.EXAMPLE
    .\refresh
.EXAMPLE
    .\refresh -Only web
#>
[CmdletBinding()]
param(
    [switch]$NoPull,
    [switch]$NoVoice,
    [ValidateSet("web", "api", "worker")]
    [string[]]$Only
)

# Not "Stop": Windows PowerShell 5.1 turns a native command's stderr into a
# terminating error under it, even when the command succeeds, and git and
# docker both write progress to stderr. Every native call checks its exit code
# instead.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step([string]$text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Fail([string]$text) { Write-Host "`n$text" -ForegroundColor Red; exit 1 }

# -- Docker --------------------------------------------------------------------

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "Docker is not running. Start Docker Desktop, wait until it says it is running, and try again."
}

# -- Code ----------------------------------------------------------------------

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($NoPull) {
    Step "Using the code already in this folder (branch $branch)"
} else {
    Step "Getting the latest code for branch $branch"
    # Fast-forward only: this never merges, rebases, or discards anything. If
    # the branch has diverged or has conflicting local edits, it stops and says
    # so rather than guessing.
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not update branch $branch automatically. Nothing was rebuilt. Run 'git status' to see why, or use -NoPull to rebuild what you have."
    }
}

# -- Settings ------------------------------------------------------------------

$files = @("-f", "infra/docker-compose.yml")

$model = Join-Path $root "models/xtts_si_female/model.pth"
if (-not $NoVoice -and (Test-Path $model)) {
    $env:MODEL_DIR = (Join-Path $root "models") -replace "\\", "/"
    $files += @("-f", "infra/compose.voice.yml")
    $voice = "real voice"
} else {
    $voice = "placeholder tone (no real voice)"
}

if (-not $env:SINHALA_READER_ANSWERS) {
    $hasKey = (Test-Path ".env") -and (Select-String -Path ".env" -Pattern "^\s*GEMINI_API_KEY\s*=\s*\S" -Quiet)
    $env:SINHALA_READER_ANSWERS = if ($hasKey) { "gemini" } else { "extractive" }
}
$answers = if ($env:SINHALA_READER_ANSWERS -eq "gemini") { "written by Gemini" } else { "extracts from the book" }

Write-Host "    Voice:   $voice"
Write-Host "    Answers: $answers"

# -- Build ---------------------------------------------------------------------

$services = if ($Only) { $Only } else { @("web", "api", "worker") }
foreach ($service in $services) {
    Step "Building $service"
    docker compose @files build $service
    if ($LASTEXITCODE -ne 0) {
        Fail "Building $service failed. The containers already running were not changed. If the log mentions 'exit code: 137' or 'killed', Docker ran out of memory."
    }
}

# -- Start ---------------------------------------------------------------------

Step "Starting the updated containers"
docker compose @files up -d
if ($LASTEXITCODE -ne 0) { Fail "Starting the containers failed. See the messages above." }

Step "Waiting for the API"
$api = "$(docker compose @files ps -q api)".Trim()
if (-not $api) { Fail "The API container was not created. See the messages above." }
$deadline = (Get-Date).AddMinutes(5)
do {
    Start-Sleep -Seconds 3
    $health = (docker inspect --format "{{.State.Health.Status}}" $api 2>$null)
    if ($health -eq "healthy") { break }
    $state = (docker inspect --format "{{.State.Status}}" $api 2>$null)
    if ($state -eq "exited") {
        Fail "The API stopped while starting. See why with: docker logs --tail 50 sinhala-reader-api-1"
    }
} while ((Get-Date) -lt $deadline)
if ($health -ne "healthy") {
    Fail "The API did not become healthy within 5 minutes. See why with: docker logs --tail 50 sinhala-reader-api-1"
}

# -- Report --------------------------------------------------------------------

docker compose @files ps

$note = ""
try {
    $ready = Invoke-RestMethod -Uri "http://127.0.0.1:8000/readiness" -TimeoutSec 10
    if ($voice -eq "real voice" -and -not $ready.real_model) {
        $note = "The voice model is still loading. Audio will work in a few minutes."
    }
} catch {
    $note = "The API is up, but its readiness check did not answer yet."
}

Write-Host "`nDone. Open http://localhost:3000 and press Ctrl+Shift+R." -ForegroundColor Green
if ($note) { Write-Host $note -ForegroundColor Yellow }
