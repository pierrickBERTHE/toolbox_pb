@echo off
REM === Detect Windows user ===
set USERNAME=%USERNAME%

REM === Choose the path according to the user ===
if /I "%USERNAME%"=="pierr" (
    cd /d C:\Users\pierr\VSC_Projects\toolbox_pb
) else (
    echo Utilisateur non reconnu : %USERNAME%
    pause
    exit /b
)

REM === Launch the Python script with the Poetry environment ===
poetry run python toolbox_pb/main.py

pause
