param(
    [switch]$ResetVolumes
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Key
    )

    if (-not (Test-Path $Path)) {
        return $null
    }

    $match = Get-Content $Path |
        Where-Object { $_ -match "^\s*$Key\s*=" } |
        Select-Object -First 1

    if (-not $match) {
        return $null
    }

    $parts = $match.Split("=", 2)
    if ($parts.Count -lt 2) {
        return $null
    }

    return $parts[1].Trim().Trim('"')
}

$defaultChatModel = "qwen2.5-7b-instruct-uncensored-q4km:latest"
$defaultEmbeddingModel = "nomic-embed-text"

$dotEnvPath = Join-Path $repoRoot ".env"
$dotEnvChatModel = Get-DotEnvValue -Path $dotEnvPath -Key "OLLAMA_CHAT_MODEL"
$dotEnvEmbeddingModel = Get-DotEnvValue -Path $dotEnvPath -Key "OLLAMA_EMBEDDING_MODEL"

$chatModel = if ($env:OLLAMA_CHAT_MODEL) {
    $env:OLLAMA_CHAT_MODEL
} elseif ($dotEnvChatModel) {
    $dotEnvChatModel
} else {
    $defaultChatModel
}

$embeddingModel = if ($env:OLLAMA_EMBEDDING_MODEL) {
    $env:OLLAMA_EMBEDDING_MODEL
} elseif ($dotEnvEmbeddingModel) {
    $dotEnvEmbeddingModel
} else {
    $defaultEmbeddingModel
}

$modelfilePath = Join-Path $repoRoot "backend/llm_models/Modelfile.qwen2.5-7b-instruct-uncensored-q4km"
if (-not (Test-Path $modelfilePath)) {
    throw "Modelfile not found: $modelfilePath"
}

$containerModelfilePath = "/models/Modelfile.qwen2.5-7b-instruct-uncensored-q4km"

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Arguments
    )

    Write-Host "> docker compose $Arguments"
    & docker compose $Arguments.Split(" ")
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $Arguments failed"
    }
}

function Wait-OllamaReady {
    $maxAttempts = 90
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        & docker compose exec -T ollama ollama list *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Ollama is ready"
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Timed out waiting for Ollama to become ready"
}

function Ensure-OllamaModel {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ModelName,
        [string]$CreateModelfile
    )

    $modelList = & docker compose exec -T ollama ollama list | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read ollama model list"
    }

    if ($modelList -match [regex]::Escape($ModelName)) {
        Write-Host "Model already exists: $ModelName"
        return
    }

    if ($CreateModelfile) {
        Write-Host "Creating model: $ModelName"
        & docker compose exec -T ollama ollama create $ModelName -f $CreateModelfile
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create model: $ModelName"
        }
        return
    }

    Write-Host "Pulling model: $ModelName"
    & docker compose exec -T ollama ollama pull $ModelName
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to pull model: $ModelName"
    }
}

Push-Location $repoRoot
try {
    if ($ResetVolumes) {
        Invoke-Compose "down -v --remove-orphans"
    }

    Invoke-Compose "up -d --build"
    Wait-OllamaReady

    Ensure-OllamaModel -ModelName $chatModel -CreateModelfile $containerModelfilePath
    Ensure-OllamaModel -ModelName $embeddingModel

    Invoke-Compose "up -d --force-recreate backend"

    Write-Host ""
    Write-Host "Done. Services are ready:"
    Write-Host "- Frontend: http://localhost:3000"
    Write-Host "- Backend:  http://localhost:8000/docs"
    Write-Host ""
    Write-Host "Tip: to include volume reset in one command, run:"
    Write-Host "pwsh ./scripts/reset-and-up.ps1 -ResetVolumes"
}
finally {
    Pop-Location
}
