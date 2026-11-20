# setup_windows.ps1 - one-time setup for the llm-cv pipeline on Windows.
#   powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
# Creates .venv, installs Python packages, builds the LM Roman 10 TTF fonts, and checks
# that Git Bash, MiKTeX and the Claude Desktop CLI are reachable.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== Python venv ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
Write-Host "packages installed"

Write-Host "== LM Roman 10 fonts (TTF) ==" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe install_fonts.py

Write-Host "== Tool check ==" -ForegroundColor Cyan
$gitBash = @("$env:ProgramFiles\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($gitBash) { Write-Host "Git Bash : $gitBash" } else { Write-Warning "Git Bash not found (install Git for Windows)." }

$info = & .\.venv\Scripts\python.exe -c "import config; print(config.find_miktex_bin() or ''); print(config.find_claude_cli() or '')"
$miktex = $info[0]; $claude = $info[1]
if ($miktex) { Write-Host "MiKTeX   : $miktex" } else { Write-Warning "MiKTeX pdflatex not found." }
if ($claude) {
    Write-Host "Claude   : $claude"
    & $claude auth status
    Write-Host "If it says you are not logged in, run:  & '$claude' auth login" -ForegroundColor Yellow
} else { Write-Warning "claude.exe not found - open the Claude Desktop app once, or set LLM_CV_CLAUDE_CLI." }

Write-Host "`nDone. Run the pipeline with:  .\run_pipeline.cmd --help" -ForegroundColor Green
