@echo off
REM Adjust this path if your project moves
set BASE=D:\Project\Business-Management-System\

cd /d "%BASE%"

REM ── Activate virtualenv and install requirements ──────────────
echo.
echo ============================================
echo   Activating virtual environment...
echo ============================================
call "%BASE%env\Scripts\activate.bat"

echo.
echo ============================================
echo   Installing requirements.txt...
echo ============================================
pip install -r "%BASE%requirements.txt"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: pip install failed. Fix the issue above and try again.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Requirements installed successfully.
echo ============================================
echo.

REM ── Use PowerShell to listen for keys and call run_server.py ──
powershell -NoExit -Command ^
"$base='%BASE%';" ^
"$py = Join-Path $base 'env\\Scripts\\python.exe';" ^
"if (-not (Test-Path $py)) { $py = 'python' }" ^
"$runner = Join-Path $base 'run_server.py';" ^
"Write-Host '';" ^
"Write-Host '  Press INS to START, END to STOP, ESC to exit.' -ForegroundColor Cyan;" ^
"Write-Host '';" ^
"while ($true) {" ^
"  $key = [Console]::ReadKey($true);" ^
"  switch ($key.Key) {" ^
"    'Insert' { Write-Host 'Starting server on http://127.0.0.1:8000 ...'; & $py $runner start }" ^
"    'End'    { Write-Host 'Stopping server ...'; & $py $runner stop }" ^
"    'Escape' { Write-Host 'Exiting...'; break }" ^
"  }" ^
"}"
