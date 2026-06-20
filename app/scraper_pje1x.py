import asyncio
import re
import sys
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.async_api import async_playwright, Page

MAX_PROCESSOS       = 100
N_MOVS              = 3
ESPERA_RESULTADOS_S = 30   # postback AJAX pode demorar para partes com muitos processos

_ARQUIVADO = re.compile(r"arquivad|baixad|extint|encerrad", re.IGNORECASE)
PADRAO_CNJ = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

DATAJUD_KEY  = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"

# Índice DataJud por tribunal
DATAJUD_INDEX = {
    "TJPE": "api_publica_tjpe",
    "TJMA": "api_publica_tjma",
    "TRF1": "api_publica_trf1",
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


def _buscar_movs_datajud(proc: dict, indice: str, headers: dict) -> tuple[dict, list]:
    numero = proc.get("numero", "")
    if not numero:
        return proc, []
    try:
        r = requests.post(
            f"{DATAJUD_BASE}/{indice}/_search",
            json={
                "query": {"match": {"numeroProcesso": numero}},
                "_source": ["movimentos"],
                "size": 1,
            },
            headers=headers,
            timeout=5,
        )
        hits = r.json().get("hits", {}).get("hits", [])
        if hits:
            movs_raw = sorted(
                hits[0]["_source"].get("movimentos", []),
                key=lambda m: m.get("dataHora", ""),
                reverse=True,
            )[:N_MOVS]
            return proc, [
                {"data": m.get("dataHora", "")[:10], "nome": m.get("nome", "").strip()}
                for m in movs_raw if m.get("nome")
            ]
    except Exception:
        pass
    return proc, []


def _enriquecer_datajud(processos: list[dict], indice: str) -> None:
    headers = {"Authorization": f"ApiKey {DATAJUD_KEY}"}
    with ThreadPoolExecutor(max_workers=20) as ex:
        futuros = {ex.submit(_buscar_movs_datajud, p, indice, headers): p for p in processos}
        for fut in as_completed(futuros):
            proc, movs = fut.result()
            if movs:
                proc["movimentacoes"] = movs


async def _aguardar_resultados(page: Page, timeout_s: int) -> bool:
    """Faz polling do postback AJAX (não é navegação; networkidle dispara cedo demais).

    A tabela pode levar ~10s para popular. Retorna True ao achar número CNJ; False ao
    detectar mensagem de vazio ou esgotar o tempo.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        await page.wait_for_timeout(800)
        try:
            body = await page.inner_text("body")
        except Exception:
            continue
        if PADRAO_CNJ.search(body):
            return True
        low = body.lower()
        if "não foram encontrados" in low or "nenhum resultado" in low or "nenhum processo" in low:
            return False
    return False


async def _extrair_pagina(page: Page, tribunal_id: str) -> list[dict]:
    rows = await page.query_selector_all("table.rich-table tr")
    processos = []
    for row in rows:
        tds = await row.query_selector_all("td")
        if len(tds) < 2:
            continue

        row_text = await row.inner_text()

        # Linha deve conter número CNJ
        m = PADRAO_CNJ.search(row_text)
        if not m:
            continue

        if _ARQUIVADO.search(row_text):
            continue

        numero = m.group()

        # Última movimentação: último td com conteúdo relevante
        ultima_mov = ""
        for td in reversed(tds):
            texto = (await td.inner_text()).strip()
            # Ignora tds que só têm o número do processo ou são vazios
            if texto and not PADRAO_CNJ.search(texto):
                ultima_mov = texto
                break

        processos.append({
            "numero":              numero,
            "classe":              "",
            "assunto":             "",
            "polo_ativo":          "",
            "polo_passivo":        "",
            "ultima_movimentacao": ultima_mov,
            "movimentacoes":       [],
            "tribunal":            tribunal_id,
        })

    return processos


async def _buscar_pje1x_async(
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
            ctx = await browser.new_context(ignore_https_errors=True)
            page = await ctx.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1500)

            if not await page.query_selector("[id*='documentoParte']"):
                body = (await page.inner_text("body"))[:300].lower()
                if "cloudflare" in body or "just a moment" in body:
                    return [], "Acesso bloqueado (Cloudflare)"
                if "indisponível" in body or "indisponivel" in body or "temporariamente" in body:
                    return [], "Sistema do tribunal temporariamente indisponível"
                return [], "Interface PJe 1.x não reconhecida"

            # Seleciona a máscara CPF/CNPJ antes de digitar. Sem isso o campo aplica a
            # máscara errada, trunca o documento e o PJe rejeita como "inválido".
            radios = await page.query_selector_all("input[name=tipoMascaraDocumento]")
            if len(radios) >= 2:
                await radios[1 if e_cnpj else 0].click()
                await page.wait_for_timeout(700)

            # O RichFaces recria o input ao trocar a máscara — busca o handle DEPOIS do radio.
            # Digita de verdade + Tab (blur) para disparar a validação AJAX; fill() não dispara
            # o handler e o documento não é registrado no servidor.
            campo = await page.query_selector("[id*='documentoParte']")
            await campo.click()
            await campo.type(doc_fmt, delay=35)
            await page.keyboard.press("Tab")
            await page.wait_for_timeout(2200)

            btn = await page.query_selector("input[value='Pesquisar']")
            if not btn:
                return [], "Botão Pesquisar não encontrado"
            await btn.click()

            if not await _aguardar_resultados(page, ESPERA_RESULTADOS_S):
                return [], None

            processos = await _extrair_pagina(page, tribunal_id)
            processos = processos[:MAX_PROCESSOS]

        except Exception as e:
            erro = str(e)
        finally:
            await browser.close()

    if processos and tribunal_id in DATAJUD_INDEX:
        _enriquecer_datajud(processos, DATAJUD_INDEX[tribunal_id])

    return processos, erro


def buscar_pje1x(
    tribunal_id: str,
    url: str,
    documento: str,
    progresso=None,
) -> tuple[list[dict], str | None]:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(_buscar_pje1x_async(tribunal_id, url, documento, progresso))
