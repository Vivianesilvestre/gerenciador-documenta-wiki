@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo  Atualizando o relatorio de INDICADORES (mais demorado)
echo ========================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERRO: o comando "python" nao foi encontrado neste computador.
    echo Instale o Python em https://www.python.org/downloads/ e marque a
    echo opcao "Add python.exe to PATH" durante a instalacao. Depois rode
    echo este arquivo de novo.
    goto fim
)

python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencia necessaria ^(requests^)...
    python -m pip install requests
    echo.
)

python relatorios_gerenciamento.py

echo.
echo ========================================================
echo  Concluido. Abrindo o painel de relatorios no navegador...
echo ========================================================
if exist "painel.html" start "" "painel.html"

:fim
echo.
echo Pressione qualquer tecla para fechar esta janela...
pause >nul
