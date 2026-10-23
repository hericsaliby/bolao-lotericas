"""Versão do programa e aviso de versão nova publicada no GitHub.

Para publicar uma versão nova: aumente VERSAO, gere o zip e crie no GitHub um
"Release" com a etiqueta v<VERSAO> anexando o zip (passo a passo em COMO_PUBLICAR.txt).
Quem estiver com uma versão mais antiga vê um aviso no topo da tela.
"""

import re

from dados import baixar_json

VERSAO = "1.0.0"

# "usuario/repositorio" no GitHub. Vazio = não procura versão nova.
REPO_GITHUB = "hericsaliby/bolao-lotericas"


def _tupla(versao):
    return tuple(int(x) for x in re.findall(r"\d+", versao or "")[:3])


def buscar_versao_nova():
    """Retorna {"versao", "pagina", "download"} se houver versão mais nova; senão None."""
    if not REPO_GITHUB:
        return None
    try:
        d = baixar_json(f"https://api.github.com/repos/{REPO_GITHUB}/releases/latest", 15)
    except Exception:
        return None  # sem internet ou GitHub fora do ar: tenta de novo depois
    tag = d.get("tag_name", "")
    if not tag or _tupla(tag) <= _tupla(VERSAO):
        return None
    zip_url = next((a.get("browser_download_url") for a in d.get("assets", [])
                    if a.get("name", "").lower().endswith(".zip")), None)
    return {"versao": tag.lstrip("vV"), "pagina": d.get("html_url"),
            "download": zip_url or d.get("html_url")}
