"""
coletor_wiki.py — SIG-Evidência, Documenta Wiki (MDS): fichas de indicadores
e lista de programas (vigentes/descontinuados)

A Documenta Wiki (https://wiki-sagi.mds.gov.br) é uma instância Wiki.js. O texto
das páginas NÃO vem no HTML: a página é uma SPA que busca o conteúdo pela API
GraphQL do Wiki.js. Por isso este coletor NÃO raspa HTML — consome a API, que é
o caminho oficial de leitura automatizada.

Três produtos, a partir da mesma API (estrutura da wiki: home/DS=vigentes,
home/E=descontinuados, home/F=ferramentas, home/SI=sintaxe dos indicadores):
  1. Fichas de indicador (Padrão de Indicadores): descrição, unidade, fórmula,
     fonte, periodicidade, acesso, e ONDE o dado está (ferramenta/servidor/banco/
     tabelas via página de sintaxe; link VisData via a própria ficha).
     -> catalogo_wiki_indicadores.{csv,jsonl,html}
  2. Fichas de programas/sistemas (vigentes + descontinuados): descrição/objetivo,
     legislação, público-alvo, órgão gestor, datas, selo, nº de indicadores.
     -> catalogo_programas.{csv,jsonl,html}
  3. Fichas de ferramentas informacionais (VisData, painéis, RI, observatórios).
     -> catalogo_ferramentas.{csv,jsonl,html}

Dependências: catalogo_html.py (mesma pasta) e `pip install requests`.
Acesso: a leitura via GraphQL pode exigir um token (grupo Guest sem permissão).
Peça um token de leitura à DMA/SAGICAD (wiki@mds.gov.br) e exporte em WIKI_TOKEN.

Uso:
    export WIKI_TOKEN=...                              # se a leitura exigir auth
    python coletor_wiki.py                             # fichas de indicador (API)
    python coletor_wiki.py --programas                 # fichas de programas (API)
    python coletor_wiki.py --ferramentas               # fichas de ferramentas (API)
    python coletor_wiki.py --amostra fichas.json       # testa o parser offline
    python coletor_wiki.py --programas --amostra prog.json   # idem, programas
"""
import os, re, sys, csv, json, unicodedata
import catalogo_html
import gerenciamento as _gm

BASE = "https://wiki-sagi.mds.gov.br"
GRAPHQL = f"{BASE}/graphql"


def _carregar_token():
    """Token de leitura da wiki: primeiro tenta a variável de ambiente
    WIKI_TOKEN; se não houver, tenta o arquivo local wiki_token.txt (mesma
    pasta, ignorado pelo git — veja .gitignore). Nunca fica hardcoded no
    código, para este projeto poder ir para um repositório (mesmo privado)
    sem expor a credencial de acesso à wiki."""
    tok = os.environ.get("WIKI_TOKEN", "").strip()
    if tok:
        return tok
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wiki_token.txt")
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            return f.read().strip()
    return ""


TOKEN = _carregar_token()

# caminho de ficha de indicador: .../I/IN###  — em home/DS (vigentes) e
# home/E (programas descontinuados/não-vigentes). Ex.: home/DS/Cad/I/IN007
RX_FICHA = re.compile(r"(?:^|/)home/(?:DS|E)/(?P<prog>[^/]+)/I/(?P<cod>IN\d+)\b", re.I)

# Rótulos do "Padrão de Indicadores" -> chave do catálogo. A wiki usa DOIS
# templates de ficha (um enxuto, um detalhado), com rótulos diferentes para o
# mesmo conceito; cada regex casa o PREFIXO do cabeçalho markdown. Ordem importa:
# o mais específico vem antes (ex.: "Metodologia (Fórmula...)" é fórmula, não
# metodologia genérica).
ROTULOS = [
    ("descricao",      r"descri[cç][aã]o(?:\s+e\s+interpreta[cç][aã]o)?"),
    ("unidade",        r"unidade de medida"),
    ("intervalo",      r"dom[ií]nio|intervalo de valores"),
    ("status_acesso",  r"n[ií]vel de publiciza[cç][aã]o|status de publiciza[cç][aã]o|publiciza[cç][aã]o"),
    ("fonte",          r"fonte"),
    ("data_inicio",    r"data a partir da qual|data de in[ií]cio"),
    ("periodicidade",  r"periodicidade"),
    ("desagregacao",   r"n[ií]veis? de desagrega[cç][aã]o"),
    ("formula",        r"metodologia\s*\(\s*f[oó]rmula|f[oó]rmula de c[aá]lculo"),
    ("metodologia",    r"metodologia"),
    ("sintaxe",        r"informa[cç][oõ]es sobre a sintaxe|sintaxe|mem[oó]ria de c[aá]lculo"),
    ("autoria",        r"autoria do m[eé]todo"),
    ("info_adicional", r"informa[cç][oõ]es complementares|informa[cç][oõ]es relevantes(?: adicionais)?"),
    ("interpretacao",  r"interpreta[cç][aã]o"),
]

# Rótulos da FICHA DE PROGRAMA/SISTEMA (home/DS/<slug>, home/E/<slug>)
ROTULOS_PROGRAMA = [
    ("descricao",       r"descri[cç][aã]o e objetivo|descri[cç][aã]o"),
    ("orgao_superior",  r"[oó]rg[aã]o superior"),
    ("orgao_gestor",    r"[oó]rg[aã]o gestor"),
    ("data_inicio",     r"data de in[ií]cio|data de cria"),
    ("data_encerramento", r"data de encerramento"),
    ("publico_alvo",    r"p[uú]blico-?\s*alvo"),
    ("legislacao",      r"instrumentos legais|legisla[cç][aã]o|base legal"),
    ("governanca",      r"informa[cç][oõ]es de governan|governan[cç]a"),
    ("atores",          r"atores envolvidos"),
    ("implementacao",   r"forma e detalhamento|implementa[cç][aã]o"),
    ("resultados",      r"resultados esperados|objetivos espec"),
    ("prioritario",     r"programa priorit"),
    ("marcos",          r"marcos relevantes"),
    ("info_adicional",  r"informa[cç][oõ]es complementares"),
]

# Rótulos da FICHA DE FERRAMENTA (home/F/<slug>)
ROTULOS_FERRAMENTA = [
    ("nome_completo",   r"nome"),
    ("descricao",       r"descri[cç][aã]o"),
    ("para_que_serve",  r"para que serve"),
    ("permite_fazer",   r"o que a ferramenta permite|o que permite"),
    ("info_gerais",     r"informa[cç][oõ]es gerais"),
    ("resultados",      r"como aparecem os resultados"),
    ("fonte_dados",     r"de onde v[eê]m os dados|fonte"),
    ("tecnologias",     r"tecnologias utilizadas|tecnologia"),
    ("publico_alvo",    r"qual o p[uú]blico|p[uú]blico-?\s*alvo|quem pode acessar"),
    ("acesso",          r"como acessar"),
    ("privacidade",     r"privacidade e seguran"),
    ("limitacoes",      r"limita[cç][oõ]es"),
    ("apoio",           r"apoio ao usu|suporte"),
    ("info_adicional",  r"observa[cç][oõ]es complementares|observa[cç][oõ]es"),
]

RX_COMENTARIO = re.compile(r"<!--.*?-->", re.S)            # rótulos trazem <!--(...)-->
RX_HEADER = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]*(.+?)[ \t]*$")
RX_INFOBOX = re.compile(r"\{\.is-[a-z]+\}")                # blocos {.is-info} do Wiki.js


def _sem_acento(s):
    return unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode().lower()


def _classificar(rotulo, rotulos):
    for chave, rx in rotulos:
        if re.match(rf"\s*(?:{rx})", rotulo, re.IGNORECASE):
            return chave
    return None


def extrair_campos(markdown, rotulos=ROTULOS):
    """Extrai os campos da ficha pelos cabeçalhos markdown (## Rótulo). Cada
    seção vai do seu cabeçalho até o próximo cabeçalho, qualquer que seja.
    `rotulos` permite reaproveitar o mesmo motor para fichas de programa/ferramenta."""
    texto = RX_INFOBOX.sub("", RX_COMENTARIO.sub("", markdown or ""))
    heads = list(RX_HEADER.finditer(texto))
    campos = {}
    for i, m in enumerate(heads):
        chave = _classificar(m.group(1), rotulos)
        if not chave or chave in campos:           # mantém a 1ª ocorrência
            continue
        fim = heads[i + 1].start() if i + 1 < len(heads) else len(texto)
        corpo = re.sub(r"[*`>]", "", texto[m.end():fim]).strip()
        if corpo:
            campos[chave] = corpo
    return campos


def _publico(status):
    s = (status or "").lower()
    if "restrit" in s:
        return False
    if "p\u00fablico" in s or "publico" in s:
        return True
    return None


# ======================= "onde est\u00e1 o dado / em que ferramenta" =======================
# A informa\u00e7\u00e3o de localiza\u00e7\u00e3o vive na p\u00e1gina de SINTAXE irm\u00e3 (home/SI/<prog>/IN###),
# n\u00e3o na ficha. Plataformas/ferramentas conhecidas do ecossistema de dados do MDS:
FERRAMENTAS = ["Hadoop", "Teradata", "Spark", "Hive", "Impala", "DataLake", "Data Lake",
               "Power BI", "PowerBI", "Tableau", "Qlik", "Excel", "Python", "SQL",
               "Stata", "SPSS", "SAS", "Dataprev", "DATAPREV", "Oracle", "PostgreSQL",
               "Postgres", "DuckDB", "VDP", "Denodo"]

# frases de instru\u00e7\u00e3o do template (boilerplate) \u2014 n\u00e3o s\u00e3o conte\u00fado real
_BOILER = [_sem_acento(x) for x in [
    "para calculos automatizados", "para calculos de indicadores realizados de modo",
    "preencher com", "explicacao geral sobre as escolhas", "se necessario",
    "nao disponivel", "incluir link", "nos casos em que a formula",
    "acesse aqui o link", "o nome do arquivo", "entidades responsaveis",
    "o metodo utilizado", "a localizacao dos dados", "o periodo de tempo",
    "periodo de quando os dados", "o tipo de bando de dados", "metodos de acessar",
]]
RX_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")

# ferramentas de consulta/visualização da Sagicad — ONDE o dado é publicado/visto
# (VisData, painéis, CECAD, CadSUAS, Tabsocial...). Mora na ficha, não na sintaxe.
RX_FERRAMENTA_CONSULTA = re.compile(
    r"aplicacoes\.(?:mds|cidadania)\.gov\.br|/vis/data|visdata|vis\s*data|painel|"
    r"pefi|cecad|cadsuas|tabsocial|tabnet|datasocial|data\s*social", re.I)


def _tipo_link(nome, url):
    alvo = _sem_acento(f"{nome} {url}")
    if RX_FERRAMENTA_CONSULTA.search(f"{nome} {url}"):
        return "ferramenta"
    if "/home/si/" in url.lower() or "sintaxe" in alvo:
        return "sintaxe"
    if any(k in alvo for k in ("planalto.gov.br", "in.gov.br", "ccivil", " lei ",
                               "portaria", "resolu", "decreto", "medida provis")):
        return "legislacao"
    if "manual" in alvo:
        return "manual"
    if "wiki-sagi" in url.lower():
        return "wiki"
    return "outro"


def extrair_links(content):
    """Todos os links markdown da página, classificados e deduplicados por URL."""
    vistos, out = set(), []
    for nome, url in RX_LINK.findall(content or ""):
        u = url.rstrip(").,;")
        if u in vistos:
            continue
        vistos.add(u)
        out.append({"nome": (nome.strip(" *`.") or u), "url": u, "tipo": _tipo_link(nome, u)})
    return out


def _limpar_boiler(content):
    """Remove instru\u00e7\u00f5es de template (linhas '>', blocos {.is-info}, coment\u00e1rios
    e frases-padr\u00e3o), devolvendo s\u00f3 o que foi de fato preenchido."""
    txt = RX_COMENTARIO.sub("", content or "")
    txt = re.sub(r"\{\.is-[a-z]+\}", "", txt)
    out = []
    for l in txt.splitlines():
        ls = _sem_acento(l).strip()
        if not ls or l.lstrip().startswith(">") or l.lstrip().startswith("#"):
            continue
        if any(b in ls for b in _BOILER):
            continue
        out.append(l.strip(" *`"))
    return "\n".join([l for l in out if l]).strip()


def extrair_sintaxe(content):
    """Da p\u00e1gina de sintaxe, extrai localiza\u00e7\u00e3o do dado: ferramenta/plataforma,
    servidor, banco, tabelas, e o script/links \u2014 tudo que diz 'onde est\u00e1'."""
    limpo = _limpar_boiler(content)
    info = {"sintaxe": limpo, "ferramenta": "", "servidor": "", "banco": "",
            "tabelas": "", "links": extrair_links(content)}
    if not limpo:
        return info
    achadas = [f for f in FERRAMENTAS if re.search(rf"\b{re.escape(f)}\b", limpo, re.I)]
    # dedup preservando ordem e normalizando capitaliza\u00e7\u00e3o
    vis, ferr = set(), []
    for f in achadas:
        k = f.lower().replace(" ", "")
        if k not in vis:
            vis.add(k); ferr.append(f)
    info["ferramenta"] = "; ".join(ferr)
    for chave, rx in (("servidor", r"servidor"), ("banco", r"banco"), ("tabelas", r"tabelas?")):
        m = re.search(rf"{rx}\s*[:\-]\s*([^\n*]+)", limpo, re.I)
        if m:
            info[chave] = m.group(1).strip(" *`.;")
    return info


def normalizar(path, title, content):
    m = RX_FICHA.search(path or "")
    prog = m.group("prog") if m else ""
    cod = m.group("cod").upper() if m else ""
    c = extrair_campos(content)
    nome = re.sub(r"^\s*IN\d+\s*[-–]\s*", "", (title or "").strip())
    # fórmula consolidada: regra explícita > metodologia > sintaxe
    formula = c.get("formula") or c.get("metodologia") or c.get("sintaxe") or ""
    rec = {
        "id": f"wiki-{prog}-{cod}".lower(),
        "codigo": cod, "programa": prog, "programa_status": "",
        "nome": nome,
        "descricao": c.get("descricao", ""), "interpretacao": c.get("interpretacao", ""),
        "unidade": c.get("unidade", ""), "intervalo": c.get("intervalo", ""),
        "status_acesso": c.get("status_acesso", ""), "publico": _publico(c.get("status_acesso")),
        "fonte": c.get("fonte", ""), "periodicidade": c.get("periodicidade", ""),
        "data_inicio": c.get("data_inicio", ""), "desagregacao": c.get("desagregacao", ""),
        "formula": formula, "metodologia": c.get("metodologia", ""),
        "autoria": c.get("autoria", ""), "info_adicional": c.get("info_adicional", ""),
        # === onde está o dado / em que ferramenta ===
        # ferramenta/servidor/banco/tabelas/sintaxe vêm da página SI (enriquecer);
        # ferramentas_consulta/visdata/links saem da PRÓPRIA ficha (logo abaixo).
        "ferramenta": "", "servidor": "", "banco": "", "tabelas": "", "sintaxe": "",
        "ferramentas_consulta": [], "visdata": "",
        "links": extrair_links(content),
        "sintaxe_url": "", "bd_url": "",      # páginas-irmãs (SI e Base de Dados)
        "url": f"{BASE}/{path}",
    }
    _aplicar_ferramentas_consulta(rec)
    # qualidade: stub ("EM PROCESSO DE CRIAÇÃO") ou sem nenhum campo aproveitável
    rec["stub"] = "processo de cria" in _sem_acento(content or "")
    rec["completa"] = bool(rec["descricao"] or rec["formula"]) and not rec["stub"]
    _finalizar_texto_busca(rec)
    rec["content"] = content or ""          # markdown bruto, para reembedding/reparse
    return rec


def _aplicar_ferramentas_consulta(rec):
    """Deriva ferramentas_consulta e o atalho `visdata` a partir de rec['links']."""
    fc = [l for l in rec["links"] if l["tipo"] == "ferramenta"]
    rec["ferramentas_consulta"] = fc
    rec["visdata"] = next((l["url"] for l in fc
                           if "vis/data" in l["url"].lower() or "visdata" in _sem_acento(l["nome"] + l["url"])), "")


# rótulos legíveis -> texto_busca (indexação/embedding)
_LABELS = {"descricao": "Descrição", "interpretacao": "Interpretação",
           "unidade": "Unidade", "intervalo": "Intervalo de valores",
           "status_acesso": "Publicização", "fonte": "Fonte de dados",
           "periodicidade": "Periodicidade", "data_inicio": "Início da série",
           "desagregacao": "Desagregação territorial", "formula": "Fórmula de cálculo",
           "autoria": "Autoria do método", "info_adicional": "Informações complementares",
           "ferramenta": "Ferramenta/plataforma", "servidor": "Servidor",
           "banco": "Banco de dados", "tabelas": "Tabelas", "sintaxe": "Sintaxe/script"}


def _finalizar_texto_busca(rec):
    partes = [f"{rec['codigo']} — {rec['nome']}", f"Programa: {rec['programa']}"]
    for k, lab in _LABELS.items():
        if rec.get(k):
            partes.append(f"{lab}: {rec[k]}")
    if rec.get("ferramentas_consulta"):
        nomes = "; ".join(l["nome"] for l in rec["ferramentas_consulta"])
        partes.append(f"Ferramentas de consulta (onde ver o dado): {nomes}")
    rec["texto_busca"] = "\n".join(partes)


def _merge_links(rec, novos):
    urls = {l["url"] for l in rec["links"]}
    for l in novos:
        if l["url"] not in urls:
            urls.add(l["url"]); rec["links"].append(l)


def enriquecer(rec, si_content="", si_url="", bd_url=""):
    """Anexa à ficha a localização do dado a partir da página de sintaxe irmã,
    PRESERVANDO os links/ferramentas de consulta já extraídos da própria ficha."""
    rec["sintaxe_url"] = si_url
    rec["bd_url"] = bd_url
    if si_content:
        info = extrair_sintaxe(si_content)
        rec.update({k: info[k] for k in ("ferramenta", "servidor", "banco", "tabelas", "sintaxe")})
        _merge_links(rec, info["links"])
    _aplicar_ferramentas_consulta(rec)      # reavalia com os links mesclados
    _finalizar_texto_busca(rec)
    return rec


# ======================= acesso à API GraphQL =======================
def _gql(query, variables=None):
    import requests
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    r = requests.post(GRAPHQL, json={"query": query, "variables": variables or {}},
                      headers=headers, timeout=120)
    r.encoding = "utf-8"
    dados = r.json()
    if "errors" in dados:
        raise RuntimeError(f"GraphQL: {dados['errors']}")
    return dados["data"]


def _todas_paginas():
    # Esta instância Wiki.js cataloga TODAS as páginas como locale "en" (mesmo o
    # conteúdo em português), então NÃO filtramos por idioma — isso descartaria
    # tudo. Mantemos a lista completa retornada pela API.
    data = _gql("{ pages { list(orderBy: PATH) { id path title locale } } }")
    return list(data["pages"]["list"])


def conteudo_pagina(pid):
    q = "query($id:Int!){ pages { single(id:$id){ path title content } } }"
    pg = _gql(q, {"id": pid})["pages"]["single"]
    # algumas fichas foram criadas no editor HTML da wiki, não em markdown —
    # normaliza para o mesmo formato antes de qualquer extração usar o conteúdo.
    pg["content"] = _gm.normalizar_conteudo_pagina(pg.get("content", ""))
    return pg


# sintaxe irmã: home/SI/<prog>/IN###  ·  base de dados: <root>/<prog>/BD
RX_SINTAXE = re.compile(r"(?:^|/)home/SI/(?P<prog>[^/]+)/(?P<cod>IN\d+)\b", re.I)
RX_BD = re.compile(r"(?:^|/)home/(?P<raiz>DS|E)/(?P<prog>[^/]+)/BD\b", re.I)


# ---- fichas ----
def coletar_da_api():
    todas = _todas_paginas()
    paginas = [p for p in todas if RX_FICHA.search(p["path"])]
    status_prog = _mapa_status(todas)        # slug -> vigente/descontinuado
    # índices das páginas-irmãs que dizem ONDE o dado está
    si_idx, bd_idx = {}, {}
    for p in todas:
        ms = RX_SINTAXE.search(p["path"])
        if ms:
            si_idx[(ms.group("prog").lower(), ms.group("cod").upper())] = p
        mb = RX_BD.search(p["path"])
        if mb:
            bd_idx.setdefault(mb.group("prog").lower(), p)
    print(f"fichas de indicador encontradas: {len(paginas)} | "
          f"páginas de sintaxe: {len(si_idx)} | bases de dados: {len(bd_idx)}")
    regs, com_sintaxe = [], 0
    for i, p in enumerate(paginas, 1):
        try:
            pg = conteudo_pagina(p["id"])
            rec = normalizar(pg["path"], pg["title"], pg["content"])
            si = si_idx.get((rec["programa"].lower(), rec["codigo"].upper()))
            bd = bd_idx.get(rec["programa"].lower())
            si_content, si_url = "", ""
            if si:
                si_url = f"{BASE}/{si['path']}"
                si_content = conteudo_pagina(si["id"]).get("content", "")
            enriquecer(rec, si_content, si_url, f"{BASE}/{bd['path']}" if bd else "")
            rec["programa_status"] = status_prog.get(rec["programa"].lower(), "")
            if rec["ferramenta"] or rec["sintaxe"]:
                com_sintaxe += 1
            regs.append(rec)
        except Exception as e:
            print(f"  falha em {p['path']}: {e}")
        if i % 50 == 0:
            print(f"  ... {i}/{len(paginas)}")
    print(f"fichas com localização de dado (ferramenta/sintaxe): {com_sintaxe}")
    return regs


def coletar_de_amostra(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        fichas = json.load(f)
    return [normalizar(x["path"], x.get("title", ""), x.get("content", "")) for x in fichas]


# ---- programas: listas curadas + ficha completa ----
# Listas controladas na raiz da wiki (entradas da home):
#   home/DS = programas/sistemas VIGENTES   ·   home/E = NÃO-VIGENTES/descontinuados
# Cada item "N. [Nome](/home/{DS,E}/SLUG)" aponta para a FICHA do programa, com
# descrição/objetivo, legislação, público-alvo, governança, datas, etc. O SLUG é o
# código que liga o programa aos seus indicadores (home/{DS,E}/SLUG/I/IN###).
RX_ITEM_PROG = re.compile(r"\[([^\]]+)\]\(/home/(DS|E|SI)/([A-Za-z0-9_&.-]+)\)")
_SLUG_NAO_PROG = {"i", "bd", "si", "ds", "e", "pe", "cc", "f"}
# fontes das listas curadas e o status que cada uma carimba
_LISTAS_PROG = (("home/DS", "vigente"), ("home/SI", "vigente"), ("home/E", "descontinuado"))


def parse_lista_curada(content, fonte="", status="vigente"):
    """Programas/sistemas de uma lista curada. Preserva o root do link (DS/E)
    para montar a URL correta da ficha (um item da lista de descontinuados pode
    apontar para uma ficha que ainda mora em home/DS)."""
    regs, tipo = [], "programa"
    for raw in (content or "").splitlines():
        l = raw.strip()
        h = _sem_acento(l)
        if l.startswith("#") or re.match(r"\*\*.+\*\*", l):
            if "sistema" in h:
                tipo = "sistema"
            elif any(k in h for k in ("politica", "programa", "beneficio", "servico", "acao")):
                tipo = "programa"
            continue
        m = RX_ITEM_PROG.search(l)
        if not m:
            continue
        root, slug = m.group(2), m.group(3)
        if slug.lower() in _SLUG_NAO_PROG:
            continue
        root = "E" if root == "E" else "DS"
        selo = "ouro" if "ouro" in h else ("prata" if "prata" in h else "")
        regs.append({"codigo": slug, "programa": m.group(1).strip(" *`"), "tipo": tipo,
                     "selo": selo, "status": status, "root": root,
                     "url": f"{BASE}/home/{root}/{slug}", "fonte": fonte})
    return regs


def _contar_indicadores(paginas):
    cont = {}
    for p in paginas:
        m = RX_FICHA.search(p["path"])
        if m:
            k = m.group("prog").lower()
            cont[k] = cont.get(k, 0) + 1
    return cont


def _mapa_status(todas):
    """slug (minúsculo) -> 'vigente'/'descontinuado', a partir das listas curadas."""
    mapa = {}
    for path, status in (("home/DS", "vigente"), ("home/E", "descontinuado")):
        p = next((q for q in todas if q["path"] == path), None)
        if p:
            for r in parse_lista_curada(conteudo_pagina(p["id"])["content"], "", status):
                mapa.setdefault(r["codigo"].lower(), status)
    return mapa


# campos estruturados da ficha de programa que viram colunas/texto_busca
_CAMPOS_PROG = ["descricao", "publico_alvo", "legislacao", "orgao_gestor", "orgao_superior",
                "data_inicio", "data_encerramento", "resultados", "governanca",
                "implementacao", "atores", "marcos", "info_adicional"]
_LABELS_PROG = {"descricao": "Descrição e objetivo", "publico_alvo": "Público-alvo",
                "legislacao": "Instrumentos legais", "orgao_gestor": "Órgão gestor",
                "orgao_superior": "Órgão superior", "data_inicio": "Início/criação",
                "data_encerramento": "Encerramento", "resultados": "Resultados esperados",
                "governanca": "Governança", "implementacao": "Implementação/execução",
                "atores": "Atores envolvidos", "marcos": "Marcos relevantes",
                "info_adicional": "Informações complementares"}


def _enriquecer_programa(r, idx):
    """Busca a ficha do programa (home/DS ou home/E) e extrai os campos + texto_busca."""
    for c in _CAMPOS_PROG:
        r[c] = ""
    r["links"], r["content"], r["nome_oficial"] = [], "", r["programa"]
    pg = idx.get(f"home/{r['root']}/{r['codigo']}") or idx.get(f"home/DS/{r['codigo']}") \
        or idx.get(f"home/E/{r['codigo']}")
    if not pg:
        r["texto_busca"] = f"{r['programa']} ({r['codigo']})"
        return
    conteudo = conteudo_pagina(pg["id"])
    r["url"] = f"{BASE}/{conteudo['path']}"
    r["nome_oficial"] = (conteudo.get("title") or r["programa"]).strip()
    campos = extrair_campos(conteudo["content"], ROTULOS_PROGRAMA)
    for c in _CAMPOS_PROG:
        if campos.get(c):
            r[c] = campos[c]
    r["links"] = extrair_links(conteudo["content"])
    r["content"] = conteudo["content"] or ""
    partes = [f"{r['programa']} ({r['codigo']})", f"Tipo: {r['tipo']} · Status: {r['status']}"]
    for c in _CAMPOS_PROG:
        if r[c]:
            partes.append(f"{_LABELS_PROG[c]}: {r[c]}")
    r["texto_busca"] = "\n".join(partes)


def coletar_programas_da_api(com_ficha=True):
    todas = _todas_paginas()
    regs = []
    for path, status in _LISTAS_PROG:
        p = next((q for q in todas if q["path"] == path), None)
        if p:
            novos = parse_lista_curada(conteudo_pagina(p["id"])["content"], f"{BASE}/{path}", status)
            print(f"  {path}: {len(novos)} itens ({status})")
            regs += novos
    cont = _contar_indicadores(todas)
    idx = {q["path"]: q for q in todas}
    vistos, out = set(), []                 # dedup por slug (vigente vence empate)
    for r in regs:
        k = r["codigo"].lower()
        if k in vistos:
            continue
        vistos.add(k)
        r["n_indicadores"] = cont.get(k, 0)
        if com_ficha:
            _enriquecer_programa(r, idx)
        out.append(r)
    return out


def coletar_programas_de_amostra(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        dados = json.load(f)
    if isinstance(dados, dict):
        dados = [dados]
    regs = []
    for x in dados:
        regs += parse_lista_curada(x.get("content", ""), x.get("path", x.get("url", "")))
    vistos, out = set(), []
    for r in regs:
        k = r["codigo"].lower()
        if k and k not in vistos:
            vistos.add(k); r["n_indicadores"] = 0; out.append(r)
    return out


# ---- ferramentas informacionais (home/F) ----
RX_FICHA_FERRAMENTA = re.compile(r"^home/F/[A-Za-z0-9_&.-]+$")
_CAMPOS_FER = ["descricao", "para_que_serve", "permite_fazer", "resultados", "fonte_dados",
               "tecnologias", "publico_alvo", "acesso", "privacidade", "limitacoes",
               "apoio", "info_gerais", "info_adicional"]
_LABELS_FER = {"descricao": "Descrição", "para_que_serve": "Para que serve",
               "permite_fazer": "O que permite fazer", "resultados": "Como aparecem os resultados",
               "fonte_dados": "De onde vêm os dados", "tecnologias": "Tecnologias utilizadas",
               "publico_alvo": "Público-alvo / quem acessa", "acesso": "Como acessar",
               "privacidade": "Privacidade e segurança", "limitacoes": "Limitações",
               "apoio": "Apoio ao usuário", "info_gerais": "Informações gerais",
               "info_adicional": "Observações complementares"}


def normalizar_ferramenta(path, title, content):
    c = extrair_campos(content, ROTULOS_FERRAMENTA)
    slug = path.split("/")[-1]
    nome = re.sub(r"\s+", " ", (c.get("nome_completo") or title or slug)).strip()
    rec = {"id": f"wiki-ferramenta-{slug}".lower(), "codigo": slug, "nome": nome,
           "sigla": "", "lancamento": "", "unidade_responsavel": ""}
    for k in _CAMPOS_FER:
        rec[k] = c.get(k, "")
    # extrai sigla/lançamento/unidade do bloco "Informações gerais"
    ig = c.get("info_gerais", "")
    for chave, rx in (("sigla", r"abrevia[cç][oõ]es?/?\s*sigla|sigla"),
                      ("lancamento", r"lan[cç]amento"),
                      ("unidade_responsavel", r"unidade respons")):
        m = re.search(rf"(?:{rx})\s*[:\-]\s*([^\n]+)", ig, re.I)
        if m:
            rec[chave] = m.group(1).strip(" *`.")
    rec["links"] = extrair_links(content)
    rec["url"] = f"{BASE}/{path}"
    rec["content"] = content or ""
    partes = [f"{nome} ({slug})"]
    if rec["sigla"]:
        partes.append(f"Sigla: {rec['sigla']}")
    for k in _CAMPOS_FER:
        if rec[k]:
            partes.append(f"{_LABELS_FER[k]}: {rec[k]}")
    rec["texto_busca"] = "\n".join(partes)
    return rec


def coletar_ferramentas_da_api():
    todas = _todas_paginas()
    fichas = [p for p in todas if RX_FICHA_FERRAMENTA.match(p["path"])]
    print(f"fichas de ferramenta encontradas: {len(fichas)}")
    out = []
    for p in fichas:
        try:
            pg = conteudo_pagina(p["id"])
            out.append(normalizar_ferramenta(pg["path"], pg["title"], pg["content"]))
        except Exception as e:
            print(f"  falha em {p['path']}: {e}")
    return out


def coletar_ferramentas_de_amostra(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        dados = json.load(f)
    if isinstance(dados, dict):
        dados = [dados]
    return [normalizar_ferramenta(x.get("path", ""), x.get("title", ""), x.get("content", "")) for x in dados]


# ======================= saídas =======================
# CSV: visão tabular enxuta (sem content/texto_busca/sintaxe, que vão só no JSONL)
CAMPOS_CSV = ["id", "codigo", "programa", "programa_status", "nome", "completa",
              "stub", "unidade", "periodicidade", "data_inicio", "publico",
              "status_acesso", "ferramenta", "servidor", "banco", "tabelas",
              "visdata", "fonte", "formula", "intervalo", "desagregacao",
              "descricao", "sintaxe_url", "bd_url", "url"]


def gravar(regs, base="catalogo_wiki_indicadores"):
    with open(f"{base}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        w.writeheader()
        for r in regs:
            w.writerow(r)
    with open(f"{base}.jsonl", "w", encoding="utf-8") as f:
        for r in regs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    catalogo_html.render(
        f"{base}.html",
        titulo="SIG-Evidência · Fichas de Indicadores (Documenta Wiki)",
        subtitulo="Fichas do Padrão de Indicadores; indicadores de acesso restrito ficam marcados",
        fonte_url=BASE, total_origem=None,
        colunas=[
            {"key": "codigo", "label": "Código", "tipo": "text"},
            {"key": "nome", "label": "Indicador", "tipo": "long"},
            {"key": "programa", "label": "Programa", "tipo": "text"},
            {"key": "programa_status", "label": "Situação do programa", "tipo": "text"},
            {"key": "periodicidade", "label": "Periodicidade", "tipo": "text"},
            {"key": "acesso", "label": "Acesso", "tipo": "text"},
            {"key": "ferramenta", "label": "Calculado em", "tipo": "text"},
            {"key": "onde", "label": "Servidor · banco · tabelas", "tipo": "long"},
            {"key": "qualidade", "label": "Qualidade", "tipo": "text"},
            {"key": "visdata", "label": "VisData", "tipo": "link"},
            {"key": "_link", "label": "Ficha · sintaxe · onde ver", "tipo": "link"},
        ],
        # linhas enxutas: não embute content/texto_busca/sintaxe (mantém o HTML leve)
        linhas=[{"codigo": r["codigo"], "nome": r["nome"], "programa": r["programa"],
                 "programa_status": r.get("programa_status") or "—",
                 "periodicidade": r["periodicidade"], "ferramenta": r["ferramenta"] or "—",
                 "onde": " · ".join(x for x in (r["servidor"], r["banco"], r["tabelas"]) if x) or "—",
                 "acesso": "público" if r["publico"] else ("restrito" if r["publico"] is False else "—"),
                 "qualidade": "completa" if r["completa"] else ("stub" if r["stub"] else "incompleta"),
                 "visdata": [("abrir", r["visdata"])] if r["visdata"] else [],
                 "tem_visdata": "sim" if r["visdata"] else "não",
                 # demais ferramentas de consulta (VisData tem coluna própria)
                 "_link": [("ficha", r["url"])]
                          + ([("sintaxe", r["sintaxe_url"])] if r["sintaxe_url"] else [])
                          + [(l["nome"], l["url"]) for l in r["ferramentas_consulta"]
                             if l["url"] != r["visdata"]]}
                for r in regs],
        filtros=["programa", "programa_status", "periodicidade", "acesso", "ferramenta",
                 "qualidade", "tem_visdata"],
        filtro_labels={"tem_visdata": "Tem VisData?", "programa_status": "Situação do programa"},
    )


def gravar_programas(regs, base="catalogo_programas"):
    # CSV enxuto (sem content/texto_busca/links, que ficam só no JSONL)
    cols = ["codigo", "programa", "nome_oficial", "tipo", "status", "selo", "n_indicadores",
            "orgao_gestor", "data_inicio", "data_encerramento", "publico_alvo",
            "legislacao", "descricao", "url"]
    with open(f"{base}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in regs:
            w.writerow(r)
    with open(f"{base}.jsonl", "w", encoding="utf-8") as f:
        for r in regs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    catalogo_html.render(
        f"{base}.html",
        titulo="SIG-Evidência · Programas e Sistemas (Documenta Wiki)",
        subtitulo="Fichas de programas/sistemas vigentes (home/DS) e descontinuados (home/E), com descrição, legislação e público-alvo. O código liga cada programa aos seus indicadores.",
        fonte_url=BASE, total_origem=None,
        colunas=[
            {"key": "codigo", "label": "Código", "tipo": "text"},
            {"key": "programa", "label": "Programa / sistema", "tipo": "long"},
            {"key": "tipo", "label": "Tipo", "tipo": "text"},
            {"key": "status", "label": "Situação", "tipo": "text"},
            {"key": "selo", "label": "Selo", "tipo": "text"},
            {"key": "n_indicadores", "label": "Indicadores", "tipo": "text"},
            {"key": "descricao", "label": "Descrição e objetivo", "tipo": "long"},
            {"key": "publico_alvo", "label": "Público-alvo", "tipo": "long"},
            {"key": "_link", "label": "Ficha", "tipo": "link"},
        ],
        linhas=[{"codigo": r["codigo"], "programa": r["programa"], "tipo": r["tipo"],
                 "status": r["status"], "selo": r.get("selo") or "—",
                 "n_indicadores": r.get("n_indicadores", 0),
                 "descricao": r.get("descricao") or "—",
                 "publico_alvo": r.get("publico_alvo") or "—",
                 "_link": [("abrir", r["url"])]} for r in regs],
        filtros=["tipo", "status", "selo"],
    )


def gravar_ferramentas(regs, base="catalogo_ferramentas"):
    cols = ["id", "codigo", "nome", "sigla", "lancamento", "unidade_responsavel",
            "descricao", "para_que_serve", "tecnologias", "fonte_dados", "publico_alvo",
            "acesso", "url"]
    with open(f"{base}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in regs:
            w.writerow(r)
    with open(f"{base}.jsonl", "w", encoding="utf-8") as f:
        for r in regs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    catalogo_html.render(
        f"{base}.html",
        titulo="SIG-Evidência · Ferramentas Informacionais (Documenta Wiki)",
        subtitulo="Fichas das ferramentas informacionais da Sagicad (home/F) — VisData, painéis, relatórios, etc.",
        fonte_url=BASE, total_origem=None,
        colunas=[
            {"key": "nome", "label": "Ferramenta", "tipo": "long"},
            {"key": "sigla", "label": "Sigla", "tipo": "text"},
            {"key": "descricao", "label": "Descrição", "tipo": "long"},
            {"key": "para_que_serve", "label": "Para que serve", "tipo": "long"},
            {"key": "tecnologias", "label": "Tecnologias", "tipo": "text"},
            {"key": "unidade_responsavel", "label": "Unidade responsável", "tipo": "text"},
            {"key": "_link", "label": "Ficha", "tipo": "link"},
        ],
        linhas=[{"nome": r["nome"], "sigla": r.get("sigla") or "—",
                 "descricao": r.get("descricao") or "—",
                 "para_que_serve": r.get("para_que_serve") or "—",
                 "tecnologias": r.get("tecnologias") or "—",
                 "unidade_responsavel": r.get("unidade_responsavel") or "—",
                 "_link": [("abrir", r["url"])]} for r in regs],
        filtros=[],
    )


def _erro_api(e):
    print(f"ERRO ao acessar a API GraphQL: {e}")
    print("Provável necessidade de token de leitura. Peça à DMA/SAGICAD "
          "(wiki@mds.gov.br) e rode com: export WIKI_TOKEN=...")


def main():
    args = sys.argv[1:]
    programas = "--programas" in args
    ferramentas = "--ferramentas" in args
    amostra = None
    if "--amostra" in args:
        i = args.index("--amostra")
        amostra = args[i + 1] if i + 1 < len(args) else None

    if ferramentas:
        try:
            regs = coletar_ferramentas_de_amostra(amostra) if amostra else coletar_ferramentas_da_api()
        except Exception as e:
            _erro_api(e); return
        gravar_ferramentas(regs)
        print(f"ferramentas: {len(regs)}")
        print("gerados: catalogo_ferramentas.csv, .jsonl e .html")
        return

    if programas:
        if amostra:
            regs = coletar_programas_de_amostra(amostra)
            print(f"programas processados (amostra): {len(regs)}")
        else:
            try:
                regs = coletar_programas_da_api()
            except Exception as e:
                _erro_api(e); return
        gravar_programas(regs)
        prog = sum(1 for r in regs if r["tipo"] == "programa")
        vig = sum(1 for r in regs if r["status"] == "vigente")
        com_ficha = sum(1 for r in regs if r.get("descricao"))
        com_ind = sum(1 for r in regs if r.get("n_indicadores"))
        print(f"itens: {len(regs)} | programas: {prog} · sistemas: {len(regs) - prog} | "
              f"vigentes: {vig} · descontinuados: {len(regs) - vig}")
        print(f"com ficha descritiva: {com_ficha} · com indicadores vinculados: {com_ind}")
        print("gerados: catalogo_programas.csv, .jsonl e .html")
        return

    if amostra:
        regs = coletar_de_amostra(amostra)
        print(f"fichas processadas (amostra): {len(regs)}")
    else:
        try:
            regs = coletar_da_api()
        except Exception as e:
            print(f"ERRO ao acessar a API GraphQL: {e}")
            print("Provável necessidade de token de leitura. Peça à DMA/SAGICAD "
                  "(wiki@mds.gov.br) e rode com: export WIKI_TOKEN=...")
            return
    gravar(regs)
    publicos = sum(1 for r in regs if r["publico"] is True)
    restritos = sum(1 for r in regs if r["publico"] is False)
    completas = sum(1 for r in regs if r["completa"])
    stubs = sum(1 for r in regs if r["stub"])
    print(f"públicos: {publicos} · restritos: {restritos} · sem status: {len(regs) - publicos - restritos}")
    print(f"completas: {completas} · stubs: {stubs} · incompletas: {len(regs) - completas - stubs}")
    print("gerados: catalogo_wiki_indicadores.csv, .jsonl e .html")


if __name__ == "__main__":
    main()
