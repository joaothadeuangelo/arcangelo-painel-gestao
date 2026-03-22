@echo off
TITLE Arcangelo Painel - Servidor
echo ==========================================
echo      INICIANDO O PAINEL ARCANGELO
echo ==========================================
echo.

:: 1. Entra na pasta do projeto
cd /d "%~dp0"

:: 2. Ativa o ambiente virtual
echo Ativando ambiente virtual...
call venv\Scripts\activate

:: 3. O PULO DO GATO:
:: Inicia um contador "invisivel" de 7 segundos.
:: Quando o tempo acabar, ele abre o navegador.
:: O "/b" faz isso rodar em segundo plano sem travar o resto.
start /b cmd /c "timeout /t 7 /nobreak >nul & start brave http://127.0.0.1:5000"

:: 4. Enquanto o contador roda lá no fundo, o Python começa a carregar IMEDIATAMENTE aqui
echo Iniciando o servidor Flask e conectando ao banco...
python app.py

:: 5. Mantém a janela aberta se der erro
pause