@echo off
REM Lance l'application et publie son interface NiceGUI sur http://localhost:8080.
docker compose run --service-ports --rm toolbox
pause
