import asyncio
import re
import sys
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.async_api import async_playwright, Page

PROJUDI_URL   = "https://projudi.tjgo.jus.br/BuscaProcesso"
DATAJUD_URL   = "https://api-publica.datajud.cnj.jus.br/api_publica_tjgo/_search"
DATAJUD_KEY   = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
MAX_PAGINAS   = 7
MAX_PROCESSOS = 100
USER_AGENT    = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _limpar(doc: str) -> str:
    return re.sub(r"\D", "", doc)


def _formatar_cnpj(cnpj: str) -> str:
    c = _limpar(cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cnpj


def _formatar_cpf(cpf: str) -> str:
    c = _limpar(cpf)
    if len(c) == 11:
        return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
    return cpf


def _e_cnpj(doc: str) -> bool:
    return len(_limpar(doc)) == 14


def _parse_partes(texto: str) -> tuple[str, str]:
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
    ativo = passivo = ""
    modo = None
    for l in linhas:
        lu = l.upper()
        if "POLO ATIVO" in lu or lu in ("AUTOR", "REQUERENTE", "EXEQUENTE"):
            modo = "ativo"
        elif "POLO PASSIVO" in lu or lu in ("RÉU", "REQUERIDO", "EXECUTADO"):
            modo = "passivo"
        elif modo == "ativo" and not ativo:
            ativo = l
        elif modo == "passivo" and not passivo:
            passivo = l
    return ativo or "—", passivo or "—"


def _parse_data(texto: str) -> str:
    texto = texto.strip()
    return texto[:10] if len(texto) >= 10 else texto or "—"


def _buscar_mov_unico(proc: dict, headers: dict) -> tuple[dict, list]:
    # O PROJUDI só fornece o número no formato antigo (NNNNNNN-DD), sem o ano. Os 9
    # dígitos (sequencial + verificador) já identificam o processo de forma única no
    # DataJud — o DV é calculado sobre o número inteiro. Não dependemos do ano (que
    # vinha da data de distribuição e falhava em processos redistribuídos). Wildcard
    # ancorado no início do número de 20 dígitos.
    base = proc.get("numero", "").split(".")[0]
    partes = base.split("-")
    num = re.sub(r"\D", "", partes[0]).zfill(7)
    if num == "0000000":
        return proc, []
    dig = re.sub(r"\D", "", partes[1])[:2].zfill(2) if len(partes) > 1 else "00"
    wildcard = f"{num}{dig}*"
    try:
        r = requests.post(
            DATAJUD_URL,
            json={
                "query": {"wildcard": {"numeroProcesso": wildcard}},
                "_source": ["movimentos"],
                "size": 1,
            },
            headers=headers,
            timeout=15,
        )
        hits = r.json().get("hits", {}).get("hits", [])
        if hits:
            movs_raw = hits[0]["_source"].get("movimentos", [])
            movs_ord = sorted(movs_raw, key=lambda m: m.get("dataHora", ""), reverse=True)[:3]
            return proc, [
                {"data": m.get("dataHora", "")[:10], "nome": m.get("nome", "").strip()}
                for m in movs_ord if m.get("nome")
            ]
    except Exception:
        pass
    return proc, []


def _buscar_movimentos_datajud(processos: list[dict]) -> None:
    """Consulta o DataJud em paralelo (20 workers) para adicionar movimentações."""
    headers = {"Authorization": f"ApiKey {DATAJUD_KEY}"}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futuros = {ex.submit(_buscar_mov_unico, proc, headers): proc for proc in processos}
        for fut in as_completed(futuros):
            proc, movs = fut.result()
            if movs:
                proc["movimentacoes"] = movs


def _total_paginas(body: str) -> int:
    m = re.search(r"Total de:\s*(\d+)", body)
    if not m:
        return 1
    total = int(m.group(1))
    return max(1, -(-total // 15))


_ARQUIVADO = re.compile(r"arquivad|baixad|extint|encerrad", re.IGNORECASE)


async def _extrair_pagina(page: Page) -> list[dict]:
    rows = await page.query_selector_all("table tr.TabelaLinha1, table tr.TabelaLinha2")
    processos = []
    for row in rows:
        tds = await row.query_selector_all("td")
        if len(tds) < 4:
            continue

        row_text = await row.inner_text()
        if _ARQUIVADO.search(row_text):
            continue

        numero_raw = (await tds[2].inner_text()).strip()
        numero = re.sub(r"\s+", " ", numero_raw).strip()

        partes_txt = (await tds[3].inner_text()).strip()
        polo_ativo, polo_passivo = _parse_partes(partes_txt)

        data_txt = (await tds[4].inner_text()).strip() if len(tds) > 4 else ""
        data_dist = _parse_data(data_txt)

        processos.append({
            "numero": numero,
            "classe": "",
            "assunto": "",
            "polo_ativo": polo_ativo,
            "polo_passivo": polo_passivo,
            "data_distribuicao": data_dist,
            "movimentacoes": [],
            "tribunal": "TJGO",
        })

    return processos


async def buscar_projudi_go(documento: str, progresso=None) -> tuple[list[dict], str | None]:
    e_cnpj = _e_cnpj(documento)
    doc_fmt = _formatar_cnpj(documento) if e_cnpj else _formatar_cpf(documento)

    processos: list[dict] = []
    erro = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        try:
            ctx = await browser.new_context(user_agent=USER_AGENT)
            page = await ctx.new_page()

            await page.goto(PROJUDI_URL, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)

            await page.evaluate(f"""
                var overlays = document.querySelectorAll('.ui-widget-overlay,.ui-dialog');
                overlays.forEach(function(el){{ el.style.display='none'; }});
                document.getElementById('CpfCnpjParte').value = '{doc_fmt}';
                document.getElementById('btnBuscar').removeAttribute('disabled');
                AlterarValue('PaginaAtual','2');
                document.querySelector('form').submit();
            """)
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            await page.wait_for_timeout(1000)

            body = await page.inner_text("body")
            if "nenhum" in body.lower() or "não foram" in body.lower():
                return [], None
            if "bloqueou" in body.lower():
                return [], "PROJUDI Goiás: busca bloqueada por proteção anti-bot."

            total_pags = min(_total_paginas(body), MAX_PAGINAS)
            pag_atual = 1

            if progresso:
                progresso(pag_atual, total_pags, "TJGO")

            procs = await _extrair_pagina(page)
            processos.extend(procs)

            if len(processos) >= MAX_PROCESSOS:
                processos = processos[:MAX_PROCESSOS]
                total_pags = 0  # pula paginação

            for pos in range(1, total_pags):
                pag_atual = pos + 1
                if progresso:
                    progresso(pag_atual, total_pags, "TJGO")

                url_pag = (
                    f"{PROJUDI_URL}?PaginaAtual=2&Paginacao=true"
                    f"&PosicaoPaginaAtual={pos}&PassoBusca=1"
                )
                try:
                    await page.goto(url_pag, wait_until="domcontentloaded", timeout=10000)
                except Exception:
                    pass
                await page.wait_for_timeout(500)

                procs = await _extrair_pagina(page)
                if not procs:
                    break
                processos.extend(procs)
                if len(processos) >= MAX_PROCESSOS:
                    processos = processos[:MAX_PROCESSOS]
                    break

        except Exception as e:
            erro = str(e)
        finally:
            await browser.close()

    # Enriquece com movimentações do DataJud (síncrono, fora do browser)
    if processos:
        _buscar_movimentos_datajud(processos)

    return processos, erro


def buscar(documento: str, progresso=None) -> tuple[list[dict], str | None]:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(buscar_projudi_go(documento, progresso))
