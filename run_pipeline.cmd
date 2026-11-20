@echo off
rem run_pipeline.cmd - run the Git Bash pipeline (run_pipeline.sh) from cmd.exe / PowerShell.
rem Usage:  run_pipeline.cmd --file jd.txt --render latex --style us --source "Cold Apply" --language English --stuffing none --score-boost auto
setlocal
set "BASH_EXE="
for %%P in ("%ProgramFiles%\Git\bin\bash.exe" "%ProgramFiles(x86)%\Git\bin\bash.exe" "%LOCALAPPDATA%\Programs\Git\bin\bash.exe") do (
    if exist %%P if not defined BASH_EXE set "BASH_EXE=%%~P"
)
if not defined BASH_EXE (
    echo [error] Git Bash not found. Install Git for Windows ^(https://git-scm.com/download/win^) and retry.
    exit /b 1
)
"%BASH_EXE%" "%~dp0run_pipeline.sh" %*
exit /b %ERRORLEVEL%
