"""
catalogo_html.py — renderiza um catálogo (documentos ou indicadores) como uma
página HTML autocontida: tabela com busca em tempo real, filtros multi-seleção
com busca por texto, links clicáveis e exportação da visão atual para CSV.
Sem dependências externas; abre em qualquer navegador.

Usado pelos relatórios de gerenciamento (relatorios_gerenciamento.py) e pelos
catálogos originais (coletor_wiki.py).
"""
import html
import json
from datetime import datetime

NAVY = "#1F3864"
GOLD = "#BF8F00"


def _esc(v):
    return html.escape("" if v is None else str(v))


def _celula(valor, tipo):
    """Renderiza uma célula conforme o tipo da coluna."""
    if tipo == "link":
        # valor = (texto, url) ou lista de (texto, url)
        pares = valor if isinstance(valor, list) else [valor]
        out = []
        for texto, url in pares:
            if url:
                out.append(f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(texto)}</a>')
        return " · ".join(out) or '<span class="vazio">—</span>'
    if tipo == "tags":
        itens = valor or []
        if not itens:
            return '<span class="vazio">—</span>'
        return "".join(f'<span class="tag">{_esc(t)}</span>' for t in itens)
    if tipo == "long":
        txt = _esc(valor)
        return f'<span class="long" title="{txt}">{txt}</span>'
    return _esc(valor)


def _texto_busca(linha, colunas):
    """Concatena tudo que é pesquisável de uma linha (para o filtro por texto)."""
    partes = []
    for col in colunas:
        v = linha.get(col["key"])
        if isinstance(v, list):
            for item in v:
                partes.append(str(item[0]) if isinstance(item, tuple) else str(item))
        elif v is not None:
            partes.append(str(v))
    return " ".join(partes).lower()


_COR_SITUACAO = {
    "documentada": "#2E7D32",
    "iniciada": GOLD,
    "não documentada": "#B03A2E",
    "sintaxe indisponível": "#6C757D",
    "sem ferramenta vinculada": "#9AA5B1",
}


def _cor_barra(label):
    return _COR_SITUACAO.get(str(label).strip().lower(), NAVY)


def render_dashboard(path, *, titulo="Painel Geral · Documenta Wiki (MDS)",
                      gerado_em=None, cards=None, graficos=None):
    """
    Gera uma página de dashboard: cards com números grandes + gráficos de
    barra horizontal (sem depender de nenhuma biblioteca externa — cada
    barra é só uma <div> com largura proporcional, calculada em Python).

    cards:    lista de {"label": "Indicadores", "valor": 1121}
    graficos: lista de {"titulo": "...", "itens": [(label, valor), ...]}
              "itens" já deve vir na ordem em que você quer exibir.
    """
    cards = cards or []
    graficos = graficos or []
    gerado = gerado_em or datetime.now().strftime("%d/%m/%Y %H:%M")

    cards_html = "".join(f"""
    <div class="card">
      <div class="card-valor">{c['valor']:,}</div>
      <div class="card-label">{_esc(c['label'])}</div>
    </div>""".replace(",", ".") for c in cards)

    graficos_html = []
    for g in graficos:
        itens = g.get("itens") or []
        maximo = max((v for _, v in itens), default=0) or 1
        total = sum(v for _, v in itens)
        barras = "".join(f"""
        <div class="barra-linha">
          <div class="barra-rotulo">{_esc(label)}</div>
          <div class="barra-trilha">
            <div class="barra-fill" style="width:{(v / maximo * 100):.1f}%; background:{_cor_barra(label)};"></div>
          </div>
          <div class="barra-valor">{v:,}</div>
        </div>""".replace(",", ".") for label, v in itens)
        if not itens:
            barras = '<p class="sem-dados">Sem dados ainda — gere o relatório correspondente.</p>'
        graficos_html.append(f"""
    <div class="grafico">
      <h3>{_esc(g.get('titulo', ''))}{f' <span class="grafico-total">({total:,} no total)</span>'.replace(",", ".") if total else ''}</h3>
      {barras}
    </div>""")

    doc = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(titulo)}</title>
<style>
  :root {{ --navy:{NAVY}; --gold:{GOLD}; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:Arial,Helvetica,sans-serif; margin:0; color:#222; background:#f4f5f7; }}
  header {{ background:var(--navy); color:#fff; padding:20px 28px; }}
  header h1 {{ margin:0 0 4px; font-size:20px; }}
  header p {{ margin:0; font-size:13px; opacity:.9; }}
  .wrap {{ padding:22px 28px 40px; }}
  .cards {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:24px; }}
  .card {{ background:#fff; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,.08);
           padding:18px 26px; min-width:160px; flex:1; text-align:center; }}
  .card-valor {{ font-size:36px; font-weight:bold; color:var(--navy); line-height:1.1; }}
  .card-label {{ font-size:13px; color:#666; margin-top:4px; }}
  .graficos {{ display:flex; flex-direction:column; gap:18px; }}
  .grafico {{ background:#fff; border-radius:10px; box-shadow:0 1px 3px rgba(0,0,0,.08); padding:18px 24px; }}
  .grafico h3 {{ margin:0 0 14px; font-size:15px; color:var(--navy); }}
  .grafico-total {{ font-size:12px; color:#888; font-weight:normal; }}
  .barra-linha {{ display:flex; align-items:center; gap:10px; margin-bottom:9px; font-size:13px; }}
  .barra-rotulo {{ width:220px; flex:none; color:#333; text-align:right; }}
  .barra-trilha {{ flex:1; background:#eef1f6; border-radius:5px; height:16px; overflow:hidden; }}
  .barra-fill {{ height:100%; border-radius:5px; min-width:2px; }}
  .barra-valor {{ width:50px; flex:none; color:#555; font-weight:bold; }}
  .sem-dados {{ color:#999; font-size:13px; margin:0; }}
  @media (max-width: 680px) {{ .barra-rotulo {{ width:120px; font-size:12px; }} }}
</style></head>
<body>
<header>
  <h1>{_esc(titulo)}</h1>
  <p>Visão geral · gerado em {_esc(gerado)}</p>
</header>
<div class="wrap">
  <div class="cards">{cards_html}</div>
  <div class="graficos">{''.join(graficos_html)}</div>
</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path


def render_painel(path, relatorios, *, titulo="Documenta Wiki (MDS) · Painel de Relatórios"):
    """
    Gera uma página única com abas no topo; cada aba abre, num iframe abaixo,
    o relatório .html já gerado (sem alterar nada dentro dele).
    relatorios: lista de {"key","label","arquivo"} — só entram os que você
                quer oferecer como aba (o chamador decide quais existem).
    """
    abas = "".join(
        f'<button type="button" class="aba" data-arquivo="{_esc(r["arquivo"])}">{_esc(r["label"])}</button>'
        for r in relatorios)
    primeiro = relatorios[0]["arquivo"] if relatorios else ""
    aviso = "" if relatorios else '<p class="aviso">Nenhum relatório encontrado nesta pasta ainda. Rode o gerador primeiro.</p>'
    doc = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(titulo)}</title>
<style>
  :root {{ --navy:{NAVY}; --gold:{GOLD}; }}
  * {{ box-sizing:border-box; }}
  html, body {{ margin:0; height:100%; font-family:Arial,Helvetica,sans-serif; background:#f4f5f7; }}
  header {{ background:var(--navy); color:#fff; padding:16px 28px; }}
  header h1 {{ margin:0; font-size:19px; }}
  nav {{ background:#fff; border-bottom:1px solid #dcdfe4; padding:0 28px; display:flex; gap:4px; }}
  .aba {{ padding:12px 18px; font-size:14px; border:none; background:none; cursor:pointer;
          color:#555; border-bottom:3px solid transparent; }}
  .aba:hover {{ color:var(--navy); }}
  .aba.ativa {{ color:var(--navy); font-weight:bold; border-bottom-color:var(--gold); }}
  .aviso {{ padding:24px 28px; color:#888; }}
  #frame {{ display:block; width:100%; border:none; height:calc(100vh - 118px); background:#fff; }}
</style></head>
<body>
<header><h1>{_esc(titulo)}</h1></header>
<nav>{abas}</nav>
{aviso}
<iframe id="frame" src="{_esc(primeiro)}"></iframe>
<script>
  const abas = Array.from(document.querySelectorAll('.aba'));
  const frame = document.getElementById('frame');
  function abrir(arquivo, semHash) {{
    const btn = abas.find(b => b.dataset.arquivo === arquivo);
    if (!btn) return;
    abas.forEach(b => b.classList.toggle('ativa', b === btn));
    frame.src = arquivo;
    if (!semHash) location.hash = encodeURIComponent(arquivo);
  }}
  abas.forEach(b => b.addEventListener('click', () => abrir(b.dataset.arquivo)));
  const doHash = decodeURIComponent((location.hash || '').replace('#', ''));
  if (doHash && abas.some(b => b.dataset.arquivo === doHash)) {{
    abrir(doHash, true);
  }} else if (abas.length) {{
    abrir(abas[0].dataset.arquivo, true);
  }}
</script>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path


def render(path, *, titulo, subtitulo, fonte_url, total_origem, colunas, linhas,
           filtros=None, filtro_labels=None, filtro_dependencias=None):
    """
    colunas: lista de {"key","label","tipo"}  tipo in {text,link,tags,long}
    linhas:  lista de dicts com os valores por key
    filtros: lista de keys que viram um filtro de MÚLTIPLA seleção com busca.
             Pode ser uma key de coluna (text/tags) ou um campo só-para-filtro
             presente nas linhas (ex.: "programa_nome" mesmo que a coluna
             mostre outra coisa). A ORDEM da lista é a ordem de exibição.
    filtro_labels: {key: rótulo} para nomear filtros que não são coluna.
    filtro_dependencias: {key_filho: [key_pai, ...]} — quando o(s) filtro(s)
             pai(s) tiver(em) alguma opção marcada, a lista de opções do
             filtro filho é restrita às que ocorrem nas linhas que combinam
             com a seleção do(s) pai(s) (e opções que deixam de valer são
             desmarcadas automaticamente). Ex.: {"programa": ["status_programa"]}
             faz a lista de programas depender do status selecionado.
    """
    filtros = filtros or []
    filtro_labels = filtro_labels or {}
    filtro_dependencias = filtro_dependencias or {}
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")
    mostrados = len(linhas)
    cobertura = ""
    if total_origem is not None and mostrados != total_origem:
        cobertura = (f' <strong style="color:{GOLD}">'
                     f'(amostra: {mostrados} de {total_origem} — rode o script '
                     f'com acesso à rede para o acervo completo)</strong>')
    elif total_origem is not None:
        cobertura = f" ({mostrados} de {total_origem})"

    # opções de cada filtro (multi-seleção)
    opcoes = {}
    for fk in filtros:
        vals = set()
        for ln in linhas:
            v = ln.get(fk)
            if isinstance(v, list):
                vals.update(str(x) for x in v if x)
            elif v:
                vals.add(str(v))
        opcoes[fk] = sorted(vals, key=lambda s: s.lower())

    # para filtros filhos (filtro_dependencias): para cada opção do filho,
    # quais valores de cada filtro pai aparecem junto nas mesmas linhas
    dependencia_valores = {}
    for fk_filho, pais in filtro_dependencias.items():
        mapa = {}
        for ln in linhas:
            v = ln.get(fk_filho)
            opcoes_linha = [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])
            for o in opcoes_linha:
                entry = mapa.setdefault(o, {})
                for pk in pais:
                    pv = ln.get(pk)
                    valores_pai = [str(x) for x in pv] if isinstance(pv, list) else ([str(pv)] if pv else [])
                    entry.setdefault(pk, set()).update(valores_pai)
        dependencia_valores[fk_filho] = mapa

    label = {c["key"]: c["label"] for c in colunas}

    # cabeçalho da tabela
    ths = "".join(f"<th>{_esc(c['label'])}</th>" for c in colunas)

    # linhas
    trs = []
    for ln in linhas:
        tds = "".join(f"<td data-col=\"{c['key']}\">{_celula(ln.get(c['key']), c['tipo'])}</td>"
                      for c in colunas)
        attrs_filtro = "".join(
            f' data-f-{fk}="{_esc("|".join(map(str, ln.get(fk))) if isinstance(ln.get(fk), list) else ln.get(fk) or "")}"'
            for fk in filtros)
        trs.append(f'<tr data-busca="{_esc(_texto_busca(ln, colunas))}"{attrs_filtro}>{tds}</tr>')

    # widgets de filtro (multi-seleção com busca por texto, sem rolar a página —
    # a lista tem rolagem própria dentro do painel, que abre por cima da tabela)
    filtros_html = []
    for fk in filtros:
        nome = label.get(fk) or filtro_labels.get(fk) or fk
        pais_deste = filtro_dependencias.get(fk, [])

        def _item_html(o, _fk=fk, _pais=pais_deste):
            attrs_pai = "".join(
                f' data-pai-{pk}="{_esc("|".join(sorted(dependencia_valores.get(_fk, {}).get(o, {}).get(pk, []))))}"'
                for pk in _pais)
            return f'<label class="ms-item"{attrs_pai}><input type="checkbox" value="{_esc(o)}">{_esc(o)}</label>'

        itens = "".join(_item_html(o) for o in opcoes[fk])
        filtros_html.append(f"""
  <div class="filtro-ms" data-filtro="{fk}">
    <button type="button" class="ms-botao">{_esc(nome)} <span class="ms-contagem"></span><span class="ms-seta">▾</span></button>
    <div class="ms-painel oculto">
      <div class="ms-cabecalho">
        <strong>{_esc(nome)}</strong>
        <button type="button" class="ms-fechar" title="Fechar" aria-label="Fechar">✕</button>
      </div>
      <input type="text" class="ms-busca" placeholder="Buscar {_esc(nome.lower())}...">
      <div class="ms-lista">{itens or '<span class="ms-vazio">sem opções</span>'}</div>
      <div class="ms-acoes">
        <button type="button" class="ms-limpar">Limpar seleção</button>
        <button type="button" class="ms-aplicar">Aplicar e fechar</button>
      </div>
    </div>
  </div>""")

    doc = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(titulo)}</title>
<style>
  :root {{ --navy:{NAVY}; --gold:{GOLD}; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:Arial,Helvetica,sans-serif; margin:0; color:#222; background:#f4f5f7; }}
  header {{ background:var(--navy); color:#fff; padding:20px 28px; }}
  header h1 {{ margin:0 0 4px; font-size:20px; }}
  header p {{ margin:0; font-size:13px; opacity:.9; }}
  header a {{ color:#cfe0ff; }}
  .barra {{ position:sticky; top:0; background:#fff; border-bottom:1px solid #dcdfe4;
            padding:12px 28px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; z-index:30; }}
  .barra input[type=search] {{ flex:1; min-width:220px; padding:8px 12px; font-size:14px;
            border:1px solid #c4c8ce; border-radius:6px; }}
  #contador {{ font-size:13px; color:#666; margin-left:auto; white-space:nowrap; }}
  #baixar-csv {{ padding:7px 14px; font-size:13px; border:1px solid var(--navy); border-radius:6px;
            background:var(--navy); color:#fff; cursor:pointer; white-space:nowrap; }}
  #baixar-csv:hover {{ opacity:.9; }}
  .wrap {{ padding:18px 28px 40px; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; font-size:13px;
           box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  th {{ background:#eef1f6; color:var(--navy); text-align:left; padding:10px 12px;
        position:sticky; top:57px; border-bottom:2px solid var(--navy); }}
  td {{ padding:9px 12px; border-bottom:1px solid #eceef1; vertical-align:top; }}
  tr:hover td {{ background:#fafbfd; }}
  .tag {{ display:inline-block; background:#eef1f6; color:var(--navy); border:1px solid #d6dce8;
          border-radius:10px; padding:1px 8px; margin:1px 3px 1px 0; font-size:11px; }}
  .long {{ display:block; max-width:520px; }}
  .vazio {{ color:#bbb; }}
  a {{ color:#1a56b8; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
  .oculto {{ display:none; }}

  .filtro-ms {{ position:relative; }}
  .ms-botao {{ padding:7px 10px; font-size:13px; border:1px solid #c4c8ce; border-radius:6px;
               background:#fff; cursor:pointer; color:#333; }}
  .ms-botao:hover {{ border-color:var(--navy); }}
  .ms-contagem {{ display:inline-block; background:var(--navy); color:#fff; border-radius:9px;
               padding:0 6px; font-size:11px; margin:0 3px; }}
  .ms-contagem:empty {{ display:none; }}
  .ms-seta {{ font-size:10px; color:#888; }}
  .ms-painel {{ position:absolute; top:calc(100% + 4px); left:0; width:260px; background:#fff;
               border:1px solid #c4c8ce; border-radius:8px; box-shadow:0 6px 18px rgba(0,0,0,.15);
               padding:8px; display:flex; flex-direction:column; gap:6px; }}
  .ms-busca {{ padding:6px 8px; font-size:13px; border:1px solid #d6dce8; border-radius:5px; width:100%; }}
  .ms-lista {{ max-height:220px; overflow-y:auto; display:flex; flex-direction:column; }}
  .ms-item {{ font-size:13px; padding:4px 4px; display:flex; align-items:center; gap:7px; cursor:pointer;
               border-radius:4px; }}
  .ms-item:hover {{ background:#f2f4f8; }}
  .ms-item input {{ flex:none; }}
  .ms-item.ms-filtrado {{ display:none; }}
  .ms-item.ms-fora-do-pai {{ display:none; }}
  .ms-vazio {{ font-size:12px; color:#999; padding:4px; }}
  .ms-cabecalho {{ display:flex; align-items:center; justify-content:space-between; gap:8px;
               font-size:13px; color:var(--navy); }}
  .ms-fechar {{ background:none; border:none; cursor:pointer; font-size:14px; color:#888; line-height:1;
               padding:2px 4px; border-radius:4px; }}
  .ms-fechar:hover {{ background:#f2f4f8; color:#333; }}
  .ms-acoes {{ display:flex; justify-content:space-between; align-items:center; gap:8px;
               border-top:1px solid #eceef1; padding-top:6px; }}
  .ms-limpar {{ font-size:12px; background:none; border:none; color:var(--navy); cursor:pointer;
               text-decoration:underline; padding:0; }}
  .ms-aplicar {{ font-size:12px; background:var(--navy); color:#fff; border:none; border-radius:5px;
               padding:5px 10px; cursor:pointer; }}
  .ms-painel.oculto {{ display:none !important; }}
</style></head>
<body>
<header>
  <h1>{_esc(titulo)}</h1>
  <p>{subtitulo}{cobertura} · gerado em {gerado} · fonte: <a href="{_esc(fonte_url)}" target="_blank" rel="noopener">{_esc(fonte_url)}</a></p>
</header>
<div class="barra">
  <input type="search" id="busca" placeholder="Buscar em todo o catálogo...">
  {''.join(filtros_html)}
  <button type="button" id="baixar-csv">Baixar CSV</button>
  <span id="contador"></span>
</div>
<div class="wrap">
  <table id="tab"><thead><tr>{ths}</tr></thead><tbody>
  {''.join(trs)}
  </tbody></table>
</div>
<script>
  const tbody = document.querySelector('#tab tbody');
  const linhas = Array.from(tbody.querySelectorAll('tr'));
  const busca = document.getElementById('busca');
  const contador = document.getElementById('contador');
  const painelFiltros = Array.from(document.querySelectorAll('.filtro-ms'));

  function selecaoDoFiltro(painel) {{
    return Array.from(painel.querySelectorAll('.ms-item input:checked')).map(i => i.value);
  }}

  function aplicar() {{
    const termo = busca.value.trim().toLowerCase();
    const fs = painelFiltros.map(p => [p.dataset.filtro, selecaoDoFiltro(p)]);
    let visiveis = 0;
    for (const tr of linhas) {{
      let ok = !termo || tr.dataset.busca.includes(termo);
      if (ok) for (const [k, selecionados] of fs) {{
        if (!selecionados.length) continue;
        const valoresLinha = (tr.getAttribute('data-f-' + k) || '').split('|');
        if (!selecionados.some(v => valoresLinha.includes(v))) {{ ok = false; break; }}
      }}
      tr.classList.toggle('oculto', !ok);
      if (ok) visiveis++;
    }}
    contador.textContent = visiveis + ' de ' + linhas.length + ' registros';
  }}

  busca.addEventListener('input', aplicar);

  const todasAsCaixas = painelFiltros.map(p => p.querySelector('.ms-painel'));
  function fecharTodos(exceto) {{
    todasAsCaixas.forEach(c => {{ if (c !== exceto) c.classList.add('oculto'); }});
  }}

  // widgets de multi-seleção com busca: abrir/fechar, contagem, busca interna, limpar
  painelFiltros.forEach(painel => {{
    const botao = painel.querySelector('.ms-botao');
    const caixa = painel.querySelector('.ms-painel');
    const fechar = painel.querySelector('.ms-fechar');
    const buscaFiltro = painel.querySelector('.ms-busca');
    const itens = Array.from(painel.querySelectorAll('.ms-item'));
    const contagem = painel.querySelector('.ms-contagem');
    const limpar = painel.querySelector('.ms-limpar');
    const aplicarBtn = painel.querySelector('.ms-aplicar');

    botao.addEventListener('click', (e) => {{
      e.stopPropagation();
      const estavaAberto = !caixa.classList.contains('oculto');
      fecharTodos(caixa);
      caixa.classList.toggle('oculto', estavaAberto);
    }});

    fechar.addEventListener('click', (e) => {{
      e.stopPropagation();
      caixa.classList.add('oculto');
    }});

    aplicarBtn.addEventListener('click', (e) => {{
      e.stopPropagation();
      caixa.classList.add('oculto');
      aplicar();
    }});

    buscaFiltro.addEventListener('input', () => {{
      const t = buscaFiltro.value.trim().toLowerCase();
      itens.forEach(it => it.classList.toggle('ms-filtrado', t && !it.textContent.toLowerCase().includes(t)));
    }});

    itens.forEach(it => {{
      const chk = it.querySelector('input');
      chk.addEventListener('change', () => {{
        const n = itens.filter(x => x.querySelector('input').checked).length;
        contagem.textContent = n ? n : '';
        aplicar();
      }});
    }});

    limpar.addEventListener('click', (e) => {{
      e.stopPropagation();
      itens.forEach(it => {{ it.querySelector('input').checked = false; }});
      contagem.textContent = '';
      aplicar();
    }});

    caixa.addEventListener('click', (e) => e.stopPropagation());
    caixa.addEventListener('keydown', (e) => {{ if (e.key === 'Escape') caixa.classList.add('oculto'); }});
  }});

  // filtros em cascata: a lista de opções de um filtro filho é restrita pela
  // seleção feita em seu(s) filtro(s) pai (ex.: Programa depende do Status
  // do programa selecionado); opções que deixam de valer são desmarcadas.
  const DEPENDENCIAS = {json.dumps(filtro_dependencias, ensure_ascii=False)};
  Object.entries(DEPENDENCIAS).forEach(([filhoKey, paisKeys]) => {{
    const painelFilho = painelFiltros.find(p => p.dataset.filtro === filhoKey);
    if (!painelFilho) return;
    const itensFilho = Array.from(painelFilho.querySelectorAll('.ms-item'));
    const contagemFilho = painelFilho.querySelector('.ms-contagem');

    function atualizarFilho() {{
      const selecaoPorPai = paisKeys.map(pk => {{
        const painelPai = painelFiltros.find(p => p.dataset.filtro === pk);
        return painelPai ? selecaoDoFiltro(painelPai) : [];
      }});
      const algumPaiComSelecao = selecaoPorPai.some(s => s.length);
      let mudouSelecao = false;
      itensFilho.forEach(it => {{
        let visivel = true;
        if (algumPaiComSelecao) {{
          visivel = paisKeys.every((pk, i) => {{
            const sel = selecaoPorPai[i];
            if (!sel.length) return true;
            const valoresItem = (it.getAttribute('data-pai-' + pk) || '').split('|');
            return sel.some(v => valoresItem.includes(v));
          }});
        }}
        it.classList.toggle('ms-fora-do-pai', !visivel);
        const chk = it.querySelector('input');
        if (!visivel && chk.checked) {{ chk.checked = false; mudouSelecao = true; }}
      }});
      const n = itensFilho.filter(it => it.querySelector('input').checked).length;
      contagemFilho.textContent = n ? n : '';
      if (mudouSelecao) aplicar();
    }}

    paisKeys.forEach(pk => {{
      const painelPai = painelFiltros.find(p => p.dataset.filtro === pk);
      if (!painelPai) return;
      painelPai.querySelectorAll('.ms-item input').forEach(chk => chk.addEventListener('change', atualizarFilho));
      const limparPai = painelPai.querySelector('.ms-limpar');
      if (limparPai) limparPai.addEventListener('click', atualizarFilho);
    }});
    atualizarFilho();
  }});

  document.addEventListener('click', () => fecharTodos(null));
  document.addEventListener('keydown', (e) => {{ if (e.key === 'Escape') fecharTodos(null); }});

  // baixar CSV com os registros visíveis (respeita busca + filtros aplicados)
  document.getElementById('baixar-csv').addEventListener('click', () => {{
    const ths = Array.from(document.querySelectorAll('#tab thead th')).map(th => th.textContent);
    const linhasVisiveis = linhas.filter(tr => !tr.classList.contains('oculto'));
    function csvEsc(v) {{
      const s = (v ?? '').toString().replace(/\\s+/g, ' ').trim();
      return '"' + s.replace(/"/g, '""') + '"';
    }}
    const corpo = linhasVisiveis.map(tr =>
      Array.from(tr.children).map(td => csvEsc(td.textContent)).join(','));
    const csv = [ths.map(csvEsc).join(',')].concat(corpo).join('\\r\\n');
    const blob = new Blob(['\\ufeff' + csv], {{type: 'text/csv;charset=utf-8;'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = document.title.replace(/[^\\w\\-]+/g, '_') + '.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }});

  aplicar();
</script>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path
