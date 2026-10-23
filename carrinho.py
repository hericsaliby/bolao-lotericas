"""Carrinho: jogos que a pessoa separou para decidir depois se aposta ou não.

Fluxo: gera os jogos -> marca os que gostou -> "Pôr no carrinho" -> no carrinho,
marca e escolhe "Registrar como apostados" (vão para Minhas apostas) ou "Remover".
"""

import json
from datetime import datetime

from dados import MODOS, PASTA

ARQ_CARRINHO = PASTA / "carrinho.json"


def carregar_carrinho():
    try:
        itens = json.loads(ARQ_CARRINHO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [i for i in itens if i.get("modo") in MODOS]  # ignora loterias que saíram


def salvar_carrinho(itens):
    ARQ_CARRINHO.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")


def adicionar(itens, modo, jogos):
    """Põe jogos no carrinho (sem duplicar). Retorna quantos entraram."""
    ja = {(i["modo"], tuple(i["dezenas"])) for i in itens}
    proximo_id = max((i["id"] for i in itens), default=0) + 1
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    novos = 0
    for j in jogos:
        dez = sorted(int(d) for d in j)
        if (modo, tuple(dez)) in ja:
            continue
        itens.append({"id": proximo_id, "modo": modo, "dezenas": dez, "adicionado_em": agora})
        ja.add((modo, tuple(dez)))
        proximo_id += 1
        novos += 1
    return novos


def remover(itens, ids):
    """Tira do carrinho os itens com esses ids. Retorna a lista nova."""
    ids = set(ids)
    return [i for i in itens if i["id"] not in ids]


def por_loteria(itens):
    """{modo: [itens]} na ordem das loterias do programa."""
    grupos = {m: [] for m in MODOS}
    for i in itens:
        grupos[i["modo"]].append(i)
    return {m: g for m, g in grupos.items() if g}
