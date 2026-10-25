@echo off
rem ---------------------------------------------------------------------------
rem  Double-click to start the whole project:
rem    window 1: backend API  (Python)   http://127.0.0.1:8600
rem    window 2: frontend UI  (Next.js)  http://localhost:3000   <- open this
rem  Close both windows (or Ctrl+C in each) to stop. Closing the backend window
rem  also stops the MQTT broker it started.
rem ---------------------------------------------------------------------------
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python environment (first run only)...
  python -m venv .venv || goto :error
  ".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt || goto :error
)
if not exist "frontend\node_modules" (
  echo Installing frontend packages (first run only)...
  pushd frontend
  call npm install || (popd & goto :error)
  popd
)

start "IoT backend - API :8600" powershell -NoExit -ExecutionPolicy Bypass -File backend\scripts\start_backend.ps1
start "IoT frontend - http://localhost:3000" cmd /k "cd /d frontend && npm run dev"
echo Waiting for the servers to start...
timeout /t 10 /nobreak >nul
start "" http://localhost:3000
exit /b 0

:error
echo.
echo Setup failed - see the messages above.
pause
exit /b 1
