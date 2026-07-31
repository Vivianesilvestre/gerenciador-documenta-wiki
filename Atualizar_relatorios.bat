@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo  Atualizando relatorios da Documenta Wiki (MDS)
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

echo Rodando os 4 relatorios: indicadores, programas, base de dados e ferramentas.
echo Isso pode levar alguns minutos ^(o de indicadores le cerca de 1100 fichas^).
echo.
python relatorios_gerenciamento.py --tudo

echo.
echo ========================================================
echo  Concluido. Abrindo o painel de relatorios no navegador...
echo ========================================================
if exist "painel.html" start "" "painel.html"
echo.
echo Se apareceu algum "falha em ..." acima, foi so naquela ficha especifica -
echo o resto do relatorio saiu normal.

:fim
echo.
echo Pressione qualquer tecla para fechar esta janela...
pause >nul
