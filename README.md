# Gerenciador Documenta Wiki (MDS)

Ferramenta de gerenciamento da situação de documentação das fichas da
[Documenta Wiki](https://wiki-sagi.mds.gov.br) (MDS/SAGICAD). Lê a wiki pela
API GraphQL do Wiki.js e gera relatórios de quais fichas estão
**documentadas**, **iniciadas** ou **não documentadas** — para Indicadores,
Programas, Base de Dados e Ferramentas.

## O que gera

Para cada um dos 4 tipos de ficha, um `.csv`, um `.jsonl` e um `.html`
(visualizador com busca, filtros de múltipla seleção e exportação em CSV),
mais um `painel.html` com abas reunindo os quatro relatórios.

## Como rodar

Veja o passo a passo completo em [`como_rodar.txt`](como_rodar.txt).

Resumo rápido (Windows): dê duplo clique em `Atualizar_relatorios.bat`.

Resumo rápido (linha de comando):

```bash
pip install -r requirements.txt
export WIKI_TOKEN=seu_token_de_leitura_da_wiki   # ou crie um arquivo wiki_token.txt
python relatorios_gerenciamento.py --tudo
```

Também é possível testar todo o funcionamento **sem rede e sem token**,
usando os arquivos de amostra fictícios inclusos (`exemplo_amostra_*.json`):

```bash
python relatorios_gerenciamento.py --amostra exemplo_amostra_indicadores.json
```

## Estrutura

| Arquivo | Papel |
|---|---|
| `relatorios_gerenciamento.py` | script principal — rode este |
| `gerenciamento.py` | motor de classificação (documentada/iniciada/não documentada) |
| `coletor_wiki.py` | acesso à API GraphQL da wiki |
| `catalogo_html.py` | gera os relatórios `.html` e o `painel.html` |
| `padroes_fichas.json` | textos-padrão de cada campo, por tipo de ficha (editável, sem precisar tocar no código) |
| `exemplo_amostra_*.json` | fichas fictícias para testar tudo offline |

## Segurança

O token de leitura da wiki **não fica no código**. Ele é lido de:

1. Variável de ambiente `WIKI_TOKEN`, ou
2. Arquivo local `wiki_token.txt` (nesta pasta) — **listado no `.gitignore`**,
   nunca deve ser commitado.

Os relatórios gerados com dados reais (`relatorio_*.csv/.jsonl/.html` e
`painel.html`) também estão no `.gitignore`, porque contêm nomes de
servidores responsáveis pela última atualização de cada ficha (dado
pessoal). Só os arquivos de amostra fictícios são versionados.

## Licença / uso

Projeto interno do MDS/SAGICAD. Repositório privado.
