"""Scraper do e-SAJ do TJSP — Consulta de Processos do 1º Grau (cpopg).

Busca por "Documento da Parte" (CPF/CNPJ) via requests puro: o e-SAJ não exige
captcha nessa consulta (verificado em 2026-06). A lista traz número, classe,
assunto e a PARTE PESQUISADA com o papel dela (autor/réu/exequente/executado...).
O polo contrário só aparece no detalhe do processo, então aqui registramos apenas
a parte conhecida. Movimentações vêm do DataJud (índice tjsp), como nos demais.

Paginação: página 1 em search.do; páginas seguintes em trocarPagina.do?paginaConsulta=N.
"""

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE        = "https://esaj.tjsp.jus.br/cpopg"
OPEN_URL    = f"{BASE}/open.do"
SEARCH_URL  = f"{BASE}/search.do"

MAX_PROCESSOS = 25  # 1ª página; paginar exigiria browser (ver nota em buscar_esaj)
N_MOVS        = 3

DATAJUD_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
DATAJUD_URL = "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

_TAGS    = re.compile(r"<[^>]+>")
_NUM     = re.compile(r'class="linkProcesso"[^>]*>\s*([\d.\-]+)')
_PARTE   = re.compile(r'class="[^"]*nomeParte"[^>]*>(.*?)</div>', re.S)
_PAPEL   = re.compile(r'class="[^"]*tipoDeParticipacao"[^>]*>(.*?)</label>', re.S)
_CLASSE  = re.compile(r'class="classeProcesso"[^>]*>(.*?)</div>', re.S)
_ASSUNTO = re.compile(r'class="assuntoPrincipalProcesso"[^>]*>(.*?)</div>', re.S)
_ARQUIVADO = re.compile(r"arquivad|baixad|extint", re.IGNORECASE)

# papéis do polo passivo (comparados sem acento/minúsculo)
_PASSIVO_STEMS = ("exec", "reu", "requerid", "reclamad", "impetrad",
                  "embargad", "agravad", "apelad", "recorrid", "devedor")


def _sessao_resiliente() -> requests.Session:
    """Sessão com retry+backoff: sob paralelismo a conexão com o e-SAJ falha
    de forma transitória (Max retries / reset). Retenta erros de conexão e
    respostas 429/5xx em vez de derrubar a consulta do tribunal inteiro."""
    s = requests.Session()
    retry = Retry(total=3, connect=3, read=2, backoff_factor=0.6,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "POST"))
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def _norm(s: str) -> str:
    s = (s or "").lower()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _texto(frag: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub(" ", frag or "")).strip()


def _grab(rx: re.Pattern, frag: str) -> str:
    m = rx.search(frag)
    return _texto(m.group(1)) if m else ""


def _e_passivo(papel: str) -> bool:
    n = _norm(papel)
    return any(stem in n for stem in _PASSIVO_STEMS)


def _parse_lista(html: str) -> list[dict]:
    procs = []
    for frag in html.split("home__lista-de-processos")[1:]:
        mnum = _NUM.search(frag)
        if not mnum:
            continue
        if _ARQUIVADO.search(frag[:1200]):
            continue
        parte = _grab(_PARTE, frag)
        passivo = _e_passivo(_grab(_PAPEL, frag))
        procs.append({
            "numero":              mnum.group(1).strip(),
            "classe":              _grab(_CLASSE, frag),
            "assunto":             _grab(_ASSUNTO, frag),
            "polo_ativo":          "" if passivo else parte,
            "polo_passivo":        parte if passivo else "",
            "ultima_movimentacao": "",
            "movimentacoes":       [],
            "tribunal":            "TJSP",
        })
    return procs


def _movs_datajud(proc: dict, headers: dict) -> tuple[dict, list]:
    digitos = re.sub(r"\D", "", proc.get("numero", ""))
    if not digitos:
        return proc, []
    try:
        r = requests.post(
            DATAJUD_URL,
            json={"query": {"match": {"numeroProcesso": digitos}},
                  "_source": ["movimentos"], "size": 1},
            headers=headers, timeout=15,
        )
        hits = r.json().get("hits", {}).get("hits", [])
        if hits:
            movs = sorted(hits[0]["_source"].get("movimentos", []),
                          key=lambda m: m.get("dataHora", ""), reverse=True)[:N_MOVS]
            return proc, [
                {"data": m.get("dataHora", "")[:10], "nome": m.get("nome", "").strip()}
                for m in movs if m.get("nome")
            ]
    except Exception:
        pass
    return proc, []


def _enriquecer_datajud(procs: list[dict]) -> None:
    headers = {"Authorization": f"ApiKey {DATAJUD_KEY}"}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futuros = {ex.submit(_movs_datajud, p, headers): p for p in procs}
        for fut in as_completed(futuros):
            proc, movs = fut.result()
            if movs:
                proc["movimentacoes"] = movs


def buscar_esaj(documento: str, progresso=None) -> tuple[list[dict], str | None]:
    """Consulta o e-SAJ do TJSP por documento da parte. Retorna (processos, erro)."""
    s = _sessao_resiliente()
    s.headers.update({"User-Agent": _UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    params = {"conversationId": "", "cbPesquisa": "DOCPARTE",
              "dadosConsulta.valorConsulta": documento, "cdForo": "-1"}
    try:
        s.get(OPEN_URL, timeout=20, verify=False)  # estabelece a sessão
        r = s.get(SEARCH_URL, params=params, timeout=30, verify=False)
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        if "nao existem informacoes" in _norm(r.text):
            return [], None

        # Só a 1ª página (25). A paginação do e-SAJ (trocarPagina.do) é AJAX e não
        # devolve a lista via requests; cobrir mais exigiria dirigir o browser.
        # Para os clientes do escritório, 25 processos por documento cobre o normal.
        procs = _parse_lista(r.text)[:MAX_PROCESSOS]
    except Exception as e:
        return [], f"Exceção: {e}"

    if procs:
        _enriquecer_datajud(procs)
    return procs, None
