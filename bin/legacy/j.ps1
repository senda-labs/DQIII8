# ══════════════════════════════════════════════════════════════════
# j.ps1 — JARVIS launcher
# Usage: j [project] [flags]
# Flags: --model local|claude|auto  --status  --sync  --audit
#        --clear  --worktree nombre  --new nombre
# ══════════════════════════════════════════════════════════════════
param(
    [string]$Project  = "",
    [string]$Model    = "auto",
    [switch]$Status,
    [switch]$Sync,
    [switch]$Audit,
    [switch]$Clear,
    [string]$Worktree = "",
    [switch]$New
)

$ROOT = "C:\jarvis"
$env:JARVIS_ROOT = $ROOT

# ── Helpers ────────────────────────────────────────────────────────
function RamFreeMB {
    try { return [int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1024) }
    catch { return 4000 }
}

function OllamaModel {
    $ram = RamFreeMB
    if ($ram -lt 2800) {
        Write-Host "  ⚠  RAM free: ${ram}MB → qwen2.5-coder:1.5b" -ForegroundColor Yellow
        return "qwen2.5-coder:1.5b"
    }
    return "qwen2.5-coder:3b"
}

function EnsureOllama {
    $r = ollama list 2>$null
    if (-not $?) {
        Write-Host "  ▶  Starting Ollama..." -ForegroundColor DarkGray
        Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep 2
    }
}

function ActiveProject {
    if ($Project)              { return $Project }
    if ($env:JARVIS_PROJECT)   { return $env:JARVIS_PROJECT }
    $cwd = (Get-Location).Path
    foreach ($n in @("content-automation","hult-finance","leyendas-del-este")) {
        if ($cwd -like "*$n*") { return $n }
    }
    return "jarvis-core"
}

function ChooseModel($proj) {
    if ($Model -eq "local")  { return "ollama:$(OllamaModel)" }
    if ($Model -eq "claude") { return "claude-sonnet-4-5" }
    # Auto: proyectos que necesitan API
    if ($proj -in @("hult-finance","leyendas-del-este")) { return "claude-sonnet-4-5" }
    return "ollama:$(OllamaModel)"
}

# ── --status ───────────────────────────────────────────────────────
if ($Status) {
    $proj  = ActiveProject
    $model = ChooseModel $proj
    $ram   = RamFreeMB
    Write-Host ""
    Write-Host "  JARVIS status" -ForegroundColor Cyan
    Write-Host "  Project  : $proj"
    Write-Host "  Model    : $model"
    Write-Host "  RAM free : ${ram}MB"
    $wt = git -C $ROOT worktree list 2>$null
    Write-Host "  Worktrees:"
    if ($wt) { $wt | % { Write-Host "    $_" -ForegroundColor DarkGray } }
    else      { Write-Host "    (none)" -ForegroundColor DarkGray }
    Write-Host ""
    exit 0
}

# ── --sync ─────────────────────────────────────────────────────────
if ($Sync) {
    Write-Host "  ↓ Syncing..." -ForegroundColor DarkGray
    git -C $ROOT pull --quiet 2>$null
    Write-Host "  ✓ Sync complete" -ForegroundColor Green
}

# ── Resolution ─────────────────────────────────────────────────────
$proj  = ActiveProject
$model = ChooseModel $proj
$env:JARVIS_PROJECT = $proj
$env:JARVIS_MODEL   = $model

Write-Host ""
Write-Host "  ╔══════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║  JARVIS — Claude Code   ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════╝" -ForegroundColor Cyan
Write-Host "  Project  : $proj" -ForegroundColor White
Write-Host "  Model    : $model" -ForegroundColor $(if ($model -like "ollama*") {"Green"} else {"Cyan"})
Write-Host ""

# ── --new ──────────────────────────────────────────────────────────
if ($New -and $Project) {
    $md = "$ROOT\projects\$Project.md"
    if (-not (Test-Path $md)) {
        @"
# $Project — Project Status
Last updated: $(Get-Date -Format 'yyyy-MM-dd')

## Current status
New project.

## Assigned agents
- Main: python-specialist

## Active skills
(none — add in skills-registry/INDEX.md)

## Preferred model
local (qwen2.5-coder:3b)

## Next step
Define scope and first files.

## Specific lessons
(none yet)
"@ | Out-File $md -Encoding utf8
        Write-Host "  ✓ Created: projects\$Project.md" -ForegroundColor Green
    }
}

# ── Ollama si modelo local ──────────────────────────────────────────
if ($model -like "ollama*") { EnsureOllama }

$ollamaModel = $model -replace "ollama:", ""

# ── --worktree ─────────────────────────────────────────────────────
if ($Worktree) {
    if ($model -like "claude*") {
        claude --worktree $Worktree --model $model --add-dir $ROOT
    } else {
        $env:ANTHROPIC_BASE_URL   = "http://localhost:11434"
        $env:ANTHROPIC_AUTH_TOKEN = "ollama"
        claude --worktree $Worktree --model $ollamaModel --add-dir $ROOT
    }
    exit 0
}

# ── Lanzar Claude Code ─────────────────────────────────────────────
$clearFlag = if ($Clear) { @("--clear") } else { @() }

if ($model -like "claude*") {
    claude --model $model --add-dir $ROOT @clearFlag
} else {
    $env:ANTHROPIC_BASE_URL   = "http://localhost:11434"
    $env:ANTHROPIC_AUTH_TOKEN = "ollama"
    claude --model $ollamaModel --add-dir $ROOT @clearFlag
}
