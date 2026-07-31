"""
relatorios_gerenciamento.py — Ferramenta de Gerenciamento de Indicadores da
Documenta Wiki (MDS)

Gera os relatórios de situação de documentação:
  1) Fichas de INDICADORES  (modelo antigo/novo, situação, sintaxe, status)
  2) Fichas de PROGRAMAS
  3) Fichas de BASE DE DADOS
  4) Fichas de FERRAMENTAS (bônus, mesma lógica)

Depende de (mesma pasta):
  coletor_wiki.py     -> acesso à API GraphQL da wiki (token, GET de páginas)
  catalogo_html.py    -> renderizador do .html de cada relatório
  gerenciamento.py    -> motor de classificação (documentada/iniciada/não documentada)
  padroes_fichas.json -> textos-padrão de cada campo, por tipo de ficha

Uso:
    export WIKI_TOKEN=...                        # se necessário (ver coletor_wiki.py)
    python relatorios_gerenciamento.py                  # relatório de indicadores
    python relatorios_gerenciamento.py --programas       # relatório de programas
    python relatorios_gerenciamento.py --bd              # relatório de base de dados
    python relatorios_gerenciamento.py --ferramentas     # relatório de ferramentas
    python relatorios_gerenciamento.py --tudo            # os quatro de uma vez
    python relatorios_gerenciamento.py --amostra arq.json               # teste offline (indicadores)
    python relatorios_gerenciamento.py --programas --amostra arq.json   # idem, programas
    python relatorios_gerenciamento.py --painel         # só reconstrói painel.html (abas),
                                                          # a partir dos relatórios já existentes
    python relatorios_gerenciamento.py --dashboard      # só reconstrói dashboard.html (cards e
                                                          # gráficos), a partir dos .jsonl já existentes

Todo comando acima também atualiza painel.html no final — a página com abas
que abre cada relatório existente na pasta num iframe (veja como_rodar.txt).

Ver como_rodar.txt para o passo a passo completo.
"""
import csv
import json
import os
import re
import sys
from collections import Counter

import catalogo_html
import coletor_wiki as cw
import gerenciamento as gm

CFG = gm.carregar_padroes()
BASE = cw.BASE

# ======================= códigos da ficha nova de indicador =======================
CODIGOS_FICHA_NOVA = ["A1", "A2", "A3", "A4", "A5", "B6", "B7", "B8", "B9",
                      "C10", "C11", "C12", "C13", "C14", "D15", "D16", "D17", "D18",
                      "E19", "E20", "E21", "E22", "F23"]

# rótulos (cabeçalhos) da ficha de PROGRAMA — regex casa o PREFIXO do cabeçalho
ROTULOS_PROGRAMA = [
    ("descricao", r"descri[cç][aã]o e objetivo geral"),
    ("publico_alvo", r"p[uú]blico-?\s*alvo"),
    ("orgao_superior", r"[oó]rg[aã]o superior"),
    ("orgao_gestor", r"[oó]rg[aã]o gestor"),
    ("atores", r"atores envolvidos na implementa[cç][aã]o"),
    ("outros_atores", r"outros [oó]rg[aã]os\s*/?\s*atores envolvidos"),
    ("data_inicio", r"data de in[ií]cio\s*/?\s*cria[cç][aã]o"),
    ("legislacao", r"instrumentos legais relacionados"),
    ("data_encerramento", r"data de encerramento"),
    ("implementacao", r"forma e detalhamento da implementa[cç][aã]o"),
    ("resultados", r"resultados esperados"),
    ("marcos", r"marcos relevantes"),
    ("info_adicional", r"outras informa[cç][oõ]es"),
    ("prioritario", r"programa priorit[aá]rio"),
    ("ppa", r"plano plurianual"),
]

# rótulos da ficha de BASE DE DADOS
ROTULOS_BD = [
    ("nome", r"^nome$"),
    ("responsavel_dados", r"respons[aá]vel pelos dados prim[aá]rios"),
    ("forma_coleta", r"formas de coleta dos dados"),
    ("local_custodia", r"local onde os dados est[aã]o custodiados"),
    ("periodicidade", r"periodicidade de atualiza[cç][aã]o dos dados custodiados"),
    ("periodo_referencia", r"per[ií]odo de refer[eê]ncia"),
    ("formato", r"^formato$"),
    ("forma_acesso", r"formas de acesso"),
    ("perfis_acesso", r"perfis de usu[aá]rios e n[ií]veis de acesso"),
    ("dicionario", r"dicion[aá]rio de vari[aá]veis"),
    ("tratamento_dados", r"tratamento dos dados"),
    ("info_complementares", r"informa[cç][oõ]es complementares e links de manuais"),
]

# rótulos da ficha de FERRAMENTA
ROTULOS_FERRAMENTA = [
    ("nome", r"^nome$"),
    ("descricao", r"^descri[cç][aã]o$"),
    ("para_que_serve", r"para que serve"),
    ("info_gerais", r"informa[cç][oõ]es gerais"),
    ("publico_alvo", r"qual o p[uú]blico-?\s*alvo"),
    ("permite_fazer", r"o que a ferramenta permite fazer"),
    ("resultados", r"como aparecem os resultados"),
    ("privacidade", r"privacidade e seguran[cç]a"),
    ("limitacoes", r"limita[cç][oõ]es da ferramenta"),
    ("fonte_dados", r"de onde v[eê]m os dados"),
    ("tecnologias", r"tecnologias utilizadas"),
    ("acesso", r"quem pode acessar"),
    ("apoio", r"apoio ao usu[aá]rio"),
    ("como_acessar", r"como acessar e quem procurar"),
    ("info_adicional", r"observa[cç][oõ]es complementares"),
]

# rótulos da ficha de SINTAXE
ROTULOS_SINTAXE = [
    ("sintaxe", r"^sintaxe$"),
    ("descricao_sintaxe", r"descri[cç][aã]o da sintaxe"),
    ("autoria_sintaxe", r"autoria da sintaxe"),
]


# ======================= acesso à API (com metadados) =======================
def pagina_completa(pid):
    """Como cw.conteudo_pagina, mas também traz isPublished/autor/data —
    usados para 'ficha publicada?' e 'responsável/data da última atualização'."""
    q = ("query($id:Int!){ pages { single(id:$id){ path title content "
         "isPublished authorName updatedAt createdAt } } }")
    pg = cw._gql(q, {"id": pid})["pages"]["single"]
    # idem: normaliza fichas escritas no editor HTML antes de extrair campos.
    pg["content"] = gm.normalizar_conteudo_pagina(pg.get("content", ""))
    return pg


# ======================= indicadores =======================
def _dividir_f23(corpo):
    m = re.search(r"acompanhe o indicador nas ferramentas da sagicad", corpo, re.IGNORECASE)
    if not m:
        return corpo.strip(), ""
    documentos = corpo[:m.start()].strip()
    resto = corpo[m.start():]
    resto = re.sub(r"(?i)acompanhe o indicador nas ferramentas da sagicad[:\s]*", "", resto, count=1)
    return documentos, resto.strip()


def extrair_campos_indicador(markdown):
    """Detecta o modelo (antigo/novo) e extrai os campos correspondentes.
    Retorna (modelo, campos:dict)."""
    modelo = gm.detectar_modelo(markdown)
    if modelo == "novo":
        brutos = gm.extrair_por_item_numerado(markdown, CODIGOS_FICHA_NOVA)
        campos = {k: v for k, v in brutos.items() if k != "f23"}
        doc, ferr = _dividir_f23(brutos.get("f23", ""))
        campos["f23_documentos"] = doc
        campos["f23_ferramentas_sagicad"] = ferr
    else:
        campos = gm.extrair_por_cabecalho(markdown, cw.ROTULOS)
    return modelo, campos


def classificar_situacao_ficha_indicador(modelo, campos):
    if modelo == "novo":
        return gm.classificar_ficha(
            campos, CFG["indicador_novo"], CFG["indicador_novo_campos_status"], CFG)
    return gm.classificar_ficha(
        campos, CFG["indicador_antigo"], list(CFG["indicador_antigo"]), CFG)


def status_a5(campos_novo):
    c = gm.normalizar(campos_novo.get("a5", ""))
    if "em producao regular" in c:
        return "vigente"
    if "descontinuado" in c:
        return "descontinuado"
    return None


def nome_ferramenta_sagicad(nome, url):
    """Nome OFICIAL da ferramenta a partir do link registrado em "Acompanhe o
    indicador nas ferramentas da SAGICAD". Na ficha NOVA (Bloco F) o texto do
    link costuma ser uma descrição do INDICADOR (ex.: "Famílias e pessoas
    incluídas no Cadastro Único"), não o nome da ferramenta — então primeiro
    tentamos reconhecer a ferramenta pelo padrão da URL (ver
    "ferramentas_dominios" em padroes_fichas.json). Na ficha ANTIGA o texto do
    link já é o nome da ferramenta (ex.: "Visdata"), então isso normalmente
    nem chega a precisar do fallback por URL."""
    u = (url or "").lower()
    for pedaco, canonico in CFG.get("ferramentas_dominios", {}).items():
        if pedaco.lower() in u:
            return canonico
    nome = (nome or "").strip()
    if nome and len(nome) <= 30:
        return nome
    # nome ausente ou longo demais para ser o nome de uma ferramenta (é
    # provavelmente uma descrição do indicador) e a URL não bateu com
    # nenhum padrão conhecido -> identifica ao menos pelo domínio da URL.
    from urllib.parse import urlparse
    host = urlparse(url).netloc
    return f"Ferramenta em {host}" if host else (nome or "Ferramenta sem nome identificado")


_RX_ACOMPANHE_FERRAMENTAS = re.compile(r"acompanhe o indicador nas ferramentas da sagicad", re.IGNORECASE)
_RX_URL_SOLTA = re.compile(r"https?://[^\s)\]]+")


def extrair_ferramentas_sagicad(modelo, campos, markdown):
    """Nome + link registrados em "Acompanhe o indicador nas ferramentas da
    SAGICAD" (ex.: VisData, Monitora MDS, Observatório do Cadastro Único).

    Busca a frase em QUALQUER lugar da página — cabeçalho markdown (como na
    ficha nova, Bloco F), texto em negrito, item de lista ou parágrafo solto
    (como costuma acontecer na ficha antiga, onde esse campo não faz parte
    do Padrão de Indicadores oficial e por isso não tem formatação fixa) —
    e considera ferramenta QUALQUER link que apareça depois dela, seja em
    formato markdown [nome](url) ou uma URL solta, até o próximo cabeçalho
    ou o fim da página. Se não houver nenhum link ali, não é ferramenta
    vinculada, mesmo que haja outro texto preenchido."""
    texto = gm._RX_INFOBOX.sub("", gm._RX_COMENTARIO.sub("", markdown or ""))
    m = _RX_ACOMPANHE_FERRAMENTAS.search(texto)
    if not m:
        return []
    resto = texto[m.end():]
    prox_cabecalho = gm._RX_HEADER_MD.search(resto)
    secao = resto[:prox_cabecalho.start()] if prox_cabecalho else resto

    links = cw.extrair_links(secao)
    if not links:
        m_url = _RX_URL_SOLTA.search(secao)
        if m_url:
            links = [{"nome": "", "url": m_url.group(0).rstrip(").,;"), "tipo": "link"}]

    for l in links:
        l["nome"] = nome_ferramenta_sagicad(l.get("nome", ""), l.get("url", ""))
    return links


def classificar_sintaxe(campo_sintaxe_texto, link_sintaxe, texto_padrao_campo=""):
    """Retorna (situacao, pagina_sintaxe_url_usada)."""
    c = gm.normalizar(campo_sintaxe_texto or "")
    for frase in CFG["frases_sintaxe_indisponivel"]:
        if frase in c:
            return "Sintaxe indisponível", ""
    # a frase completa (com a explicação de onde a memória de cálculo está
    # registrada) pode variar um pouco na redação real da ficha; o núcleo
    # "sintaxe indisponível" já é suficientemente específico para não dar
    # falso positivo, então também aceitamos esse casamento mais solto.
    if "sintaxe indisponivel" in c:
        return "Sintaxe indisponível", ""
    if link_sintaxe:
        try:
            pid = link_sintaxe.get("id")
            conteudo = pagina_completa(pid)["content"] if pid else ""
        except Exception:
            conteudo = ""
        if conteudo:
            campos_si = gm.extrair_por_cabecalho(conteudo, ROTULOS_SINTAXE)
            situacao, _ = gm.classificar_ficha(
                campos_si, CFG["sintaxe"], list(CFG["sintaxe"]), CFG)
            return situacao, link_sintaxe.get("path", "")
        # há um link para a sintaxe mas não conseguimos ler a página-irmã agora
        return "iniciada", link_sintaxe.get("path", "")
    if not gm.campo_preenchido(campo_sintaxe_texto, texto_padrao_campo, CFG):
        return "não documentada", ""
    return "iniciada", ""


def _mapa_nomes_programa(todas):
    """codigo (minúsculo) -> nome oficial, a partir das listas curadas
    home/DS (vigentes) e home/E (não vigentes/descontinuados). É esse nome
    que aparece no filtro "Programa" do relatório, em vez do código curto
    (ex.: "Cadastro Único" em vez de "Cad")."""
    mapa = {}
    for path, status in cw._LISTAS_PROG:
        p = next((q for q in todas if q["path"] == path), None)
        if p:
            for r in cw.parse_lista_curada(cw.conteudo_pagina(p["id"])["content"], f"{BASE}/{path}", status):
                mapa.setdefault(r["codigo"].lower(), r["programa"])
    return mapa


def coletar_indicadores_da_api():
    todas = cw._todas_paginas()
    fichas = [p for p in todas if cw.RX_FICHA.search(p["path"])]
    status_lista = cw._mapa_status(todas)
    nomes_programa = _mapa_nomes_programa(todas)
    si_idx, bd_idx = {}, {}
    for p in todas:
        ms = cw.RX_SINTAXE.search(p["path"])
        if ms:
            si_idx[(ms.group("prog").lower(), ms.group("cod").upper())] = p
        mb = cw.RX_BD.search(p["path"])
        if mb:
            bd_idx.setdefault(mb.group("prog").lower(), p)

    print(f"fichas de indicador encontradas: {len(fichas)}")
    linhas = []
    for i, p in enumerate(fichas, 1):
        try:
            pg = pagina_completa(p["id"])
            modelo, campos = extrair_campos_indicador(pg["content"])
            situacao, detalhe = classificar_situacao_ficha_indicador(modelo, campos)
            publicada = gm.esta_publicada(pg, pg["content"])

            m = cw.RX_FICHA.search(pg["path"])
            prog, cod = (m.group("prog"), m.group("cod").upper()) if m else ("", "")
            nome = re.sub(r"^\s*IN\d+\s*[-–]\s*", "", (pg.get("title") or "").strip())

            si = si_idx.get((prog.lower(), cod.upper()))
            campo_sintaxe = campos.get("d18", "") if modelo == "novo" else campos.get("sintaxe", "")
            ref_sintaxe = CFG["indicador_novo"]["d18"] if modelo == "novo" else CFG["indicador_antigo"]["sintaxe"]
            link_si = {"id": si["id"], "path": f"{BASE}/{si['path']}"} if si else None
            situacao_sintaxe, sintaxe_url = classificar_sintaxe(campo_sintaxe, link_si, ref_sintaxe)
            if not sintaxe_url and si:
                sintaxe_url = f"{BASE}/{si['path']}"

            ferramentas_sagicad = extrair_ferramentas_sagicad(modelo, campos, pg["content"])
            visdata = next((l["url"] for l in ferramentas_sagicad
                             if "visdata" in gm.normalizar(l["nome"] + l["url"])), "")

            status_a5_val = status_a5(campos) if modelo == "novo" else None
            status_lista_val = status_lista.get(prog.lower())
            if status_a5_val and status_lista_val and status_a5_val != status_lista_val:
                status_programa = f"divergente (A5: {status_a5_val} / lista: {status_lista_val})"
            else:
                status_programa = status_a5_val or status_lista_val or ""

            bd = bd_idx.get(prog.lower())

            linhas.append({
                "codigo": cod, "nome": nome,
                "programa": nomes_programa.get(prog.lower(), prog),
                "codigo_programa": prog,
                "status_programa": status_programa,
                "modelo_ficha": modelo,
                "situacao_ficha": situacao,
                "publicada": "sim" if publicada else "não",
                "situacao_sintaxe": situacao_sintaxe,
                "link_sintaxe": sintaxe_url,
                "ferramenta_consulta": "; ".join(l["nome"] for l in ferramentas_sagicad),
                "ferramentas_sagicad": ferramentas_sagicad,
                "visdata": visdata,
                "link_bd": f"{BASE}/{bd['path']}" if bd else "",
                "responsavel_atualizacao": pg.get("authorName", ""),
                "data_atualizacao": pg.get("updatedAt", ""),
                "url": f"{BASE}/{pg['path']}",
                "_detalhe_campos": detalhe,
            })
        except Exception as e:
            print(f"  falha em {p['path']}: {e}")
        if i % 50 == 0:
            print(f"  ... {i}/{len(fichas)}")
    return linhas


def coletar_indicadores_de_amostra(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        fichas = json.load(f)
    linhas = []
    for x in fichas:
        x["content"] = gm.normalizar_conteudo_pagina(x.get("content", ""))
        modelo, campos = extrair_campos_indicador(x.get("content", ""))
        situacao, detalhe = classificar_situacao_ficha_indicador(modelo, campos)
        publicada = gm.esta_publicada(x, x.get("content", ""))
        m = cw.RX_FICHA.search(x.get("path", ""))
        prog, cod = (m.group("prog"), m.group("cod").upper()) if m else ("", "")
        campo_sintaxe = campos.get("d18", "") if modelo == "novo" else campos.get("sintaxe", "")
        ref_sintaxe = CFG["indicador_novo"]["d18"] if modelo == "novo" else CFG["indicador_antigo"]["sintaxe"]
        situacao_sintaxe, _ = classificar_sintaxe(campo_sintaxe, None, ref_sintaxe)
        ferramentas_sagicad = extrair_ferramentas_sagicad(modelo, campos, x.get("content", ""))
        visdata = next((l["url"] for l in ferramentas_sagicad
                         if "visdata" in gm.normalizar(l["nome"] + l["url"])), "")
        linhas.append({
            # modo offline (--amostra): sem acesso às listas curadas, o nome do
            # programa fica no código mesmo (prog); no modo real ele é resolvido.
            "codigo": cod, "nome": x.get("title", ""), "programa": prog, "codigo_programa": prog,
            "status_programa": status_a5(campos) if modelo == "novo" else "",
            "modelo_ficha": modelo, "situacao_ficha": situacao,
            "publicada": "sim" if publicada else "não",
            "situacao_sintaxe": situacao_sintaxe, "link_sintaxe": "",
            "ferramenta_consulta": "; ".join(l["nome"] for l in ferramentas_sagicad),
            "ferramentas_sagicad": ferramentas_sagicad,
            "visdata": visdata, "link_bd": "",
            "responsavel_atualizacao": x.get("authorName", ""),
            "data_atualizacao": x.get("updatedAt", ""),
            "url": x.get("path", ""), "_detalhe_campos": detalhe,
        })
    return linhas


CAMPOS_CSV_INDICADORES = ["codigo", "nome", "programa", "codigo_programa", "status_programa",
                           "modelo_ficha", "situacao_ficha", "publicada", "situacao_sintaxe",
                           "link_sintaxe", "ferramenta_consulta", "visdata", "link_bd",
                           "responsavel_atualizacao", "data_atualizacao", "url"]


def gravar_indicadores(linhas, base="relatorio_indicadores"):
    with open(f"{base}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_CSV_INDICADORES, extrasaction="ignore")
        w.writeheader()
        for r in linhas:
            w.writerow(r)
    with open(f"{base}.jsonl", "w", encoding="utf-8") as f:
        for r in linhas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    catalogo_html.render(
        f"{base}.html",
        titulo="Gerenciamento de Indicadores · Documenta Wiki (MDS)",
        subtitulo="Modelo de ficha, situação de preenchimento, sintaxe e publicação de cada indicador.",
        fonte_url=BASE, total_origem=None,
        colunas=[
            {"key": "codigo", "label": "Código", "tipo": "text"},
            {"key": "nome", "label": "Indicador", "tipo": "long"},
            {"key": "programa", "label": "Programa", "tipo": "text"},
            {"key": "status_programa", "label": "Status do programa", "tipo": "text"},
            {"key": "modelo_ficha", "label": "Modelo da ficha", "tipo": "text"},
            {"key": "situacao_ficha", "label": "Situação da ficha", "tipo": "text"},
            {"key": "publicada", "label": "Publicada?", "tipo": "text"},
            {"key": "situacao_sintaxe", "label": "Sintaxe", "tipo": "text"},
            {"key": "_ferramentas", "label": "Ferramenta de consulta", "tipo": "link"},
            {"key": "responsavel_atualizacao", "label": "Última atualização por", "tipo": "text"},
            {"key": "data_atualizacao", "label": "Data", "tipo": "text"},
            {"key": "_link", "label": "Ficha · sintaxe", "tipo": "link"},
        ],
        linhas=[{**r,
                 "_ferramentas": [(l["nome"], l["url"]) for l in r.get("ferramentas_sagicad", [])],
                 "_link": [("ficha", r["url"])] + ([("sintaxe", r["link_sintaxe"])] if r["link_sintaxe"] else [])}
                for r in linhas],
        filtros=["status_programa", "programa", "modelo_ficha", "situacao_ficha",
                 "publicada", "situacao_sintaxe"],
        filtro_dependencias={"programa": ["status_programa"]},
    )


# ======================= programas =======================
def extrair_campos_programa(markdown):
    texto = gm._RX_INFOBOX.sub("", gm._RX_COMENTARIO.sub("", markdown or ""))
    heads = list(gm._RX_HEADER_MD.finditer(texto))
    campos = gm.extrair_por_cabecalho(markdown, ROTULOS_PROGRAMA)
    campos["nome_popular"] = (texto[:heads[0].start()] if heads else texto).strip()
    return campos


def classificar_situacao_programa(campos, vigente):
    excluidos = set(CFG.get("programa_campos_excluidos", []))
    campos_avaliar = [k for k in CFG["programa"] if k not in excluidos]
    return gm.classificar_ficha(
        campos, CFG["programa"], campos_avaliar, CFG,
        campos_fixos=CFG["programa_campos_fixos"],
        campos_condicionais=CFG["programa_campos_condicionais_vigente"],
        condicao_ativa=not vigente)


def coletar_programas_da_api():
    todas = cw._todas_paginas()
    regs = []
    for path, status in cw._LISTAS_PROG:
        p = next((q for q in todas if q["path"] == path), None)
        if p:
            regs += cw.parse_lista_curada(cw.conteudo_pagina(p["id"])["content"], f"{BASE}/{path}", status)
    cont = cw._contar_indicadores(todas)
    idx = {q["path"]: q for q in todas}
    vistos, linhas = set(), []
    for r in regs:
        k = r["codigo"].lower()
        if k in vistos:
            continue
        vistos.add(k)
        pg = idx.get(f"home/{r['root']}/{r['codigo']}") or idx.get(f"home/DS/{r['codigo']}") \
            or idx.get(f"home/E/{r['codigo']}")
        if not pg:
            linhas.append({**r, "situacao_ficha": "não documentada", "publicada": "—",
                           "n_indicadores": cont.get(k, 0), "responsavel_atualizacao": "",
                           "data_atualizacao": "", "url": ""})
            continue
        conteudo = pagina_completa(pg["id"])
        campos = extrair_campos_programa(conteudo["content"])
        vigente = r["status"] == "vigente"
        situacao, _ = classificar_situacao_programa(campos, vigente)
        publicada = gm.esta_publicada(conteudo, conteudo["content"])
        linhas.append({
            "codigo": r["codigo"], "programa": campos.get("nome_popular") or r["programa"],
            "tipo": r["tipo"], "status": r["status"], "selo": r.get("selo", ""),
            "n_indicadores": cont.get(k, 0),
            "situacao_ficha": situacao, "publicada": "sim" if publicada else "não",
            "responsavel_atualizacao": conteudo.get("authorName", ""),
            "data_atualizacao": conteudo.get("updatedAt", ""),
            "url": f"{BASE}/{conteudo['path']}",
        })
    return linhas


def coletar_programas_de_amostra(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        dados = json.load(f)
    if isinstance(dados, dict):
        dados = [dados]
    linhas = []
    for x in dados:
        x["content"] = gm.normalizar_conteudo_pagina(x.get("content", ""))
        campos = extrair_campos_programa(x.get("content", ""))
        vigente = gm.normalizar(x.get("status", "vigente")) != "descontinuado"
        situacao, _ = classificar_situacao_programa(campos, vigente)
        publicada = gm.esta_publicada(x, x.get("content", ""))
        linhas.append({
            "codigo": x.get("codigo", ""), "programa": campos.get("nome_popular") or x.get("programa", ""),
            "tipo": x.get("tipo", "programa"), "status": "vigente" if vigente else "descontinuado",
            "selo": "", "n_indicadores": 0,
            "situacao_ficha": situacao, "publicada": "sim" if publicada else "não",
            "responsavel_atualizacao": x.get("authorName", ""), "data_atualizacao": x.get("updatedAt", ""),
            "url": x.get("path", ""),
        })
    return linhas


def gravar_programas(linhas, base="relatorio_programas"):
    cols = ["codigo", "programa", "tipo", "status", "selo", "n_indicadores", "situacao_ficha",
            "publicada", "responsavel_atualizacao", "data_atualizacao", "url"]
    with open(f"{base}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in linhas:
            w.writerow(r)
    with open(f"{base}.jsonl", "w", encoding="utf-8") as f:
        for r in linhas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    catalogo_html.render(
        f"{base}.html",
        titulo="Gerenciamento de Programas · Documenta Wiki (MDS)",
        subtitulo="Situação de preenchimento da ficha de cada política/programa/benefício/serviço/ação.",
        fonte_url=BASE, total_origem=None,
        colunas=[
            {"key": "codigo", "label": "Código", "tipo": "text"},
            {"key": "programa", "label": "Programa / sistema", "tipo": "long"},
            {"key": "status", "label": "Status do programa", "tipo": "text"},
            {"key": "situacao_ficha", "label": "Situação da ficha", "tipo": "text"},
            {"key": "publicada", "label": "Publicada?", "tipo": "text"},
            {"key": "n_indicadores", "label": "Indicadores", "tipo": "text"},
            {"key": "responsavel_atualizacao", "label": "Última atualização por", "tipo": "text"},
            {"key": "data_atualizacao", "label": "Data", "tipo": "text"},
            {"key": "_link", "label": "Ficha", "tipo": "link"},
        ],
        linhas=[{**r, "_link": [("abrir", r["url"])] if r["url"] else []} for r in linhas],
        filtros=["status", "situacao_ficha", "publicada", "selo"],
    )


# ======================= base de dados =======================
def extrair_campos_bd(markdown):
    return gm.extrair_por_cabecalho(markdown, ROTULOS_BD)


def coletar_bd_da_api():
    todas = cw._todas_paginas()
    fichas_bd = [p for p in todas if cw.RX_BD.search(p["path"])]
    idx_prog = {}
    for p in todas:
        m = re.search(r"(?:^|/)home/(DS|E)/([^/]+)$", p["path"])
        if m:
            idx_prog[m.group(2).lower()] = p
    print(f"fichas de base de dados encontradas: {len(fichas_bd)}")
    linhas = []
    for p in fichas_bd:
        try:
            m = cw.RX_BD.search(p["path"])
            prog = m.group("prog") if m else ""
            status_programa = "vigente" if (m and m.group("raiz").upper() == "DS") else "descontinuado"
            conteudo = pagina_completa(p["id"])
            campos = extrair_campos_bd(conteudo["content"])
            situacao, _ = gm.classificar_ficha(campos, CFG["base_dados"], list(CFG["base_dados"]), CFG)
            publicada = gm.esta_publicada(conteudo, conteudo["content"])
            pg_prog = idx_prog.get(prog.lower())
            linhas.append({
                "programa": (pg_prog.get("title") if pg_prog else prog) or prog,
                "codigo_programa": prog,
                "status_programa": status_programa,
                "situacao_ficha": situacao, "publicada": "sim" if publicada else "não",
                "responsavel_atualizacao": conteudo.get("authorName", ""),
                "data_atualizacao": conteudo.get("updatedAt", ""),
                "url": f"{BASE}/{conteudo['path']}",
            })
        except Exception as e:
            print(f"  falha em {p['path']}: {e}")
    return linhas


def coletar_bd_de_amostra(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        dados = json.load(f)
    if isinstance(dados, dict):
        dados = [dados]
    linhas = []
    for x in dados:
        x["content"] = gm.normalizar_conteudo_pagina(x.get("content", ""))
        campos = extrair_campos_bd(x.get("content", ""))
        situacao, _ = gm.classificar_ficha(campos, CFG["base_dados"], list(CFG["base_dados"]), CFG)
        publicada = gm.esta_publicada(x, x.get("content", ""))
        status_default = "descontinuado" if re.search(r"(?:^|/)home/E/", x.get("path", ""), re.I) else "vigente"
        linhas.append({
            "programa": x.get("programa", ""), "codigo_programa": x.get("codigo", ""),
            "status_programa": "descontinuado" if gm.normalizar(x.get("status", status_default)) == "descontinuado" else "vigente",
            "situacao_ficha": situacao, "publicada": "sim" if publicada else "não",
            "responsavel_atualizacao": x.get("authorName", ""), "data_atualizacao": x.get("updatedAt", ""),
            "url": x.get("path", ""),
        })
    return linhas


def gravar_bd(linhas, base="relatorio_base_dados"):
    cols = ["programa", "codigo_programa", "status_programa", "situacao_ficha", "publicada",
            "responsavel_atualizacao", "data_atualizacao", "url"]
    with open(f"{base}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in linhas:
            w.writerow(r)
    with open(f"{base}.jsonl", "w", encoding="utf-8") as f:
        for r in linhas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    catalogo_html.render(
        f"{base}.html",
        titulo="Gerenciamento de Bases de Dados · Documenta Wiki (MDS)",
        subtitulo="Situação de preenchimento da ficha de base de dados de cada programa.",
        fonte_url=BASE, total_origem=None,
        colunas=[
            {"key": "programa", "label": "Programa vinculado", "tipo": "long"},
            {"key": "codigo_programa", "label": "Código", "tipo": "text"},
            {"key": "status_programa", "label": "Status do programa", "tipo": "text"},
            {"key": "situacao_ficha", "label": "Situação da ficha", "tipo": "text"},
            {"key": "publicada", "label": "Publicada?", "tipo": "text"},
            {"key": "responsavel_atualizacao", "label": "Última atualização por", "tipo": "text"},
            {"key": "data_atualizacao", "label": "Data", "tipo": "text"},
            {"key": "_link", "label": "Ficha", "tipo": "link"},
        ],
        linhas=[{**r, "_link": [("abrir", r["url"])] if r["url"] else []} for r in linhas],
        filtros=["status_programa", "situacao_ficha", "publicada"],
    )


# ======================= ferramentas (bônus) =======================
def extrair_campos_ferramenta(markdown):
    return gm.extrair_por_cabecalho(markdown, ROTULOS_FERRAMENTA)


def coletar_ferramentas_da_api():
    todas = cw._todas_paginas()
    fichas = [p for p in todas if cw.RX_FICHA_FERRAMENTA.match(p["path"])]
    print(f"fichas de ferramenta encontradas: {len(fichas)}")
    linhas = []
    for p in fichas:
        try:
            conteudo = pagina_completa(p["id"])
            campos = extrair_campos_ferramenta(conteudo["content"])
            situacao, _ = gm.classificar_ficha(campos, CFG["ferramenta"], list(CFG["ferramenta"]), CFG)
            publicada = gm.esta_publicada(conteudo, conteudo["content"])
            nome = (campos.get("nome") or conteudo.get("title") or p["path"].split("/")[-1]).strip()
            linhas.append({
                "nome": nome, "situacao_ficha": situacao, "publicada": "sim" if publicada else "não",
                "responsavel_atualizacao": conteudo.get("authorName", ""),
                "data_atualizacao": conteudo.get("updatedAt", ""),
                "url": f"{BASE}/{conteudo['path']}",
            })
        except Exception as e:
            print(f"  falha em {p['path']}: {e}")
    return linhas


def gravar_ferramentas(linhas, base="relatorio_ferramentas"):
    cols = ["nome", "situacao_ficha", "publicada", "responsavel_atualizacao", "data_atualizacao", "url"]
    with open(f"{base}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in linhas:
            w.writerow(r)
    with open(f"{base}.jsonl", "w", encoding="utf-8") as f:
        for r in linhas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    catalogo_html.render(
        f"{base}.html",
        titulo="Gerenciamento de Ferramentas · Documenta Wiki (MDS)",
        subtitulo="Situação de preenchimento da ficha de cada ferramenta informacional da SAGICAD.",
        fonte_url=BASE, total_origem=None,
        colunas=[
            {"key": "nome", "label": "Ferramenta", "tipo": "long"},
            {"key": "situacao_ficha", "label": "Situação da ficha", "tipo": "text"},
            {"key": "publicada", "label": "Publicada?", "tipo": "text"},
            {"key": "responsavel_atualizacao", "label": "Última atualização por", "tipo": "text"},
            {"key": "data_atualizacao", "label": "Data", "tipo": "text"},
            {"key": "_link", "label": "Ficha", "tipo": "link"},
        ],
        linhas=[{**r, "_link": [("abrir", r["url"])] if r["url"] else []} for r in linhas],
        filtros=["situacao_ficha", "publicada"],
    )


# ======================= dashboard (cards + gráficos) =======================
def _ler_jsonl(caminho):
    if not os.path.exists(caminho):
        return []
    linhas = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                linhas.append(json.loads(linha))
    return linhas


_ORDEM_SITUACAO = ["documentada", "iniciada", "não documentada"]
_ORDEM_SINTAXE = ["documentada", "iniciada", "não documentada", "Sintaxe indisponível"]


def _contagem_ordenada(linhas, chave, ordem):
    cont = Counter(r.get(chave, "") or "—" for r in linhas)
    itens = [(rotulo, cont[rotulo]) for rotulo in ordem if cont.get(rotulo)]
    # qualquer valor fora da ordem esperada (ex.: "divergente (...)") entra no final
    extras = [(k, v) for k, v in cont.items() if k not in ordem]
    itens += sorted(extras, key=lambda kv: -kv[1])
    return itens


def _eh_vigente(valor):
    return gm.normalizar(valor or "") == "vigente"


def _montar_cards_e_graficos(indicadores, programas, n_ferramentas):
    cards = [
        {"label": "Programas / sistemas", "valor": len(programas)},
        {"label": "Indicadores", "valor": len(indicadores)},
        {"label": "Ferramentas", "valor": n_ferramentas},
    ]

    graficos = []
    if indicadores:
        graficos.append({
            "titulo": "Situação da ficha (indicadores)",
            "itens": _contagem_ordenada(indicadores, "situacao_ficha", _ORDEM_SITUACAO),
        })
        graficos.append({
            "titulo": "Situação da sintaxe",
            "itens": _contagem_ordenada(indicadores, "situacao_sintaxe", _ORDEM_SINTAXE),
        })

        contagem_ferr = Counter()
        sem_vinculo = 0
        for r in indicadores:
            nomes = [x.get("nome", "").strip() for x in (r.get("ferramentas_sagicad") or []) if x.get("nome")]
            if not nomes:
                sem_vinculo += 1
            for n in nomes:
                contagem_ferr[n] += 1
        itens_ferr = sorted(contagem_ferr.items(), key=lambda kv: -kv[1])
        if sem_vinculo:
            itens_ferr.append(("Sem ferramenta vinculada", sem_vinculo))
        graficos.append({
            "titulo": "Indicadores vinculados a ferramentas da SAGICAD (por ferramenta)",
            "itens": itens_ferr,
        })
    return cards, graficos


def gravar_dashboard(base="dashboard.html"):
    """Lê os .jsonl já existentes na pasta (não refaz a coleta) e monta os
    cards + gráficos do dashboard, com abas Vigente/Descontinuado (aberto
    por padrão em Vigente). Pode ser chamado sozinho (--dashboard) para só
    atualizar essa página a partir do que já foi gerado antes.
    Ferramentas não são filtradas por status — não são vinculadas a um
    programa específico, então o card mostra o total nas duas abas."""
    indicadores = _ler_jsonl("relatorio_indicadores.jsonl")
    programas = _ler_jsonl("relatorio_programas.jsonl")
    n_ferramentas = len(_ler_jsonl("relatorio_ferramentas.jsonl"))

    prog_vigentes = [p for p in programas if _eh_vigente(p.get("status"))]
    prog_descontinuados = [p for p in programas if not _eh_vigente(p.get("status"))]
    ind_vigentes = [r for r in indicadores if _eh_vigente(r.get("status_programa"))]
    ind_descontinuados = [r for r in indicadores if not _eh_vigente(r.get("status_programa"))]

    cards_v, graf_v = _montar_cards_e_graficos(ind_vigentes, prog_vigentes, n_ferramentas)
    cards_d, graf_d = _montar_cards_e_graficos(ind_descontinuados, prog_descontinuados, n_ferramentas)

    secoes = [
        {"key": "vigente", "label": "Vigente", "cards": cards_v, "graficos": graf_v},
        {"key": "descontinuado", "label": "Descontinuado", "cards": cards_d, "graficos": graf_d},
    ]
    catalogo_html.render_dashboard(base, secoes=secoes, padrao="vigente")
    print(f"gerado: {base}")
    return base


# ======================= painel (abas) =======================
_PAINEL_CANDIDATOS = [
    ("dashboard", "Dashboard", "dashboard.html"),
    ("indicadores", "Indicadores", "relatorio_indicadores.html"),
    ("programas", "Programas", "relatorio_programas.html"),
    ("bd", "Base de Dados", "relatorio_base_dados.html"),
    ("ferramentas", "Ferramentas", "relatorio_ferramentas.html"),
]


def gravar_painel(base="painel.html"):
    """Monta/atualiza a página de abas com os relatórios que existirem na
    pasta neste momento (não precisa ter rodado os 4 agora — reaproveita
    o que já foi gerado antes)."""
    relatorios = [{"key": k, "label": l, "arquivo": a}
                  for k, l, a in _PAINEL_CANDIDATOS if os.path.exists(a)]
    if not relatorios:
        return None
    catalogo_html.render_painel(base, relatorios)
    print(f"gerado: {base} (abas: {', '.join(r['label'] for r in relatorios)})")
    return base


# ======================= CLI =======================
def _erro_api(e):
    print(f"ERRO ao acessar a API GraphQL: {e}")
    print("Provável necessidade de token de leitura. Peça à DMA/SAGICAD "
          "(wiki@mds.gov.br) e rode com: export WIKI_TOKEN=...")


def _resumo(linhas, chave="situacao_ficha"):
    cont = {}
    for r in linhas:
        cont[r.get(chave, "")] = cont.get(r.get(chave, ""), 0) + 1
    return ", ".join(f"{k or '—'}: {v}" for k, v in sorted(cont.items()))


def main():
    args = sys.argv[1:]

    if "--painel" in args:
        gravar_painel()
        return

    if "--dashboard" in args:
        gravar_dashboard()
        gravar_painel()
        return

    amostra = None
    if "--amostra" in args:
        i = args.index("--amostra")
        amostra = args[i + 1] if i + 1 < len(args) else None

    alvos = []
    if "--tudo" in args:
        alvos = ["indicadores", "programas", "bd", "ferramentas"]
    elif "--programas" in args:
        alvos = ["programas"]
    elif "--bd" in args:
        alvos = ["bd"]
    elif "--ferramentas" in args:
        alvos = ["ferramentas"]
    else:
        alvos = ["indicadores"]

    if "indicadores" in alvos:
        try:
            linhas = coletar_indicadores_de_amostra(amostra) if amostra else coletar_indicadores_da_api()
        except Exception as e:
            _erro_api(e)
        else:
            gravar_indicadores(linhas)
            print(f"[Indicadores] total: {len(linhas)} | situação da ficha -> {_resumo(linhas)}")
            print(f"[Indicadores] sintaxe -> {_resumo(linhas, 'situacao_sintaxe')}")
            print(f"[Indicadores] modelo -> {_resumo(linhas, 'modelo_ficha')}")
            print("gerados: relatorio_indicadores.csv, .jsonl e .html")

    if "programas" in alvos:
        try:
            linhas = coletar_programas_de_amostra(amostra) if amostra else coletar_programas_da_api()
        except Exception as e:
            _erro_api(e)
        else:
            gravar_programas(linhas)
            print(f"[Programas] total: {len(linhas)} | situação da ficha -> {_resumo(linhas)}")
            print("gerados: relatorio_programas.csv, .jsonl e .html")

    if "bd" in alvos:
        try:
            linhas = coletar_bd_de_amostra(amostra) if amostra else coletar_bd_da_api()
        except Exception as e:
            _erro_api(e)
        else:
            gravar_bd(linhas)
            print(f"[Base de Dados] total: {len(linhas)} | situação da ficha -> {_resumo(linhas)}")
            print("gerados: relatorio_base_dados.csv, .jsonl e .html")

    if "ferramentas" in alvos:
        try:
            linhas = coletar_ferramentas_da_api()
        except Exception as e:
            _erro_api(e)
        else:
            gravar_ferramentas(linhas)
            print(f"[Ferramentas] total: {len(linhas)} | situação da ficha -> {_resumo(linhas)}")
            print("gerados: relatorio_ferramentas.csv, .jsonl e .html")

    gravar_dashboard()
    gravar_painel()


if __name__ == "__main__":
    main()
