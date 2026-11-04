@echo off
REM Final Whistle - start backend + frontend for local development.
REM Double-click this file, or run "dev" from a terminal in this folder.
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo [setup] Creating backend virtual environment...
  python -m venv backend\.venv || goto :error
  backend\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt || goto :error
)
if not exist "frontend\node_modules" (
  echo [setup] Installing frontend packages...
  pushd frontend & call npm install & popd
)

start "Final Whistle - backend" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
start "Final Whistle - frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo Waiting for servers to start...
timeout /t 5 /nobreak >nul
start "" http://localhost:5173
echo.
echo Running. Close the two server windows to stop.
echo   Dashboard: http://localhost:5173
echo   API docs:  http://localhost:8000/docs
exit /b 0

:error
echo Setup failed - see messages above.
pause
exit /b 1
