# Relatório Processual — Clemon Campos

Aplicativo desktop que consulta processos por CPF ou CNPJ em tribunais públicos
(TJDFT 1º/2º grau, TJPE, TJMA, TRF1, TJGO e TJSP) e gera um relatório em PDF.
Roda localmente na máquina do usuário e se atualiza sozinho a partir deste
repositório a cada vez que é aberto.

## Estrutura

- `app/` — código do sistema (Streamlit + scrapers + gerador de PDF). É a pasta
  que o launcher atualiza automaticamente. O arquivo `app/VERSION` controla a
  versão publicada.
- `launcher.py` — verifica atualização, baixa a versão nova se houver e inicia o
  app no navegador. Usa apenas a biblioteca padrão do Python.
- `requirements.txt` — dependências do app (instaladas no pacote, não pelo usuário).

## Publicar uma atualização

1. Altere o código em `app/`.
2. Incremente o número em `app/VERSION` (ex.: `1.0.0` → `1.0.1`).
3. Faça commit e push para a branch `main`.

Na próxima vez que o usuário abrir o app, o launcher detecta a versão nova e
atualiza sozinho.