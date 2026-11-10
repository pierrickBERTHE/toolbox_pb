@echo off
REM Lance l'application et publie son interface sur http://localhost:8501.
docker compose run --service-ports --rm toolbox
pause
