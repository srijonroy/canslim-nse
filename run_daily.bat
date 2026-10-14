@echo off
rem Daily CAN SLIM scan (scheduled 18:30 IST). Research only.
cd /d C:\Project\asd

rem Screener + Fyers login run through the debuggable Chrome profile; start it if it is not up.
curl -s http://127.0.0.1:9222/json/version >nul 2>&1
if errorlevel 1 (
  start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\Project\asd\.browser_profile https://www.screener.in/
  ping -n 16 127.0.0.1 >nul
)

rem 1) prices, rules, report, database, paper portfolio (Fyers logs in by TOTP if .env has it, else in Chrome)
python -u -m canslim.daily >> data\daily_console.log 2>&1
if errorlevel 1 (
  echo Scan failed - see C:\Project\asd\data\daily.log
  start "" notepad C:\Project\asd\data\daily.log
  exit /b 1
)

rem 2) research briefs for new / stale names on the list (Claude Code headless, max 3 a day).
rem    A failure here never affects the scan above.
python -u -m canslim.autobrief >> data\autobrief_console.log 2>&1

rem 3) Saturdays: refresh the comparison of other frameworks (app page "Other frameworks"; ~15 min).
for /f %%d in ('powershell -NoProfile -Command "(Get-Date).DayOfWeek"') do set DOW=%%d
if "%DOW%"=="Saturday" python -u -m canslim.fwtest > data\tune\frameworks\run.log 2>&1

start "" C:\Project\asd\data\reports\latest.html
