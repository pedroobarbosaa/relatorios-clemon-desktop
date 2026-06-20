"""
Launcher do Relatorio Processual - Clemon Campos.

Roda na instalacao local (Python embarcado). Antes de abrir o sistema:
  1. Verifica se ha versao nova no repositorio e atualiza a pasta app/.
  2. Inicia o Streamlit e abre o navegador no relatorio.

Tolerante a falta de internet: se nao conseguir verificar atualizacao,
inicia a versao ja instalada. Usa apenas a biblioteca padrao do Python.
"""

import io
import os
import sys
import time
import socket
import shutil
import zipfile
import subprocess
import urllib.request
import webbrowser
from pathlib import Path

# --- Repositorio de atualizacao (publico) -----------------------------------
REPO_USER = "pedroobarbosaa"
REPO_NAME = "relatorios-clemon-desktop"
BRANCH    = "main"

# API de conteudo do GitHub: reflete a versao na hora (o raw.githubusercontent
# tem cache de CDN de varios minutos, o que atrasaria a chegada das atualizacoes).
API_VERSION_URL = f"https://api.github.com/repos/{REPO_USER}/{REPO_NAME}/contents/app/VERSION?ref={BRANCH}"
ZIP_URL         = f"https://github.com/{REPO_USER}/{REPO_NAME}/archive/refs/heads/{BRANCH}.zip"

BASE    = Path(__file__).resolve().parent
APP_DIR = BASE / "app"
PORT    = 8501
URL     = f"http://localhost:{PORT}"


def _log(msg: str) -> None:
    print(msg, flush=True)


def _versao_local() -> str:
    f = APP_DIR / "VERSION"
    return f.read_text(encoding="utf-8").strip() if f.exists() else "0.0.0"


def _como_tupla(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0,)


def _baixar(url: str, timeout: int, headers: dict | None = None) -> bytes:
    h = {"User-Agent": "ClemonApp"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def verificar_atualizacao() -> None:
    """Baixa a versao remota; se for mais nova, substitui a pasta app/."""
    try:
        _log("Verificando atualizacoes...")
        remota = _baixar(
            API_VERSION_URL, timeout=10,
            headers={"Accept": "application/vnd.github.raw"},
        ).decode("utf-8").strip()
    except Exception as e:
        _log(f"Sem conexao para atualizar ({e}). Usando a versao instalada.")
        return

    local = _versao_local()
    if _como_tupla(remota) <= _como_tupla(local):
        _log(f"Ja esta na versao mais recente ({local}).")
        return

    _log(f"Nova versao disponivel: {remota} (atual {local}). Baixando...")
    tmp = BASE / "_update_tmp"
    antigo = BASE / "_app_old"
    try:
        dados = _baixar(ZIP_URL, timeout=120)
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        zipfile.ZipFile(io.BytesIO(dados)).extractall(tmp)
        # O zip do GitHub extrai como <REPO>-<BRANCH>/ na raiz
        raiz = next(p for p in tmp.iterdir() if p.is_dir())
        novo_app = raiz / "app"
        if not (novo_app / "app.py").exists():
            raise RuntimeError("pacote invalido (app.py ausente)")
        # Substituicao segura: so remove a app/ antiga depois de validar a nova
        if antigo.exists():
            shutil.rmtree(antigo, ignore_errors=True)
        if APP_DIR.exists():
            APP_DIR.rename(antigo)
        shutil.move(str(novo_app), str(APP_DIR))
        _log(f"Atualizado para a versao {remota}.")
    except Exception as e:
        _log(f"Falha ao atualizar ({e}). Usando a versao instalada.")
        if not APP_DIR.exists() and antigo.exists():
            antigo.rename(APP_DIR)  # restaura se a troca quebrou no meio
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(antigo, ignore_errors=True)


def _esperar_porta(timeout: int = 45) -> bool:
    fim = time.time() + timeout
    while time.time() < fim:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                time.sleep(1)  # folga para o Streamlit terminar de subir
                return True
        time.sleep(0.5)
    return False


def iniciar_app() -> None:
    _log("Iniciando o sistema...")
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        f"--server.port={PORT}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    env = os.environ.copy()
    browsers = BASE / "ms-playwright"
    if browsers.exists():  # navegador empacotado na instalacao
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    proc = subprocess.Popen(cmd, cwd=str(APP_DIR), env=env)
    if _esperar_porta():
        _log(f"Abrindo o navegador em {URL}")
        webbrowser.open(URL)
    else:
        _log("O servidor demorou a responder. Abra manualmente: " + URL)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


def main() -> None:
    _log("=== Relatorio Processual - Clemon Campos ===")
    verificar_atualizacao()
    iniciar_app()


if __name__ == "__main__":
    main()