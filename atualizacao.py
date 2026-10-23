"""Versão do programa e aviso de versão nova publicada no GitHub.

A versão publicada fica no arquivo download/versao.json do repositório, junto
com o zip (download/Gerador-Bolao.zip). Quem estiver com versão mais antiga vê
um aviso no topo da tela. Como publicar: COMO_PUBLICAR.txt.
"""

import re

from dados import baixar_json

VERSAO = "1.0.0"

# "usuario/repositorio" no GitHub. Vazio = não procura versão nova.
REPO_GITHUB = "hericsaliby/bolao-lotericas"

URL_VERSAO = "https://raw.githubusercontent.com/{repo}/main/download/versao.json"
URL_ZIP = "https://github.com/{repo}/raw/main/download/Gerador-Bolao.zip"


def _tupla(versao):
    return tuple(int(x) for x in re.findall(r"\d+", versao or "")[:3])


def interpretar(info, versao_atual=None, repo=None):
    """versao.json publicado -> {"versao", "download", "notas"} se for mais novo; senão None."""
    versao_atual = versao_atual or VERSAO
    repo = repo or REPO_GITHUB
    publicada = str((info or {}).get("versao", ""))
    if not publicada or _tupla(publicada) <= _tupla(versao_atual):
        return None
    return {"versao": publicada,
            "download": info.get("download") or URL_ZIP.format(repo=repo),
            "notas": info.get("notas", "")}


def buscar_versao_nova():
    """Consulta o GitHub. Sem internet ou sem arquivo: None (tenta de novo depois)."""
    if not REPO_GITHUB:
        return None
    try:
        info = baixar_json(URL_VERSAO.format(repo=REPO_GITHUB), 15)
    except Exception:
        return None
    return interpretar(info)
