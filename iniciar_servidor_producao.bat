@echo off
title LOL BURGUER - Servidor (Producao)
cd /d "%~dp0"

REM ================== CONFIGURACAO ==================
REM Gere uma chave com:
REM   venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
set LOLBURGUER_SECRET_KEY=COLE_AQUI_UMA_CHAVE_ALEATORIA_E_LONGA
set LOLBURGUER_DEBUG=False
set LOLBURGUER_ALLOWED_HOSTS=localhost,127.0.0.1
set LOLBURGUER_CSRF_TRUSTED_ORIGINS=
REM =================================================

echo Aplicando migracoes...
.\venv\Scripts\python.exe manage.py migrate --noinput

echo Coletando arquivos estaticos...
.\venv\Scripts\python.exe manage.py collectstatic --noinput

echo.
echo Acesse: http://127.0.0.1:8080
start "" http://127.0.0.1:8080
.\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8080

pause
