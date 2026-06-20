import asyncio
import re
import sys
from playwright.async_api import async_playwright, Page

MAX_PAGINAS   = 10
MAX_PROCESSOS = 100
LOTE_POPUPS   = 8
N_MOVS        = 3

_ARQUIVADO = re.compile(r"arquivad|baixad|extint|encerrad", re.IGNORECASE)
PADRAO_MOV = re.compile(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})\s*[-–]\s*([^\t\n]+)")

# id -> (nome_exibição, url_consulta_publica, versao_pje)
# versao_pje: "2x" = Angular/ngb-pagination | "1x" = JSF/RichFaces | "2gapi" = SPA Angular nova + API REST
TRIBUNAIS_PJE: dict[str, tuple[str, str, str]] = {
    "TJDFT":    ("TJDFT 1º Grau", "https://pje.tjdft.jus.br/pje/ConsultaPublica/listView.seam",      "2x"),
    "TJDFT-2G": ("TJDFT 2º Grau", "https://pje2i-consultapublica-api.tjdft.jus.br/v1/processos",     "2gapi"),
    "TJPE":  ("TJPE",  "https://pje.cloud.tjpe.jus.br/1g/ConsultaPublica/listView.seam",             "1x"),
    "TJMA":  ("TJMA",  "https://pje.tjma.jus.br/pje/ConsultaPublica/listView.seam",                  "1x"),
    "TRF1":  ("TRF1",  "https://pje1g-consultapublica.trf1.jus.br/consultapublica/ConsultaPublica/listView.seam", "1x"),
}


def _limpar(doc: str) -> str:
    return re.sub(r"\D", "", doc)

def _formatar_cnpj(cnpj: str) -> str:
    c = _limpar(cnpj)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else cnpj

def _formatar_cpf(cpf: str) -> str:
    c = _limpar(cpf)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}" if len(c) == 11 else cpf

def _e_cnpj(doc: str) -> bool:
    return len(_limpar(doc)) == 14


async def _movs_de_popup(popup: Page) -> list[dict]:
    try:
        await popup.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    await popup.wait_for_timeout(1000)
    try:
        body = await popup.inner_text("body")
    except Exception:
        return []

    idx = body.find("Movimentações do Processo")
    if idx < 0:
        return []

    movs = []
    for linha in body[idx:idx + 4000].split("\n"):
        m = PADRAO_MOV.match(linha.strip())
        if m:
            movs.append({"data": m.group(1), "nome": m.group(2).strip()})
        if len(movs) >= N_MOVS:
            break
    return movs


async def _extrair_lista_pagina(page: Page, tribunal_id: str) -> list[dict]:
    rows = await page.query_selector_all("table tbody tr")
    processos = []
    for row in rows:
        tds = await row.query_selector_all("td")
        if len(tds) < 3:
            continue

        row_text = await row.inner_text()
        if _ARQUIVADO.search(row_text):
            continue

        td2 = await tds[1].inner_text()
        linhas = [l.strip() for l in td2.split("\n") if l.strip()]

        classe = linhas[0] if linhas else ""

        numero = assunto = ""
        if len(linhas) > 1:
            m = re.match(r"^\S+\s+(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\s*-?\s*(.*)", linhas[1])
            if m:
                numero, assunto = m.group(1), m.group(2).strip()
            else:
                numero = linhas[1]

        partes_raw = linhas[2] if len(linhas) > 2 else ""
        if " X " in partes_raw:
            partes_split = partes_raw.split(" X ", 1)
            polo_ativo, polo_passivo = partes_split[0].strip(), partes_split[1].strip()
        else:
            polo_ativo, polo_passivo = partes_raw, ""

        ultima_mov = (await tds[2].inner_text()).strip()

        processos.append({
            "numero":             numero,
            "classe":             classe,
            "assunto":            assunto,
            "polo_ativo":         polo_ativo,
            "polo_passivo":       polo_passivo,
            "ultima_movimentacao": ultima_mov,
            "movimentacoes":      [],
            "tribunal":           tribunal_id,
        })

    return processos


async def _total_paginas(page: Page) -> int:
    try:
        paginacao = await page.query_selector("ngb-pagination, .pagination")
        if not paginacao:
            return 1
        texto = await paginacao.inner_text()
        nums = re.findall(r"\d+", texto)
        return int(max(nums, key=int)) if nums else 1
    except Exception:
        return 1


async def _buscar_pje_async(
    tribunal_id: str,
    url: str,
    documento: str,
    progresso=None,
) -> tuple[list[dict], str | None]:
    e_cnpj = _e_cnpj(documento)
    doc_fmt = _formatar_cnpj(documento) if e_cnpj else _formatar_cpf(documento)

    processos: list[dict] = []
    erro = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context()
            popups_batch: list[Page] = []

            def _on_page(pg: Page) -> None:
                popups_batch.append(pg)

            ctx.on("page", _on_page)
            page = await ctx.new_page()

            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)

            # Detecta se a interface PJe 2.x carregou corretamente
            if not await page.query_selector("input[name=documento]"):
                body = await page.inner_text("body")
                if "cloudflare" in body.lower() or "captcha" in body.lower():
                    return [], f"Acesso bloqueado (Cloudflare/CAPTCHA)"
                return [], f"Interface PJe não reconhecida — possível versão incompatível"

            radios = await page.query_selector_all("input[name=documento]")
            if len(radios) >= 2:
                await radios[1 if e_cnpj else 0].click()
                await page.wait_for_timeout(300)

            await page.fill("#documento", doc_fmt)
            await page.click("button.pesquisar")
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)

            body = await page.inner_text("body")
            if "nenhum processo" in body.lower() or "não foram encontrados" in body.lower():
                return [], None

            total_pags = min(await _total_paginas(page), MAX_PAGINAS)
            pag_atual = 1

            while True:
                if progresso:
                    progresso(pag_atual, total_pags)

                procs_pag = await _extrair_lista_pagina(page, tribunal_id)
                if not procs_pag:
                    break

                links_pag = await page.query_selector_all("a.ver-detalhes")
                idx_proc = 0

                for i in range(0, len(links_pag), LOTE_POPUPS):
                    lote = links_pag[i:i + LOTE_POPUPS]
                    popups_batch.clear()

                    for link in lote:
                        await link.click()
                        await asyncio.sleep(0.08)

                    deadline = asyncio.get_running_loop().time() + 7
                    while len(popups_batch) < len(lote) and asyncio.get_running_loop().time() < deadline:
                        await asyncio.sleep(0.3)

                    movs_lote = await asyncio.gather(*[_movs_de_popup(pg) for pg in popups_batch])

                    for j, movs in enumerate(movs_lote):
                        if idx_proc + j < len(procs_pag):
                            procs_pag[idx_proc + j]["movimentacoes"] = movs

                    for pg in popups_batch:
                        try:
                            await pg.close()
                        except Exception:
                            pass

                    idx_proc += len(lote)

                processos.extend(procs_pag)

                if len(processos) >= MAX_PROCESSOS:
                    processos = processos[:MAX_PROCESSOS]
                    break

                if pag_atual >= total_pags:
                    break
                try:
                    proximo = await page.query_selector(
                        "ngb-pagination [aria-label='Próximo'], .pagination .page-item:last-child a"
                    )
                    if not proximo:
                        break
                    await proximo.click()
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(1500)
                    pag_atual += 1
                except Exception:
                    break

        except Exception as e:
            erro = str(e)
        finally:
            await browser.close()

    return processos, erro


def buscar_pje(
    tribunal_id: str,
    url: str,
    documento: str,
    progresso=None,
) -> tuple[list[dict], str | None]:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(_buscar_pje_async(tribunal_id, url, documento, progresso))
