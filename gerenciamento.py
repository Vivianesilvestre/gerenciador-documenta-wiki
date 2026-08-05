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


# ======================= caixinha de orientação (> texto {.is-info}) =======================
# A wiki estiliza a instrução/placeholder de cada campo como uma citação
# markdown ("> texto...") seguida do marcador de atributo "{.is-info}" (ou
# similar), que faz o Wiki.js renderizar aquilo como uma "caixinha" de aviso.
# Isso é um padrão ESTRUTURAL, não um texto a ser comparado por similaridade:
# se sobrar QUALQUER texto de resposta FORA dessa caixinha, o campo foi
# preenchido — mesmo que a caixinha em si ainda contenha a instrução original
# e mesmo que a resposta seja bem mais curta que a instrução (isso é comum:
# muita gente digita a resposta abaixo da caixinha, sem apagá-la). Antes desta
# marcação, a comparação por similaridade tratava caixinha+resposta como um
# blob só, e uma resposta curta "diluída" numa instrução longa batia como
# "cobertura alta" e era classificada (errado) como não preenchida.
_RX_CAIXA_BRUTA = re.compile(
    r"(?m)^((?:[ \t]*>[^\n]*\n?)+)[ \t]*\n?[ \t]*\{\.is-[a-z]+\}[ \t]*\n?")
_RX_CAIXA_SENTINELA = re.compile(r"\x02(.*?)\x03", re.S)


def _marcar_caixas_orientacao(texto):
    """Troca cada bloco '> ...\\n{.is-info}' por um trecho delimitado por
    sentinelas (\\x02...\\x03), preservando o texto da caixinha (sem o '>')
    para ser recuperado depois, campo a campo, por _separar_caixa_orientacao."""
    def _sub(m):
        linhas = [re.sub(r"^[ \t]*>[ \t]?", "", l) for l in m.group(1).splitlines()]
        return "\x02" + "\n".join(linhas).strip() + "\x03\n"
    return _RX_CAIXA_BRUTA.sub(_sub, texto or "")


def _separar_caixa_orientacao(conteudo):
    """(texto_fora_da_caixinha, texto_dentro_da(s)_caixinha(s)) a partir do
    conteúdo de um campo já marcado por _marcar_caixas_orientacao."""
    fora = _RX_CAIXA_SENTINELA.sub("", conteudo or "")
    dentro = "\n".join(_RX_CAIXA_SENTINELA.findall(conteudo or ""))
    return fora, dentro


def texto_visivel(conteudo):
    """Remove marcadores internos de caixinha de orientação de um valor de
    campo, para exibição (não usar para classificação)."""
    return _RX_CAIXA_SENTINELA.sub("", conteudo or "").strip()


# ======================= campo preenchido? =======================
def campo_preenchido(conteudo, texto_padrao, cfg, folga_tamanho=1.2):
    """
    Decide se um campo foi de fato preenchido (True) ou se ainda está com o
    texto-padrão/vazio (False).

    Regras, em ordem:
      0. Se há texto fora da caixinha de orientação (ver acima) que NÃO seja,
         ele mesmo, um pedaço da própria instrução, preenchido — não importa
         o que sobrou dentro da caixinha.
      1. Vazio (ou só o marcador "Em construção") -> não preenchido.
      2. Contém uma das frases-padrão de resposta curta válida (ex.: "Indicador
         público.", "Não há informações relevantes adicionais.") -> preenchido
         (é uma escolha deliberada, mesmo que o texto seja curto) — desde que
         o campo não seja, no geral, ainda basicamente a instrução inteira.
      3. Sem texto-padrão de referência para comparar -> qualquer conteúdo conta
         como preenchido.
      4. Compara com o texto-padrão: se a maior parte da instrução ainda está
         lá (alta cobertura) E o trecho coincidente é justamente o INÍCIO do
         texto-padrão (assinatura de instrução não removida) E não foi
         acrescentado conteúdo real substancial, é considerado não preenchido.
         Caso contrário, preenchido.
    """
    ref_bruto = normalizar(texto_padrao)
    fora, dentro = _separar_caixa_orientacao(conteudo)
    tem_caixa = bool(dentro)
    if tem_caixa:
        # havia caixinha(s) de orientação neste campo: texto fora dela normal-
        # mente é resposta real. MAS a marcação da caixinha depende de linhas
        # consecutivas começando com ">" — um comentário HTML (<!-- ... -->)
        # no MEIO da instrução (visto no campo D18 em branco) quebra essa
        # continuidade e faz sobrar, fora da caixinha, um pedaço da própria
        # instrução ainda intacta (não uma resposta digitada por alguém). Por
        # isso só confiamos no texto de fora se ele NÃO for, em boa parte, um
        # trecho literal do texto-padrão — senão juntamos tudo (fora + dentro)
        # e comparamos como um campo só, mais abaixo.
        fora_n = normalizar(fora)
        if fora_n:
            eh_so_instrucao_vazada = False
            if ref_bruto:
                sm_fora = SequenceMatcher(None, ref_bruto, fora_n)
                cobertura_fora = (sum(b.size for b in sm_fora.get_matching_blocks() if b.size >= 10)
                                   / max(len(fora_n), 1))
                eh_so_instrucao_vazada = cobertura_fora >= 0.6
            if not eh_so_instrucao_vazada:
                return True
            conteudo = fora + "\n" + dentro
        else:
            conteudo = dentro
    # sem caixinha nenhuma (campo sem essa marcação, ex.: ficha antiga) ->
    # segue o comportamento de sempre, comparando o campo inteiro com o
    # texto-padrão.

    c = normalizar(conteudo)
    if not c:
        return False
    for placeholder in cfg.get("indicador_novo_placeholder_vazio", []):
        if placeholder in c and len(c) < len(placeholder) + 40:
            return False

    ref = ref_bruto

    # frases-padrão de resposta curta válida (ex.: "Indicador público.",
    # "Sintaxe indisponível - memória de cálculo registrada..."): só contam
    # como resposta se o campo NÃO for basicamente a instrução inteira ainda
    # intacta. Isso importa porque várias instruções enumeram as próprias
    # alternativas válidas como exemplo (ex.: a instrução do campo de sintaxe
    # lista as 3 opções, incluindo o texto "sintaxe indisponível" dentro
    # dela) — sem essa guarda, um campo 100% intocado "bate" com a frase só
    # por ela aparecer no meio da instrução nunca apagada, e é contado (errado)
    # como preenchido. Sem texto-padrão para comparar o tamanho, aceita direto.
    for frase in cfg.get("frases_fallback_preenchido", []):
        if frase in c and (not ref or len(c) <= len(ref) * 0.5):
            return True

    if not ref:
        # não temos o texto-padrão exato deste campo para comparar (ex.: um
        # tipo de ficha ainda não catalogado em padroes_fichas.json). Se havia
        # uma caixinha de orientação e nada foi digitado fora dela, o mais
        # seguro é assumir que ainda é a instrução (é para isso que a
        # caixinha existe); sem caixinha nenhuma, não há como saber — mantém
        # o comportamento de sempre (considera preenchido).
        return not tem_caixa

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
    # a marcação da caixinha (que consome o "{.is-...}") precisa vir ANTES de
    # qualquer remoção desse marcador, senão perdemos o sinal de onde a
    # caixinha termina; o que sobrar de "{.is-...}" sem bloco de citação na
    # frente (caso raro) é limpo depois.
    texto = _RX_INFOBOX.sub("", _marcar_caixas_orientacao(_RX_COMENTARIO.sub("", markdown or "")))
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
    texto = _RX_INFOBOX.sub("", _marcar_caixas_orientacao(_RX_COMENTARIO.sub("", markdown or "")))
    # separador aceita hífen, en-dash, em-dash ou dois-pontos (autocorreção do
    # Word/editor às vezes troca "-" por "–"/"—"); marcador antes do código
    # aceita vários símbolos de lista OU negrito (ex.: "**A1 – Código...**")
    # e também um item de lista que embute um cabeçalho markdown (ex.:
    # "- ### A1 - Código único da variável", formato real visto na ficha de
    # variável — o "-" é o marcador de lista e "###" vira negrito/destaque
    # visual no navegador, mas no markdown bruto os dois aparecem juntos).
    rx_item = re.compile(
        r"(?m)^[ \t]*[▸‣►\-*•]{0,3}[ \t]*#{0,6}[ \t]*(" + "|".join(re.escape(c) for c in codigos)
        + r")\b[ \t]*[-–—:][ \t]*[^\n]*$",
        re.IGNORECASE)
    marcas = list(rx_item.finditer(texto))
    campos = {}
    for i, m in enumerate(marcas):
        codigo = m.group(1).lower()
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        corpo = texto[m.end():fim]
        corpo = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]*bloco\s+[a-z]\b.*$", "", corpo, flags=re.IGNORECASE)
        corpo = re.sub(r"[*`>]", "", corpo).strip()
        campos[codigo] = corpo
    return campos


# ======================= detecção do modelo da ficha (antigo x novo) =======================
_RX_MODELO_NOVO = re.compile(
    r"bloco\s+[a-f]\s*[:\-–—]|(?:^|\n)\s*[▸‣►\-*•]{0,3}\s*#{0,6}\s*[a-f]\d{1,2}\s*[-–—:]", re.IGNORECASE)


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
