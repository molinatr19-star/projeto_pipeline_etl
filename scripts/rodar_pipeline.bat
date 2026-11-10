@echo off
rem Roda o pipeline completo. Usado pelo Agendador de Tarefas do Windows
rem (registre com scripts\agendar_tarefa_windows.ps1).
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
echo ===== %DATE% %TIME% >> "logs\agendador.log"
".venv\Scripts\pipeline-etl.exe" >> "logs\agendador.log" 2>&1
exit /b %ERRORLEVEL%
