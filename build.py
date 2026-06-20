"""
Build do pacote desktop (Windows) do Relatorio Processual - Clemon Campos.

Gera dist/ClemonRelatorios/ pronto para empacotar num instalador:
  runtime/       -> Python relocavel + dependencias do app
  ms-playwright/ -> navegador Chromium do Playwright
  app/           -> codigo do sistema
  launcher.py    -> verifica atualizacao e inicia o app
  Iniciar Relatorios.bat

Roda com o Python do sistema. Requer internet (baixa ~350 MB).
"""

import io
import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT     = Path(__file__).resolve().parent
DIST     = ROOT / "dist" / "ClemonRelatorios"
RUNTIME  = DIST / "runtime"
BROWSERS = DIST / "ms-playwright"
PYSERIES = "3.12"  # serie com wheels garantidos para todas as deps


def baixar(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "clemon-build"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def achar_python_standalone() -> str:
    api = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
    rel = json.loads(baixar(api, timeout=60).decode("utf-8"))
    cands = [
        a["browser_download_url"] for a in rel["assets"]
        if a["name"].startswith(f"cpython-{PYSERIES}.")
        and a["name"].endswith("x86_64-pc-windows-msvc-install_only.tar.gz")
    ]
    if not cands:
        raise RuntimeError("asset do Python standalone nao encontrado no release")
    return sorted(cands)[-1]


def preparar_runtime() -> None:
    print(">>> Baixando Python standalone...", flush=True)
    url = achar_python_standalone()
    print("    ", url, flush=True)
    data = baixar(url)
    print(">>> Extraindo runtime...", flush=True)
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    tmp = DIST / "_py"
    if tmp.exists():
        shutil.rmtree(tmp)
    DIST.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        tf.extractall(tmp)
    shutil.move(str(tmp / "python"), str(RUNTIME))  # install_only extrai em python/
    shutil.rmtree(tmp, ignore_errors=True)


def py_exe() -> str:
    return str(RUNTIME / "python.exe")


def pip(*args: str) -> None:
    subprocess.check_call([py_exe(), "-m", "pip", *args])


def instalar_deps() -> None:
    print(">>> Instalando dependencias do app...", flush=True)
    pip("install", "--upgrade", "pip")
    pip("install", "-r", str(ROOT / "requirements.txt"))


def instalar_chromium() -> None:
    print(">>> Baixando o navegador Chromium do Playwright...", flush=True)
    if BROWSERS.exists():
        shutil.rmtree(BROWSERS)
    BROWSERS.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS)
    subprocess.check_call([py_exe(), "-m", "playwright", "install", "chromium"], env=env)


def copiar_app() -> None:
    print(">>> Copiando app/ e launcher.py...", flush=True)
    for nome in ("app", "launcher.py"):
        src, dst = ROOT / nome, DIST / nome
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)


def criar_bat() -> None:
    bat = DIST / "Iniciar Relatorios.bat"
    bat.write_text(
        '@echo off\r\n'
        'title Relatorio Processual - Clemon Campos\r\n'
        'cd /d "%~dp0"\r\n'
        '"runtime\\python.exe" launcher.py\r\n',
        encoding="utf-8",
    )


def main() -> None:
    preparar_runtime()
    instalar_deps()
    instalar_chromium()
    copiar_app()
    criar_bat()
    print("\n>>> Build concluido em:", DIST, flush=True)


if __name__ == "__main__":
    main()