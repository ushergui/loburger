@echo off
title LOL BURGUER - Servidor de Gestao
echo ===================================================
echo    Iniciando Servidor LOL BURGUER (Gestao)
echo ===================================================
echo.
cd /d "%~dp0"

echo Iniciar servidor na porta 8000...
echo Acesse no navegador: http://127.0.0.1:8000
echo (Para fechar o servidor, basta fechar esta janela)
echo.

:: Abre o navegador padrao
start "" http://127.0.0.1:8000

:: Executa o servidor Django usando o ambiente virtual venv
.\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000

pause
