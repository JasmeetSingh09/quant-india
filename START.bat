@echo off
REM ============================================================
REM  Quant India — one-click launcher
REM  Double-click this file to start BOTH servers in their own
REM  windows. They stay running until you close those windows.
REM ============================================================

echo Starting backend (FastAPI) ...
start "Quant India - Backend"  cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --port 8000"

echo Starting frontend (React) ...
start "Quant India - Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ============================================================
echo   Both servers are starting in separate windows.
echo.
echo   Open the website at:  http://localhost:5173
echo.
echo   (Backend takes ~30-60s the first time to load FinBERT.)
echo   To STOP: close the two server windows.
echo ============================================================
echo.
pause
