@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo  Atualizando relatorios e publicando no site
echo ========================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERRO: o comando "python" nao foi encontrado neste computador.
    goto fim
)

where git >nul 2>&1
if errorlevel 1 (
    echo ERRO: o comando "git" nao foi encontrado neste computador.
    goto fim
)

if not exist "site_relatorios\.git" (
    echo ERRO: a pasta site_relatorios ainda nao esta configurada com o
    echo repositorio do site. Siga o passo a passo enviado antes de usar
    echo este atalho.
    goto fim
)

echo Passo 1/3: gerando os 4 relatorios com dados atuais da wiki...
python relatorios_gerenciamento.py --tudo
if errorlevel 1 (
    echo ERRO ao gerar os relatorios. Nada foi publicado.
    goto fim
)

echo.
echo Passo 2/3: copiando os arquivos para a pasta do site...
copy /y "relatorio_indicadores.html" "site_relatorios\relatorio_indicadores.html" >nul
copy /y "relatorio_programas.html" "site_relatorios\relatorio_programas.html" >nul
copy /y "relatorio_base_dados.html" "site_relatorios\relatorio_base_dados.html" >nul
copy /y "relatorio_ferramentas.html" "site_relatorios\relatorio_ferramentas.html" >nul
copy /y "painel.html" "site_relatorios\index.html" >nul

echo.
echo Passo 3/3: enviando para o GitHub (a Cloudflare publica sozinha em 1-2 min)...
cd site_relatorios
git add -A
git commit -m "Atualizacao automatica dos relatorios"
if errorlevel 1 (
    echo Nada novo para publicar ^(relatorios sem mudanca desde a ultima vez^).
    goto fim
)
git push
if errorlevel 1 (
    echo ERRO ao enviar para o GitHub. Verifique sua conexao/login e tente
    echo rodar "git push" manualmente dentro da pasta site_relatorios.
    goto fim
)

echo.
echo ========================================================
echo  Publicado! Em 1-2 minutos o site estara atualizado.
echo ========================================================

:fim
echo.
echo Pressione qualquer tecla para fechar esta janela...
pause >nul
