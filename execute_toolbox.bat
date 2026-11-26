@echo off

REM === Start from the directory containing this launcher ===
cd /d "%~dp0"

REM === Launch the stable NiceGUI application ===
REM Interface available at http://localhost:8080
poetry run python -m toolbox_pb.ui.nicegui_app

pause
