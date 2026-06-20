"""Gerador de PDF — identidade visual Clemon Campos Advocacia.

Paleta e tipografia saem do DESIGN.md do escritório (verde escuro + dourado,
Cinzel para títulos, Montserrat para corpo). Estrutura inspirada no relatório
mensal feito à mão: capa, listagem das ações e cards de andamentos.
"""

from io import BytesIO
from collections import Counter
from datetime import datetime
import os
import re
import unicodedata

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ─────────────────────────────────────────────────────────── Paleta (DESIGN.md)
VERDE      = colors.HexColor("#253216")  # fundo institucional
SURFACE    = colors.HexColor("#2E3D1E")  # cards sobre o verde
SURFACE_2  = colors.HexColor("#374A26")
BORDA      = colors.HexColor("#3A4A28")
OURO       = colors.HexColor("#BF9C6F")  # dourado base
OURO_CLARO = colors.HexColor("#F2D9AF")  # dourado claro (topo do gradiente)
TEXTO      = colors.HexColor("#F4F0E6")  # off-white quente
TEXTO_MUTE = colors.HexColor("#B9B6A4")
ZEBRA      = colors.HexColor("#29371B")  # tom intermediário p/ linhas alternadas

A4_W, A4_H = A4

# ─────────────────────────────────────────────── Relevância (destaque, não filtro)
# Palavras que marcam um andamento como juridicamente relevante. Aqui NÃO removemos
# nada do relatório: só realçamos visualmente o que importa, para o cliente achar a
# olho. O filtro de fato (whitelist refinada com o Clemon) é decisão do backend.
PALAVRAS_RELEVANTES = (
    "sentenc", "decis", "despacho", "intima", "acordao", "julg",
    "deferid", "homolog", "audiencia", "citac", "transitad",
)


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _relevante(texto: str) -> bool:
    n = _norm(texto)
    return any(p in n for p in PALAVRAS_RELEVANTES)

# ─────────────────────────────────────────────────────────── Fontes (Cinzel + Montserrat)
_BASE  = os.path.dirname(os.path.abspath(__file__))
_FONTS = os.path.join(_BASE, "assets", "fonts")
_IMG   = os.path.join(_BASE, "assets", "img")

CINZEL      = "Helvetica"          # fallbacks se algo falhar no registro
CINZEL_SB   = "Helvetica-Bold"
MONT        = "Helvetica"
MONT_SB     = "Helvetica-Bold"
MONT_XB     = "Helvetica-Bold"


def _registrar_fontes() -> None:
    global CINZEL, CINZEL_SB, MONT, MONT_SB, MONT_XB
    mapa = {
        "Cinzel":             "Cinzel-Regular.ttf",
        "Cinzel-SemiBold":    "Cinzel-SemiBold.ttf",
        "Montserrat":         "Montserrat-Regular.ttf",
        "Montserrat-SemiBold":"Montserrat-SemiBold.ttf",
        "Montserrat-Bold":    "Montserrat-Bold.ttf",
        "Montserrat-ExtraBold":"Montserrat-ExtraBold.ttf",
    }
    try:
        for nome, arq in mapa.items():
            pdfmetrics.registerFont(TTFont(nome, os.path.join(_FONTS, arq)))
        pdfmetrics.registerFontFamily(
            "Montserrat", normal="Montserrat", bold="Montserrat-Bold",
            italic="Montserrat", boldItalic="Montserrat-Bold",
        )
        pdfmetrics.registerFontFamily(
            "Cinzel", normal="Cinzel", bold="Cinzel-SemiBold",
            italic="Cinzel", boldItalic="Cinzel-SemiBold",
        )
        CINZEL, CINZEL_SB = "Cinzel", "Cinzel-SemiBold"
        MONT, MONT_SB, MONT_XB = "Montserrat", "Montserrat-SemiBold", "Montserrat-ExtraBold"
    except Exception:
        pass  # mantém fallback Helvetica


_registrar_fontes()


def _img(nome: str) -> str | None:
    p = os.path.join(_IMG, nome)
    return p if os.path.exists(p) else None


# ─────────────────────────────────────────────────────────── Estilos de texto
def _p(name, **kw) -> ParagraphStyle:
    kw.setdefault("fontName", MONT)
    return ParagraphStyle(name, **kw)


S = {
    "eyebrow":   _p("eyebrow",   fontName=MONT_SB, fontSize=8,  textColor=OURO,
                    leading=11, alignment=TA_RIGHT),
    "secao":     _p("secao",     fontName=MONT_XB, fontSize=27, textColor=TEXTO,
                    leading=29, spaceAfter=2),
    "secao_sub": _p("secao_sub", fontName=MONT,    fontSize=12, textColor=TEXTO_MUTE,
                    leading=16, spaceAfter=6),
    "intro":     _p("intro",     fontName=MONT,    fontSize=9.5, textColor=TEXTO,
                    leading=15),
    # listagem
    "lista_parte": _p("lista_parte", fontName=MONT_SB, fontSize=9, textColor=TEXTO, leading=12),
    "lista_num":   _p("lista_num",   fontName=MONT_XB, fontSize=10, textColor=OURO,
                      leading=12, alignment=TA_RIGHT),
    # card
    "card_head": _p("card_head", fontName=CINZEL_SB, fontSize=10, textColor=VERDE,
                    leading=12, alignment=TA_CENTER),
    "mov":       _p("mov",       fontName=MONT, fontSize=8.5, textColor=TEXTO, leading=13,
                    leftIndent=11, firstLineIndent=-11, spaceAfter=3),
    "mov_rel":   _p("mov_rel",   fontName=MONT_SB, fontSize=8.5, textColor=OURO_CLARO, leading=13,
                    leftIndent=11, firstLineIndent=-11, spaceAfter=3),
    "mov_vazio": _p("mov_vazio", fontName=MONT, fontSize=8.5, textColor=TEXTO_MUTE,
                    leading=13, leftIndent=11, firstLineIndent=-11),
    # resumo
    "eyebrow_l":  _p("eyebrow_l",  fontName=MONT_SB, fontSize=8, textColor=OURO,
                     leading=11, alignment=TA_LEFT),
    "metric_num": _p("metric_num", fontName=CINZEL_SB, fontSize=22, textColor=OURO,
                     leading=24, alignment=TA_CENTER),
    "metric_lbl": _p("metric_lbl", fontName=MONT_SB, fontSize=7.5, textColor=TEXTO_MUTE,
                     leading=10, alignment=TA_CENTER),
    "trib_cell":  _p("trib_cell",  fontName=MONT, fontSize=9, textColor=TEXTO, leading=12),
    "trib_qtd":   _p("trib_qtd",   fontName=MONT_SB, fontSize=9, textColor=OURO,
                     leading=12, alignment=TA_RIGHT),
}


# ─────────────────────────────────────────────────────────── Helpers de dados
def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _partes(partes: list) -> tuple[str, str]:
    tipos_ativo   = {"Ativo", "Requerente", "Autor", "Reclamante", "Impetrante", "Exequente"}
    tipos_passivo = {"Passivo", "Requerido", "Réu", "Reclamado", "Impetrado", "Executado"}
    at = [p.get("nome", "").strip() for p in partes if isinstance(p, dict) and p.get("tipo") in tipos_ativo]
    pa = [p.get("nome", "").strip() for p in partes if isinstance(p, dict) and p.get("tipo") in tipos_passivo]
    return (", ".join([x for x in at if x]) or "—"), (", ".join([x for x in pa if x]) or "—")


def _primeiro_nome(nome: str) -> str:
    nome = (nome or "").strip()
    return nome.split(",")[0].strip() if nome else ""


def _rotulo_processo(proc: dict) -> str:
    # Nomes das partes em CAIXA ALTA para padronizar entre tribunais (o TJGO vem
    # capitalizado, o TJDFT em maiúsculo). O " x " separador fica minúsculo.
    ativo, passivo = _partes(proc.get("partes") or [])
    a, p = _primeiro_nome(ativo), _primeiro_nome(passivo)
    a = "" if a == "—" else a.upper()
    p = "" if p == "—" else p.upper()
    if a and p:
        return f"{a} x {p}"
    if a or p:
        return a or p
    classe = proc.get("classe") or {}
    nome_classe = classe.get("nome", "") if isinstance(classe, dict) else str(classe)
    return (nome_classe.strip() or "Processo").upper()


def _nome_consultado(processos: list[dict]) -> str:
    """Infere o nome do consultado: a parte mais frequente entre os processos.

    Como a busca é por CPF/CNPJ, o consultado figura em todos os seus processos,
    então é o nome de parte que mais se repete. Normaliza em caixa alta para somar
    ocorrências do mesmo nome vindas de tribunais com grafias diferentes.
    """
    cont: Counter[str] = Counter()
    for proc in processos:
        for parte in (proc.get("partes") or []):
            if isinstance(parte, dict):
                nome = (parte.get("nome") or "").strip().upper()
                if nome and nome != "—":
                    cont[nome] += 1
    return cont.most_common(1)[0][0] if cont else ""


def _movs(proc: dict) -> list[str]:
    out = []
    for mov in (proc.get("movimentos") or []):
        if not isinstance(mov, dict):
            continue
        nome = (mov.get("nome") or "").strip()
        if not nome:
            continue
        dh = (mov.get("dataHora") or "").strip()
        if dh:
            try:
                d = datetime.fromisoformat(dh[:10]).strftime("%d/%m/%Y")
                nome = f"{d} — {nome}" if not re.match(r"^\d{2}/\d{2}/\d{4}", nome) else nome
            except Exception:
                pass
        out.append(re.sub(r"^[\—\-\s]+", "", nome).strip())
    return out


# ─────────────────────────────────────────────────────────── Flowables custom
class GoldBar(Flowable):
    """Barra com gradiente dourado e título Cinzel centralizado (cabeçalho de card).

    O título usa fonte fixa e quebra em quantas linhas precisar; a barra cresce em
    altura. Antes a fonte era reduzida até 6,5pt para caber em uma linha, o que
    deixava títulos longos minúsculos e inconsistentes ao lado dos curtos.
    """

    def __init__(self, texto, largura, fontsize=9.5, padding=0.22 * cm):
        super().__init__()
        self.texto = texto
        self.width = largura
        self.fontsize = fontsize
        self.padding = padding
        self.leading = fontsize * 1.25
        self.lines = self._wrap()
        self.height = max(0.82 * cm, len(self.lines) * self.leading + 2 * padding)

    def _wrap(self) -> list[str]:
        limite = self.width - 0.8 * cm
        linhas, atual = [], ""
        for palavra in self.texto.split():
            teste = f"{atual} {palavra}".strip()
            if atual and pdfmetrics.stringWidth(teste, CINZEL_SB, self.fontsize) > limite:
                linhas.append(atual)
                atual = palavra
            else:
                atual = teste
        if atual:
            linhas.append(atual)
        return linhas or [""]

    def draw(self):
        c = self.canv
        c.saveState()
        path = c.beginPath()
        path.rect(0, 0, self.width, self.height)
        c.clipPath(path, stroke=0, fill=0)
        c.linearGradient(0, 0, self.width, 0,
                         [OURO, OURO_CLARO, OURO], positions=[0, 0.5, 1])
        c.restoreState()
        c.setFillColor(VERDE)
        c.setFont(CINZEL_SB, self.fontsize)
        n = len(self.lines)
        y = self.height / 2 + (n - 1) * self.leading / 2 - self.fontsize * 0.34
        for ln in self.lines:
            c.drawCentredString(self.width / 2, y, ln)
            y -= self.leading


class HRule(Flowable):
    """Linha horizontal dourada fina."""

    def __init__(self, largura, cor=OURO, esp=0.6, dash=False):
        super().__init__()
        self.width = largura
        self.height = esp
        self.cor = cor
        self.esp = esp
        self.dash = dash

    def draw(self):
        c = self.canv
        c.setStrokeColor(self.cor)
        c.setLineWidth(self.esp)
        if self.dash:
            c.setDash(1, 2)
        c.line(0, 0, self.width, 0)


# ─────────────────────────────────────────────────────────── Card de processo
def _card(proc: dict, largura: float, indice: int) -> KeepTogether:
    numero = (proc.get("numeroProcesso") or "").strip() or "—"
    rotulo = _rotulo_processo(proc)
    titulo = f"{indice} - {rotulo}  ·  {numero}"

    movs = _movs(proc)
    if movs:
        # Relevantes ganham realce (semibold + dourado claro); nada é removido.
        corpo = [
            Paragraph(
                f'<font color="#BF9C6F">•</font>&nbsp;&nbsp;{_esc(m)}',
                S["mov_rel"] if _relevante(m) else S["mov"],
            )
            for m in movs
        ]
    else:
        ultima = (proc.get("ultima_movimentacao") or "").strip()
        txt = _esc(ultima) if ultima else "Sem movimentações capturadas para este processo."
        corpo = [Paragraph(f'<font color="#BF9C6F">•</font>&nbsp;&nbsp;{txt}', S["mov_vazio"])]

    corpo_tbl = Table([[corpo]], colWidths=[largura])
    corpo_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), SURFACE),
        ("LINEABOVE",     (0, 0), (-1, 0), 0.4, OURO),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.4, BORDA),
        ("LINEAFTER",     (-1, 0), (-1, -1), 0.4, BORDA),
        ("LINEBEFORE",    (0, 0), (0, -1), 2.2, OURO),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))

    return KeepTogether([
        GoldBar(titulo, largura),
        corpo_tbl,
        Spacer(1, 0.45 * cm),
    ])


# ─────────────────────────────────────────────────────────── Listagem das ações
def _tabela_listagem(processos: list[dict], largura: float) -> Table:
    """Listagem como uma única tabela: quebra de página limpa (sem linha órfã numa
    página vazia) e linhas alternadas para leitura de listas longas."""
    rows = []
    estilo = [
        ("LINEABOVE",     (0, 0), (-1, 0), 0.5, BORDA),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, BORDA),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, proc in enumerate(processos, 1):
        rotulo = _rotulo_processo(proc)
        numero = (proc.get("numeroProcesso") or "").strip() or "—"
        trib = (proc.get("tribunal") or "").strip()
        esq = f'<font color="#F4F0E6">{_esc(rotulo)}</font>'
        if numero != "—":
            esq += f'&nbsp;&nbsp;<font color="#B9B6A4">{_esc(numero)}</font>'
        if trib:
            esq += f'&nbsp;&nbsp;<font color="#BF9C6F" size="7">{_esc(trib)}</font>'
        rows.append([Paragraph(esq, S["lista_parte"]), Paragraph(str(i), S["lista_num"])])
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i - 1), (-1, i - 1), ZEBRA))

    t = Table(rows, colWidths=[largura - 1.2 * cm, 1.2 * cm])
    t.setStyle(TableStyle(estilo))
    return t


def _titulo_secao(titulo_linhas: list[str], subtitulo: str, largura: float) -> list:
    flow = [Spacer(1, 0.3 * cm)]
    for ln in titulo_linhas:
        flow.append(Paragraph(_esc(ln), S["secao"]))
    if subtitulo:
        flow.append(Spacer(1, 0.15 * cm))
        flow.append(Paragraph(_esc(subtitulo), S["secao_sub"]))
    flow.append(Spacer(1, 0.2 * cm))
    flow.append(HRule(largura))
    flow.append(Spacer(1, 0.5 * cm))
    return flow


def _resumo(docs_validos: list[tuple[str, list]], largura: float) -> list:
    """Painel de resumo da consulta: totais e distribuição por tribunal."""
    todos = [p for _, ps in docs_validos for p in ps]
    por_trib: dict[str, int] = {}
    for p in todos:
        t = (p.get("tribunal") or "—").strip() or "—"
        por_trib[t] = por_trib.get(t, 0) + 1

    flow = _titulo_secao(["RESUMO", "DA CONSULTA"],
                         "Visão geral dos processos localizados", largura)

    def _tile(numero: int, rotulo: str) -> list:
        return [Paragraph(str(numero), S["metric_num"]), Spacer(1, 2),
                Paragraph(rotulo, S["metric_lbl"])]

    tiles = Table(
        [[_tile(len(docs_validos), "DOCUMENTOS"),
          _tile(len(todos), "PROCESSOS"),
          _tile(len(por_trib), "TRIBUNAIS")]],
        colWidths=[largura / 3] * 3,
    )
    tiles.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), SURFACE),
        ("BOX",           (0, 0), (-1, -1), 0.5, BORDA),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, BORDA),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    flow.append(tiles)
    flow.append(Spacer(1, 0.7 * cm))

    flow.append(Paragraph("POR TRIBUNAL", S["eyebrow_l"]))
    flow.append(Spacer(1, 0.25 * cm))
    trib_rows = [
        [Paragraph(_esc(t), S["trib_cell"]), Paragraph(str(q), S["trib_qtd"])]
        for t, q in sorted(por_trib.items(), key=lambda x: (-x[1], x[0]))
    ]
    tt = Table(trib_rows, colWidths=[largura - 2.2 * cm, 2.2 * cm])
    tt.setStyle(TableStyle([
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, BORDA),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow.append(tt)
    return flow


# ─────────────────────────────────────────────────────────── Chrome das páginas
def _fundo(c) -> None:
    c.setFillColor(VERDE)
    c.rect(0, 0, A4_W, A4_H, stroke=0, fill=1)


def _capa(c, doc) -> None:
    _fundo(c)
    # grafismo: arcos concêntricos dourados saindo do canto inferior esquerdo
    c.saveState()
    p = c.beginPath(); p.rect(0, 0, A4_W, A4_H); c.clipPath(p, stroke=0, fill=0)
    cx, cy = -3.0 * cm, 6.0 * cm
    c.setStrokeColor(OURO)
    c.setLineWidth(0.5)
    c.setStrokeAlpha(0.16)
    raio = 2.6 * cm
    for _ in range(16):
        c.circle(cx, cy, raio, stroke=1, fill=0)
        raio += 0.62 * cm
    c.restoreState()

    # logo dourada no topo
    logo = _img("logo-full-gold.png")
    if logo:
        lw = 5.0 * cm
        c.drawImage(logo, 2.2 * cm, A4_H - 3.3 * cm, width=lw, height=lw / 2.888,
                    mask="auto", preserveAspectRatio=True)

    # data no topo direito (sem tracinho — encostava no texto)
    data_str = datetime.now().strftime("%B DE %Y").upper()
    data_str = _MESES.get(data_str.split(" ")[0], data_str.split(" ")[0]) + data_str[len(data_str.split(" ")[0]):]
    c.setFont(MONT_SB, 10)
    c.setFillColor(OURO)
    c.drawRightString(A4_W - 2.2 * cm, A4_H - 2.55 * cm, data_str)

    # título grande Cinzel, alinhado à direita
    c.setFillColor(TEXTO)
    x = A4_W - 2.2 * cm
    y = A4_H / 2 + 2.6 * cm
    for ln in ("RELATÓRIO", "PROCESSUAL"):
        c.setFont(CINZEL_SB, 40)
        c.drawRightString(x, y, ln)
        y -= 1.35 * cm
    c.setFont(MONT, 15)
    c.setFillColor(TEXTO_MUTE)
    c.drawRightString(x, y - 0.4 * cm, "Processos Judiciais")

    # crédito no rodapé
    c.setFont(MONT_SB, 9)
    c.setFillColor(OURO)
    c.drawCentredString(A4_W / 2, 3.0 * cm, "APRESENTADO POR")
    c.setFont(CINZEL, 13)
    c.setFillColor(TEXTO)
    c.drawCentredString(A4_W / 2, 2.3 * cm, "ESCRITÓRIO CLEMON CAMPOS")


def _conteudo(c, doc) -> None:
    _fundo(c)
    # eyebrow topo
    c.setFont(MONT_SB, 8)
    c.setFillColor(OURO)
    c.drawRightString(A4_W - 1.8 * cm, A4_H - 1.5 * cm, "RELATÓRIO PROCESSUAL")
    c.setStrokeColor(OURO); c.setLineWidth(1); c.setStrokeAlpha(0.8)
    c.line(1.8 * cm, A4_H - 1.55 * cm, 4.0 * cm, A4_H - 1.55 * cm)
    c.setStrokeAlpha(1)
    # rodapé: monograma + paginação
    mono = _img("monograma-gold.png")
    if mono:
        c.drawImage(mono, 1.8 * cm, 1.0 * cm, width=0.95 * cm, height=1.0 * cm,
                    mask="auto", preserveAspectRatio=True)
    c.setFont(MONT_SB, 8)
    c.setFillColor(OURO)
    c.drawRightString(A4_W - 1.8 * cm, 1.35 * cm, f"CLEMON CAMPOS  ·  PÁG {doc.page - 1}")


_MESES = {
    "JANUARY": "JANEIRO", "FEBRUARY": "FEVEREIRO", "MARCH": "MARÇO", "APRIL": "ABRIL",
    "MAY": "MAIO", "JUNE": "JUNHO", "JULY": "JULHO", "AUGUST": "AGOSTO",
    "SEPTEMBER": "SETEMBRO", "OCTOBER": "OUTUBRO", "NOVEMBER": "NOVEMBRO", "DECEMBER": "DEZEMBRO",
}


# ─────────────────────────────────────────────────────────── Documento
def gerar_pdf_multi(docs_processos: dict[str, list[dict]]) -> bytes:
    buf = BytesIO()
    LARG = A4_W - 3.6 * cm  # frame útil (margens de 1.8cm)
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=2.2 * cm, bottomMargin=2.0 * cm,
        title="Relatório Processual — Clemon Campos",
    )

    story: list = [Spacer(1, 1), PageBreak()]  # página 1 = capa (pintada no canvas)

    docs_validos = [(d, ps) for d, ps in docs_processos.items() if ps]

    # ── Resumo geral (após a capa)
    if docs_validos:
        story += _resumo(docs_validos, LARG)
        story.append(PageBreak())

    for di, (documento, processos) in enumerate(docs_validos):
        nome = _nome_consultado(processos)
        sub = f"{nome}  ·  {documento}  ·  {len(processos)} processo(s)" if nome \
            else f"{documento}  ·  {len(processos)} processo(s)"

        # ── Listagem das ações
        story += _titulo_secao(["LISTAGEM", "DAS AÇÕES"], sub, LARG)
        story.append(_tabela_listagem(processos, LARG))

        # ── Últimos andamentos: flui após a listagem (sem queimar uma página).
        # Só quebra se o título + primeiro card não couberem no que resta da página,
        # evitando tanto a página de listagem vazia quanto o cabeçalho órfão.
        story.append(Spacer(1, 0.8 * cm))
        story.append(CondPageBreak(6 * cm))
        story += _titulo_secao(["ÚLTIMOS", "ANDAMENTOS"],
                               "Movimentações recentes por processo", LARG)
        for i, proc in enumerate(processos, 1):
            story.append(_card(proc, LARG, i))

        if di < len(docs_validos) - 1:
            story.append(PageBreak())

    if not docs_validos:
        story += _titulo_secao(["SEM", "RESULTADOS"],
                               "Nenhum processo encontrado para os documentos consultados.", LARG)

    doc.build(story, onFirstPage=_capa, onLaterPages=_conteudo)
    return buf.getvalue()


def gerar_pdf(documento: str, processos: list[dict]) -> bytes:
    return gerar_pdf_multi({documento: processos})
