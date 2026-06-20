"""Scraper da Consulta Pública nova do PJe (SPA Angular + API REST).

Usado pelo TJDFT 2º Grau (pje2i-consultapublica). Diferente do PJe 1.x (JSF) e do
2.x clássico (Angular embutido no seam): aqui há uma API REST aberta que aceita o
documento em dígitos e devolve JSON estruturado — sem browser, sem captcha.

Endpoint: GET <api>/v1/processos?page=<0-based>&documento=<digitos>
"""

import re
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAX_PROCESSOS = 100
MAX_PAGINAS   = 10

_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_DATA_RE = re.compile(r"\((\d{2})/(\d{2})/(\d{4})")
_ARQUIVADO = re.compile(r"arquivad|baixad|extint|encerrad", re.IGNORECASE)


def _limpar(doc: str) -> str:
    return re.sub(r"\D", "", doc)


def _parte(polo: dict) -> str:
    if not isinstance(polo, dict):
        return ""
    nome = (polo.get("nomeParte") or "").strip()
    qnt = polo.get("qntOutros") or 0
    if nome and qnt:
        nome += f" e outros {qnt}"
    return nome


def _movimentacoes(ultima: str) -> list[dict]:
    """'Juntada ... (09/06/2026 07:00:38)' -> [{data: '09/06/2026', nome: 'Juntada ...'}]"""
    ultima = (ultima or "").strip()
    if not ultima:
        return []
    m = _DATA_RE.search(ultima)
    data = f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else ""
    nome = re.sub(r"\s*\(\d{2}/\d{2}/\d{4}.*?\)\s*$", "", ultima).strip() or ultima
    return [{"data": data, "nome": nome}]


def _mapear(item: dict, tribunal_id: str) -> dict:
    partes = item.get("partes") or {}
    ultima = (item.get("ultimaMovimentacao") or "").strip()
    return {
        "numero":              (item.get("numeroProcesso") or "").strip(),
        "classe":              (item.get("classe") or "").strip(),
        "assunto":             (item.get("assunto") or "").strip(),
        "polo_ativo":          _parte(partes.get("poloAtivo")),
        "polo_passivo":        _parte(partes.get("poloPassivo")),
        "ultima_movimentacao": ultima,
        "movimentacoes":       _movimentacoes(ultima),
        "tribunal":            tribunal_id,
    }


def buscar_pje2g(tribunal_id: str, api_url: str, documento: str,
                 progresso=None) -> tuple[list[dict], str | None]:
    doc = _limpar(documento)
    if len(doc) not in (11, 14):
        return [], "Documento inválido"

    processos: list[dict] = []
    try:
        page = 0
        while len(processos) < MAX_PROCESSOS and page < MAX_PAGINAS:
            r = requests.get(
                api_url,
                params={"page": page, "documento": doc},
                headers=_HEADERS, timeout=25, verify=False,
            )
            if r.status_code != 200:
                if page == 0:
                    return [], f"HTTP {r.status_code}"
                break

            dados = r.json()
            result = dados.get("result") or []
            if not result:
                break

            for item in result:
                proc = _mapear(item, tribunal_id)
                if _ARQUIVADO.search(proc.get("ultima_movimentacao", "")):
                    continue
                processos.append(proc)

            info = dados.get("pageInfo") or {}
            atual, ultima_pag = info.get("current"), info.get("last")
            if atual is not None and ultima_pag is not None and atual >= ultima_pag:
                break
            page += 1

    except Exception as e:
        return processos, str(e)

    return processos[:MAX_PROCESSOS], None
