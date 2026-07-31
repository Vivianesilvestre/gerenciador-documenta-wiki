"""
gerenciamento.py — motor de classificação da situação de preenchimento das
fichas da Documenta Wiki (MDS).

Este módulo NÃO acessa a wiki. Ele só sabe comparar o texto real de um campo
com o texto-padrão (instrução/placeholder) que a plataforma deixa naquele
campo quando ele nunca foi preenchido. A partir disso, classifica cada ficha
em:

    não documentada  -> todos os campos avaliados ainda têm o texto-padrão
    iniciada         -> parte dos campos foi preenchida
    documentada      -> todos os campos avaliados foram preenchidos

Os textos-padrão ficam em padroes_fichas.json (mesma pasta), não no código —
se a SAGICAD mudar a redação das instruções nas fichas, edite o JSON.

Uso típico (por outro script):

    import gerenciamento as gm
    cfg = gm.carregar_padroes()
    situacao, detalhe = gm.classificar_ficha(
        campos, cfg["indicador_antigo"], list(cfg["indicador_antigo"]), cfg=cfg)
"""
import html as _html
import json
import os
import re
import unicodedata
from difflib import SequenceMatcher

_AQUI = os.path.dirname(os.path.abspath(__file__))
_CAMINHO_PADRAO = os.path.join(_AQUI, "padroes_fichas.json")


def carregar_padroes(caminho=None):
    with open(caminho or _CAMINHO_PADRAO, encoding="utf-8") as f:
        return json.load(f)


# ======================= páginas escritas no editor HTML =======================
# A Documenta Wiki permite alternar entre editor markdown e editor HTML/rich-text
# por página. Quando uma ficha foi criada no editor HTML, o "content" que a API
# devolve vem em HTML puro (<h1>, <p>, <a href=...>), não em markdown — e nesse
# caso o extrator de cabeçalhos markdown não acha nenhuma seção, jogando a
# página inteira (com as tags) dentro do primeiro campo. normalizar_conteudo_pagina
# converte esse HTML para o equivalente em markdown simples (cabeçalhos, links)
# antes de qualquer extração, para os dois formatos caírem no mesmo motor.
_RX_HTML_A = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
_RX_HTML_HEAD = re.compile(r'<h([1-6])[^>]*>(.*?)</h\1>', re.I | re.S)
_RX_HTML_QUEBRA = re.compile(r'</?(?:p|div|li|br|tr)\b[^>]*>', re.I)
_RX_HTML_TAG = re.compile(r'<[^>]+>')


def normalizar_conteudo_pagina(texto):
    """Se o texto tiver tags HTML, converte para markdown equivalente
    (cabeçalhos, links) e remove o resto das tags. Se não tiver, devolve como
    veio — chamar isso sempre, mesmo em conteúdo já em markdown, é seguro."""
    if not texto or "<" not in texto:
        return texto or ""
    t = texto
    t = _RX_HTML_A.sub(lambda m: f"[{_RX_HTML_TAG.sub('', m.group(2)).strip()}]({m.group(1)})", t)
    t = _RX_HTML_HEAD.sub(
        lambda m: "\n" + "#" * int(m.group(1)) + " " + _RX_HTML_TAG.sub("", m.group(2)).strip() + "\n", t)
    t = _RX_HTML_QUEBRA.sub("\n", t)
    t = _RX_HTML_TAG.sub(" ", t)
    t = _html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", t)
    return t.strip()


# ======================= normalização de texto =======================
_RX_MD = re.compile(r"[*_`>#\[\]()]")
_RX_WS = re.compile(r"\s+")


def normalizar(texto):
    """minúsculas, sem acento, sem marcação markdown, espaços colapsados."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = t.lower()
    t = _RX_MD.sub(" ", t)
    t = _RX_WS.sub(" ", t).strip()
    return t


# ======================= campo preenchido? =======================
def campo_preenchido(conteudo, texto_padrao, cfg, folga_tamanho=1.2):
    """
    Decide se um campo foi de fato preenchido (True) ou se ainda está com o
    texto-padrão/vazio (False).

    Regras, em ordem:
      1. Vazio (ou só o marcador "Em construção") -> não preenchido.
      2. Contém uma das frases-padrão de resposta curta válida (ex.: "Indicador
         público.", "Não há informações relevantes adicionais.") -> preenchido
         (é uma escolha deliberada, mesmo que o texto seja curto).
      3. Sem texto-padrão de referência para comparar -> qualquer conteúdo conta
         como preenchido.
      4. Compara com o texto-padrão: se a maior parte da instrução ainda está
         lá (alta cobertura) E o trecho coincidente é justamente o INÍCIO do
         texto-padrão (assinatura de instrução não removida) E não foi
         acrescentado conteúdo real substancial, é considerado não preenchido.
         Caso contrário, preenchido.
    """
    c = normalizar(conteudo)
    if not c:
        return False
    for placeholder in cfg.get("indicador_novo_placeholder_vazio", []):
        if placeholder in c and len(c) < len(placeholder) + 40:
            return False

    for frase in cfg.get("frases_fallback_preenchido", []):
        if frase in c:
            return True

    ref = normalizar(texto_padrao)
    if not ref:
        return True

    # só conta blocos de match "de peso" (>=10 caracteres); combinações curtas
    # como "de", "a", "municipio" aparecem por acaso em qualquer texto longo e
    # não são evidência de que o campo ainda tem a instrução-padrão.
    sm = SequenceMatcher(None, ref, c)
    blocos = [b for b in sm.get_matching_blocks() if b.size >= 10]
    match_total = sum(bloco.size for bloco in blocos)
    cobertura_c = match_total / max(len(c), 1)          # quanto de "c" é trecho literal do padrão

    # Uma instrução ainda não removida é, por construção, um recorte que
    # começa no INÍCIO do texto-padrão (o usuário simplesmente não apagou a
    # dica). Por isso exigimos que algum bloco de coincidência comece bem no
    # início de "ref". Isso distingue esse caso de uma resposta curta e
    # válida que por acaso reaproveita uma palavra/rótulo do MEIO do texto de
    # instrução (ex.: responder só "Processos/Atividades" ou "Restrito
    # (login interno)" num campo cuja instrução é um parágrafo enorme que,
    # entre outras coisas, lista essas opções) — nesse caso o trecho
    # coincidente fica no meio/fim do texto-padrão, não no início, e portanto
    # não conta como evidência de instrução ainda presente.
    comeca_como_instrucao = any(bloco.a <= 3 for bloco in blocos)

    if (cobertura_c >= 0.80 and comeca_como_instrucao
            and len(c) <= len(ref) * folga_tamanho and match_total >= 20):
        return False
    return True


# ======================= classificação de uma ficha inteira =======================
def classificar_ficha(campos, padroes_campo, campos_avaliar, cfg,
                       campos_fixos=None, campos_condicionais=None, condicao_ativa=True):
    """
    campos:            {chave: texto_extraido_da_pagina}
    padroes_campo:      {chave: texto_padrao_de_referencia}  (ex.: cfg["indicador_antigo"])
    campos_avaliar:     lista de chaves a considerar na classificação
    campos_fixos:       {chave: valor_esperado_constante} — campo que deve repetir sempre o
                         mesmo texto (ex.: "Órgão Superior"); conta como preenchido se não
                         estiver vazio, não é comparado a um texto-padrão de instrução.
    campos_condicionais: chaves que só entram na avaliação quando condicao_ativa é True
                         (ex.: "Data de Encerramento" só se aplica a programa descontinuado).

    Retorna (situacao:str, detalhe:{chave: bool}).
    """
    campos_fixos = campos_fixos or {}
    campos_condicionais = campos_condicionais or []
    detalhe = {}
    for chave in campos_avaliar:
        if chave in campos_condicionais and not condicao_ativa:
            continue
        conteudo = campos.get(chave, "") or ""
        if chave in campos_fixos:
            detalhe[chave] = bool(normalizar(conteudo))
            continue
        ref = padroes_campo.get(chave, "")
        detalhe[chave] = campo_preenchido(conteudo, ref, cfg)

    total = len(detalhe)
    preenchidos = sum(1 for v in detalhe.values() if v)
    if total == 0 or preenchidos == 0:
        situacao = "não documentada"
    elif preenchidos == total:
        situacao = "documentada"
    else:
        situacao = "iniciada"
    return situacao, detalhe


# ======================= extração genérica de campos por cabeçalho =======================
_RX_COMENTARIO = re.compile(r"<!--.*?-->", re.S)
_RX_HEADER_MD = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]*(.+?)[ \t]*$")
_RX_INFOBOX = re.compile(r"\{\.is-[a-z]+\}")
_RX_ITEM_LISTA = re.compile(r"(?m)^[ \t]*[▸‣►\-*][ \t]*(.+?)[ \t]*$")


def extrair_por_cabecalho(markdown, rotulos):
    """
    Extrai seções pelo cabeçalho markdown (## Rótulo), do fim de um cabeçalho
    até o início do próximo. `rotulos` é uma lista [(chave, regex_do_rotulo), ...],
    testada como prefixo do texto do cabeçalho (case-insensitive).
    """
    texto = _RX_INFOBOX.sub("", _RX_COMENTARIO.sub("", markdown or ""))
    heads = list(_RX_HEADER_MD.finditer(texto))
    campos = {}
    for i, m in enumerate(heads):
        rotulo = m.group(1)
        chave = None
        for k, rx in rotulos:
            if re.match(rf"\s*(?:{rx})", rotulo, re.IGNORECASE):
                chave = k
                break
        if not chave or chave in campos:
            continue
        fim = heads[i + 1].start() if i + 1 < len(heads) else len(texto)
        corpo = re.sub(r"[*`>]", "", texto[m.end():fim]).strip()
        campos[chave] = corpo
    return campos


def extrair_por_item_numerado(markdown, codigos):
    """
    Extrai os campos da FICHA NOVA de indicador, que usa itens de lista no
    formato "‣ A1 - Código único do indicador:" seguidos do conteúdo até o
    próximo item numerado ou o próximo cabeçalho de Bloco.
    `codigos` é a lista de prefixos esperados, ex.: ["A1","A2",...,"F23"].
    """
    texto = _RX_INFOBOX.sub("", _RX_COMENTARIO.sub("", markdown or ""))
    # separador aceita hífen, en-dash, em-dash ou dois-pontos (autocorreção do
    # Word/editor às vezes troca "-" por "–"/"—"); marcador antes do código
    # aceita vários símbolos de lista OU negrito (ex.: "**A1 – Código...**").
    rx_item = re.compile(
        r"(?m)^[ \t]*[▸‣►\-*•]{0,3}[ \t]*(" + "|".join(re.escape(c) for c in codigos)
        + r")\b[ \t]*[-–—:][ \t]*[^\n]*$",
        re.IGNORECASE)
    marcas = list(rx_item.finditer(texto))
    campos = {}
    for i, m in enumerate(marcas):
        codigo = m.group(1).lower()
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        corpo = texto[m.end():fim]
        corpo = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]*bloco\s+[a-f]\b.*$", "", corpo, flags=re.IGNORECASE)
        corpo = re.sub(r"[*`>]", "", corpo).strip()
        campos[codigo] = corpo
    return campos


# ======================= detecção do modelo da ficha (antigo x novo) =======================
_RX_MODELO_NOVO = re.compile(
    r"bloco\s+[a-f]\s*[:\-–—]|(?:^|\n)\s*[▸‣►\-*•]{0,3}\s*[a-f]\d{1,2}\s*[-–—:]", re.IGNORECASE)


def detectar_modelo(markdown):
    """'novo' se achar "Bloco A/B/.../F" ou itens "A1 -", "B6 -" etc; senão 'antigo'."""
    if _RX_MODELO_NOVO.search(markdown or ""):
        return "novo"
    return "antigo"


# ======================= publicação =======================
def esta_publicada(pagina_api, conteudo_markdown=""):
    """
    Prioriza o campo isPublished da API (mais confiável). Se ausente, cai para
    o aviso de tela "This page is not published." (texto que o Wiki.js mostra
    no topo, fora do markdown salvo — raramente aparece no `content`, mas
    verificamos por garantia).
    """
    if pagina_api is not None and "isPublished" in pagina_api:
        return bool(pagina_api["isPublished"])
    aviso = "this page is not published"
    return aviso not in normalizar(conteudo_markdown)
