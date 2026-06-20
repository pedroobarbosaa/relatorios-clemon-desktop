import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from datetime import datetime

import streamlit as st

from scraper_pje import buscar_pje, TRIBUNAIS_PJE, _limpar, _formatar_cnpj, _formatar_cpf, _e_cnpj
from scraper_pje1x import buscar_pje1x
from scraper_pje2g import buscar_pje2g
from scraper_projudi_go import buscar as buscar_projudi
from scraper_esaj import buscar_esaj
from pdf_gen import gerar_pdf_multi

_BASE = os.path.dirname(os.path.abspath(__file__))
_LOGO = os.path.join(_BASE, "assets", "img", "logo-full-gold.png")
_MONO = os.path.join(_BASE, "assets", "img", "monograma-gold.png")

st.set_page_config(
    page_title="Relatório Processual — Clemon Campos",
    page_icon=_MONO if os.path.exists(_MONO) else None,
    layout="wide",
)

# ── Identidade visual Clemon Campos (verde escuro + dourado, Cinzel + Montserrat)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;500;600;700&family=Montserrat:wght@300;400;500;600;700;800&display=swap');

:root{
  --verde:#253216; --verde-2:#1d2812; --surface:#2E3D1E; --surface2:#374A26;
  --ouro:#BF9C6F; --ouro-claro:#F2D9AF; --texto:#F4F0E6; --mute:#B9B6A4; --borda:#3A4A28;
  --gold-grad:linear-gradient(135deg,#BF9C6F 0%,#F2D9AF 50%,#BF9C6F 100%);
}

/* Base + textura sutil de profundidade */
html, body, [class*="css"], .stApp, p, label, span, div, input, textarea {
  font-family:'Montserrat',sans-serif; }
.stApp{
  background:
    radial-gradient(1200px 600px at 80% -10%, rgba(191,156,111,.06), transparent 60%),
    radial-gradient(900px 500px at -10% 20%, rgba(191,156,111,.05), transparent 55%),
    var(--verde);
}
.block-container{ max-width:1180px; padding-top:2.2rem; padding-bottom:4rem; }

/* Esconde a chrome do Streamlit */
header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"]{ display:none !important; }

/* Tipografia */
h1,h2,h3,h4{ font-family:'Cinzel',serif !important; color:var(--texto) !important;
  letter-spacing:.045em; text-transform:uppercase; }
h1{ color:var(--ouro) !important; font-weight:600 !important; line-height:1.05; }
.stApp p, .stApp li{ color:var(--texto); }

/* Eyebrow, sub, divisória dourada (assinatura da marca) */
.cc-eyebrow{ font-weight:600; font-size:.7rem; letter-spacing:.22em; text-transform:uppercase;
  color:var(--ouro); display:flex; align-items:center; gap:.7rem; margin:.2rem 0 .5rem; }
.cc-eyebrow::after{ content:""; flex:1; height:1px;
  background:linear-gradient(90deg,rgba(191,156,111,.55),transparent); }
.cc-sub{ color:var(--mute); font-size:.9rem; letter-spacing:.01em; }
.cc-rule{ height:1.5px; width:100%; border:none;
  background:linear-gradient(90deg,var(--ouro),var(--ouro-claro) 35%,transparent); margin:.5rem 0 1.6rem; }

/* Inputs / textarea / selects */
.stTextArea textarea, .stTextInput input,
.stMultiSelect div[data-baseweb="select"] > div, [data-baseweb="select"] > div{
  background:var(--surface) !important; color:var(--texto) !important;
  border:1px solid var(--borda) !important; border-radius:5px !important; }
.stTextArea textarea::placeholder{ color:#7e8a6c !important; }
.stTextArea textarea:focus, .stTextInput input:focus{
  border-color:var(--ouro) !important; box-shadow:0 0 0 1px var(--ouro) !important; }
.stTextArea label, .stMultiSelect label, .stCheckbox label, .stTextInput label{
  color:var(--mute) !important; font-size:.78rem !important; letter-spacing:.04em; }

/* Chips do multiselect em dourado */
[data-baseweb="tag"]{ background:var(--gold-grad) !important; color:#253216 !important;
  border-radius:3px !important; font-weight:600 !important; }
[data-baseweb="tag"] span{ color:#253216 !important; }
[data-baseweb="tag"] svg{ fill:#253216 !important; }

/* Cards de superfície (st.container(border=True) e expanders) */
[data-testid="stVerticalBlockBorderWrapper"]{
  background:rgba(46,61,30,.55) !important; border:1px solid var(--borda) !important;
  border-radius:6px !important; }
details[data-testid="stExpander"]{
  background:rgba(46,61,30,.55); border:1px solid var(--borda) !important; border-radius:6px; }
details[data-testid="stExpander"] summary{ color:var(--texto) !important; }
details[data-testid="stExpander"] summary:hover{ color:var(--ouro) !important; }

/* Botões — dourado metálico */
.stButton > button, .stDownloadButton > button{
  background:var(--gold-grad) !important; color:#253216 !important; border:none !important;
  border-radius:5px !important; font-weight:700 !important; letter-spacing:.08em !important;
  text-transform:uppercase; font-size:.8rem !important; padding:.65rem 2rem !important;
  box-shadow:0 6px 18px rgba(0,0,0,.25); transition:filter .2s, transform .15s, box-shadow .2s; }
.stButton > button:hover, .stDownloadButton > button:hover{
  filter:brightness(1.07); transform:translateY(-2px); box-shadow:0 10px 24px rgba(0,0,0,.32); }

/* Tabs */
.stTabs [data-baseweb="tab-list"]{ gap:1.4rem; border-bottom:1px solid var(--borda); }
.stTabs [data-baseweb="tab"]{ color:var(--mute); font-weight:500; letter-spacing:.04em; }
.stTabs [aria-selected="true"]{ color:var(--ouro) !important; }
.stTabs [data-baseweb="tab-highlight"]{ background:var(--ouro) !important; }

/* Métricas — número em Cinzel dourado */
[data-testid="stMetric"]{ background:rgba(46,61,30,.5); border:1px solid var(--borda);
  border-radius:6px; padding:1rem 1.2rem; }
[data-testid="stMetricValue"]{ font-family:'Cinzel',serif !important; color:var(--ouro) !important;
  font-weight:600; }
[data-testid="stMetricLabel"]{ color:var(--mute) !important; text-transform:uppercase;
  letter-spacing:.14em; font-size:.7rem !important; }

/* Tabelas */
hr{ border-color:var(--borda) !important; }
[data-testid="stDataFrame"]{ border:1px solid var(--borda); border-radius:6px; overflow:hidden; }

/* Alerts tematizados */
[data-testid="stAlert"]{ border-radius:6px; border:1px solid var(--borda);
  background:rgba(46,61,30,.6) !important; color:var(--texto) !important; }

/* Tabelas no tema (substituem o grid padrão do st.dataframe) */
.cc-table{ width:100%; border-collapse:collapse; font-family:'Montserrat',sans-serif;
  font-size:.83rem; margin:.2rem 0 1rem; border:1px solid var(--borda);
  border-radius:6px; overflow:hidden; }
.cc-table thead th{ background:var(--gold-grad); color:#253216; font-weight:700;
  text-transform:uppercase; letter-spacing:.05em; font-size:.7rem; text-align:left;
  padding:.6rem .8rem; white-space:nowrap; }
.cc-table thead th.num{ text-align:right; }
.cc-table tbody td{ color:var(--texto); border-top:1px solid var(--borda);
  padding:.55rem .8rem; vertical-align:top; }
.cc-table tbody tr:nth-child(even){ background:rgba(46,61,30,.5); }
.cc-table tbody tr:hover{ background:rgba(191,156,111,.10); }
.cc-table td.num{ text-align:right; color:var(--ouro); font-weight:600; white-space:nowrap; }
.cc-table td.trib{ color:var(--ouro); font-weight:600; font-size:.72rem;
  letter-spacing:.04em; white-space:nowrap; }
.cc-table td.num-proc{ color:var(--mute); white-space:nowrap; }

/* Scrollbar */
::-webkit-scrollbar{ width:10px; height:10px; }
::-webkit-scrollbar-track{ background:var(--verde-2); }
::-webkit-scrollbar-thumb{ background:var(--surface2); border-radius:6px; }
::-webkit-scrollbar-thumb:hover{ background:var(--ouro); }
</style>
""", unsafe_allow_html=True)

# ── Cabeçalho com logo
_c1, _c2 = st.columns([1, 4], vertical_alignment="center")
with _c1:
    if os.path.exists(_MONO):
        st.image(_MONO, width=110)
with _c2:
    st.markdown(
        "<div class='cc-eyebrow'>Clemon Campos Advocacia</div>"
        "<h1 style='margin:.1rem 0 .2rem;'>Relatório Processual</h1>"
        "<div class='cc-sub'>Consulta por CNPJ ou CPF · TJDFT (1º e 2º grau) · TJPE · TJMA · TRF1 (PJe) · "
        "TJGO (PROJUDI) · TJSP (e-SAJ) · Sem custo</div>",
        unsafe_allow_html=True,
    )
st.markdown("<div class='cc-rule'></div>", unsafe_allow_html=True)

# ── Entrada de documentos
col_doc, col_trib = st.columns([1, 1], gap="large")

with col_doc:
    st.markdown("<div class='cc-eyebrow'>Documentos</div>", unsafe_allow_html=True)
    st.text_area(
        "CPF(s) ou CNPJ(s) — um por linha",
        key="docs_raw",
        placeholder="00.000.000/0001-91\n000.000.000-00\n11.222.333/0001-44",
        height=150,
        label_visibility="collapsed",
    )
    st.markdown("<div class='cc-sub'>Um CPF ou CNPJ por linha.</div>", unsafe_allow_html=True)

with col_trib:
    st.markdown("<div class='cc-eyebrow'>Tribunais</div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.caption("**PJe** — TJDFT 1º/2º Grau · TJPE · TJMA · TRF1")
        pje_sel = st.multiselect(
            "Tribunais PJe",
            options=list(TRIBUNAIS_PJE.keys()),
            default=["TJDFT"],
            format_func=lambda k: TRIBUNAIS_PJE[k][0],
            label_visibility="collapsed",
        )
        st.caption("**Outros**")
        tjgo_sel = st.checkbox("TJGO (PROJUDI)", value=False)
        tjsp_sel = st.checkbox("TJSP (e-SAJ)", value=False)

st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
buscar_btn = st.button("Buscar processos", type="primary", use_container_width=False)
st.divider()


def _validar(doc: str) -> tuple[bool, str]:
    d = re.sub(r"\D", "", doc)
    if len(d) == 11:
        return True, "CPF"
    if len(d) == 14:
        return True, "CNPJ"
    return False, ""


def _fmt_doc(doc: str, tipo: str) -> str:
    return _formatar_cnpj(doc) if tipo == "CNPJ" else _formatar_cpf(doc)


def _esc_html(valor) -> str:
    s = "" if valor is None else str(valor)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tabela_html(colunas: list[str], linhas: list[dict], col_class: dict | None = None) -> str:
    """Tabela HTML com a identidade da marca, no lugar do grid padrão do Streamlit.

    col_class: mapa {coluna: classe_css} aplicado ao <td> (e ao <th> quando 'num',
    para alinhar o cabeçalho à direita).
    """
    col_class = col_class or {}
    ths = "".join(
        f'<th class="num">{_esc_html(c)}</th>' if col_class.get(c) == "num"
        else f"<th>{_esc_html(c)}</th>"
        for c in colunas
    )
    trs = []
    for linha in linhas:
        tds = []
        for c in colunas:
            valor = linha.get(c)
            txt = _esc_html(valor if valor not in (None, "") else "—")
            cls = col_class.get(c)
            tds.append(f'<td class="{cls}">{txt}</td>' if cls else f"<td>{txt}</td>")
        trs.append(f"<tr>{''.join(tds)}</tr>")
    return (f'<table class="cc-table"><thead><tr>{ths}</tr></thead>'
            f"<tbody>{''.join(trs)}</tbody></table>")


def _converter_para_pdf(p: dict) -> dict:
    movs_raw = p.get("movimentacoes") or []
    movimentos = []
    for m in movs_raw:
        if not isinstance(m, dict) or not m.get("nome"):
            continue
        data = (m.get("data") or "")[:10]
        # Datas do DataJud vêm em ISO (AAAA-MM-DD); o PJe já traz dd/mm no nome.
        # Padroniza tudo para dd/mm/aaaa.
        iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", data)
        if iso:
            data = f"{iso.group(3)}/{iso.group(2)}/{iso.group(1)}"
        nome = m.get("nome", "")
        texto = f"{data} — {nome}" if data else nome
        movimentos.append({"nome": texto, "dataHora": ""})

    if not movimentos and p.get("ultima_movimentacao"):
        movimentos = [{"nome": p.get("ultima_movimentacao", ""), "dataHora": ""}]

    data_dist = p.get("data_distribuicao") or ""
    data_iso = ""
    if data_dist and data_dist != "—":
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", data_dist)
        if m:
            data_iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    return {
        "numeroProcesso": p.get("numero", ""),
        "tribunal":       p.get("tribunal", ""),
        "classe":         {"nome": p.get("classe", "")},
        "assuntos":       [{"nome": p.get("assunto", "")}] if p.get("assunto") else [],
        "partes": [
            {"nome": p.get("polo_ativo", ""),  "tipo": "Ativo"},
            {"nome": p.get("polo_passivo", ""), "tipo": "Passivo"},
        ],
        "movimentos":      movimentos,
        "dataAjuizamento": data_iso,
    }


if buscar_btn:
    # ── Parseia e valida documentos
    linhas = [l.strip() for l in (st.session_state.get("docs_raw") or "").split("\n") if l.strip()]
    docs_validos: list[tuple[str, str, str]] = []  # (doc_raw, doc_fmt, tipo)
    invalidos: list[str] = []

    for linha in linhas:
        ok, tipo = _validar(linha)
        if ok:
            docs_validos.append((linha, _fmt_doc(linha, tipo), tipo))
        else:
            invalidos.append(linha)

    if invalidos:
        st.warning(f"Ignorados (formato inválido): {', '.join(invalidos)}")

    if not docs_validos:
        st.error("Nenhum CPF ou CNPJ válido informado.")
        st.stop()

    if not pje_sel and not tjgo_sel and not tjsp_sel:
        st.error("Selecione ao menos um tribunal.")
        st.stop()

    todos_ids = pje_sel + (["TJGO"] if tjgo_sel else []) + (["TJSP"] if tjsp_sel else [])
    n_tarefas = len(docs_validos) * len(todos_ids)

    st.markdown(
        f"<div class='cc-sub'>Buscando <b style='color:#BF9C6F'>{len(docs_validos)}</b> documento(s) em "
        f"<b style='color:#BF9C6F'>{len(todos_ids)}</b> tribunal(is) — "
        f"<b style='color:#BF9C6F'>{n_tarefas}</b> consulta(s).</div>",
        unsafe_allow_html=True,
    )

    # ── Execução paralela: (doc_raw, tribunal_id) → (procs, erro)
    resultados: dict[tuple[str, str], tuple[list, str | None]] = {}
    lock = threading.Lock()

    def _tarefa(tribunal_id: str, doc_raw: str) -> None:
        try:
            if tribunal_id == "TJGO":
                procs, erro = buscar_projudi(doc_raw)
            elif tribunal_id == "TJSP":
                procs, erro = buscar_esaj(doc_raw)
            else:
                _, url, versao = TRIBUNAIS_PJE[tribunal_id]
                if versao == "1x":
                    procs, erro = buscar_pje1x(tribunal_id, url, doc_raw)
                elif versao == "2gapi":
                    procs, erro = buscar_pje2g(tribunal_id, url, doc_raw)
                else:
                    procs, erro = buscar_pje(tribunal_id, url, doc_raw)
            with lock:
                resultados[(doc_raw, tribunal_id)] = (procs or [], erro)
        except Exception as e:
            with lock:
                resultados[(doc_raw, tribunal_id)] = ([], f"Exceção: {e}")

    TIMEOUT_S   = max(180, n_tarefas * 15)
    MAX_WORKERS = 5

    with st.spinner(f"Consultando os tribunais… ({n_tarefas} consulta(s))"):
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futuros = {
                ex.submit(_tarefa, tid, doc_raw): (tid, doc_raw)
                for doc_raw, _, _ in docs_validos
                for tid in todos_ids
            }
            _, not_done = futures_wait(futuros, timeout=TIMEOUT_S)

    for fut in not_done:
        tid, doc_raw = futuros[fut]
        resultados.setdefault((doc_raw, tid), ([], f"Tempo limite de {TIMEOUT_S}s excedido."))

    # ── Tabela de status geral
    st.divider()
    st.markdown("<div class='cc-eyebrow'>Resultado da consulta</div>", unsafe_allow_html=True)
    linhas_status = []
    for doc_raw, doc_fmt, _ in docs_validos:
        for tid in todos_ids:
            procs, erro = resultados.get((doc_raw, tid), ([], "Sem retorno"))
            if erro:
                status = f"Erro: {erro[:80]}"
                n = 0
            elif procs:
                status = f"{len(procs)} processo(s)"
                n = len(procs)
            else:
                status = "Nenhum encontrado"
                n = 0
            linhas_status.append({"Documento": doc_fmt, "Tribunal": tid, "Resultado": status, "Total": n})

    total_encontrado = sum(l["Total"] for l in linhas_status)

    m1, m2, m3 = st.columns(3)
    m1.metric("Documentos", len(docs_validos))
    m2.metric("Tribunais", len(todos_ids))
    m3.metric("Processos encontrados", total_encontrado)

    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
    st.markdown(
        _tabela_html(["Documento", "Tribunal", "Resultado", "Total"], linhas_status,
                     {"Tribunal": "trib", "Total": "num"}),
        unsafe_allow_html=True,
    )

    if total_encontrado == 0:
        st.warning("Nenhum processo encontrado para nenhum dos documentos/tribunais consultados.")
        st.stop()

    # ── Resultados por documento
    st.divider()
    st.markdown("<div class='cc-eyebrow'>Detalhamento por documento</div>", unsafe_allow_html=True)
    for doc_raw, doc_fmt, _ in docs_validos:
        procs_doc = [
            p
            for tid in todos_ids
            for p in resultados.get((doc_raw, tid), ([], None))[0]
        ]
        if not procs_doc:
            continue

        with st.expander(f"{doc_fmt} — {len(procs_doc)} processo(s)", expanded=len(docs_validos) == 1):
            rows = []
            for p in procs_doc:
                movs = p.get("movimentacoes") or []
                ultima = movs[0].get("nome", "") if movs else p.get("ultima_movimentacao", "")
                rows.append({
                    "Tribunal":    p.get("tribunal", ""),
                    "Número":      p.get("numero", ""),
                    "Classe":      p.get("classe", "") or "—",
                    "Polo Ativo":  p.get("polo_ativo", ""),
                    "Polo Passivo": p.get("polo_passivo", ""),
                    "Última Mov.": ultima or "—",
                })
            cols_full = ["Tribunal", "Número", "Classe", "Polo Ativo", "Polo Passivo", "Última Mov."]
            classes = {"Tribunal": "trib", "Número": "num-proc"}
            tids_com_resultado = sorted({r["Tribunal"] for r in rows})
            tabs = st.tabs(["Todos"] + list(tids_com_resultado))
            with tabs[0]:
                st.markdown(_tabela_html(cols_full, rows, classes), unsafe_allow_html=True)
            for i, tid in enumerate(tids_com_resultado, 1):
                with tabs[i]:
                    sub_rows = [r for r in rows if r["Tribunal"] == tid]
                    cols_sub = [c for c in cols_full if c != "Tribunal"]
                    st.markdown(_tabela_html(cols_sub, sub_rows, classes), unsafe_allow_html=True)

    # ── PDF unificado
    st.divider()
    st.markdown("<div class='cc-eyebrow'>Relatório em PDF</div>", unsafe_allow_html=True)
    with st.spinner("Gerando PDF…"):
        docs_processos_pdf: dict[str, list] = {}
        for doc_raw, doc_fmt, _ in docs_validos:
            procs_doc = [
                _converter_para_pdf(p)
                for tid in todos_ids
                for p in resultados.get((doc_raw, tid), ([], None))[0]
            ]
            if procs_doc:
                docs_processos_pdf[doc_fmt] = procs_doc

        pdf_bytes = gerar_pdf_multi(docs_processos_pdf)

    nome = f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    st.download_button(
        label=f"Baixar PDF — {len(docs_processos_pdf)} documento(s), {total_encontrado} processo(s)",
        data=pdf_bytes,
        file_name=nome,
        mime="application/pdf",
        type="primary",
    )
