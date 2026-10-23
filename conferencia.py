"""Apostas registradas pelo bolão e conferência automática com os resultados.

Aceita jogos simples e jogos com mais números (ex.: Mega com 7 a 20 números):
um jogo de 8 números que acerta 4 vale várias quadras, como na Caixa.
"""

import json
from datetime import datetime
from math import comb

from dados import MODOS, PASTA

ARQ_APOSTAS = PASTA / "apostas.json"


def carregar_apostas():
    try:
        return json.loads(ARQ_APOSTAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def salvar_apostas(apostas):
    ARQ_APOSTAS.write_text(json.dumps(apostas, ensure_ascii=False, indent=1), encoding="utf-8")


def custo_jogos(jogos, cfg):
    """Preço na Caixa: jogo com mais números vale todas as combinações simples dentro dele."""
    return sum(cfg["preco"] * comb(len(j), cfg["aposta"]) for j in jogos)


def custo_aposta(ap):
    """Usa o preço guardado no registro; apostas antigas usam o preço atual."""
    if ap.get("custo") is not None:
        return ap["custo"]
    return custo_jogos(ap["jogos"], MODOS[ap["modo"]])


def registrar(apostas, modo, concurso, jogos, origem="gerado"):
    """Adiciona uma aposta (lista de jogos para um concurso). Retorna o id."""
    novo_id = max((a["id"] for a in apostas), default=0) + 1
    jogos = [sorted(int(d) for d in j) for j in jogos]
    apostas.append({
        "id": novo_id, "modo": modo, "concurso": int(concurso), "jogos": jogos,
        "custo": custo_jogos(jogos, MODOS[modo]),
        "origem": origem, "registrado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "resultado": None,
    })
    return novo_id


def balanco(apostas):
    """(gasto, ganho) somando as apostas das loterias do programa."""
    validas = [a for a in apostas if a.get("modo") in MODOS]
    gasto = sum(custo_aposta(a) for a in validas)
    ganho = sum((a.get("resultado") or {}).get("total", 0) for a in validas)
    return gasto, ganho


def validar_jogo(texto, cfg):
    """'01 02 03 04 05 06' -> lista de números, ou levanta ValueError com a explicação."""
    partes = texto.replace(",", " ").replace("-", " ").split()
    try:
        nums = sorted({int(p) for p in partes})
    except ValueError:
        raise ValueError(f"'{texto}' tem algo que não é número.")
    if len(nums) != len(partes):
        raise ValueError(f"'{texto}' tem número repetido.")
    fora = [n for n in nums if n < cfg["de"] or n > cfg["ate"]]
    if fora:
        raise ValueError(f"Números fora de {cfg['de']:02d}-{cfg['ate']:02d}: {fora}")
    if not cfg["aposta"] <= len(nums) <= cfg["max_aposta"]:
        faixa = (str(cfg["aposta"]) if cfg["aposta"] == cfg["max_aposta"]
                 else f"{cfg['aposta']} a {cfg['max_aposta']}")
        raise ValueError(f"{cfg['nome']} aceita {faixa} números por jogo; "
                         f"'{texto}' tem {len(nums)}.")
    return nums


def premios_do_jogo(jogo, sorteadas, cfg):
    """{acertos da faixa: quantidade de prêmios} para um jogo (simples ou com mais números)."""
    acertos = len(set(jogo) & set(sorteadas))
    n = len(jogo)
    if n == cfg["aposta"] or cfg["aposta"] != cfg["sorteio"]:
        return ({acertos: 1} if acertos in cfg["faixas"] else {}), acertos
    # jogo com mais números = todas as combinações simples dentro dele
    simples = cfg["aposta"]
    premios = {}
    for faixa in cfg["faixas"]:
        if faixa <= acertos:
            qtd = comb(acertos, faixa) * comb(n - acertos, simples - faixa)
            if qtd:
                premios[faixa] = qtd
    return premios, acertos


def conferir(apostas, resultados, premios):
    """Confere as apostas cujo concurso já saiu. Retorna as que mudaram agora.

    resultados/premios: {modo: {concurso: ...}}.
    """
    mudaram = []
    for ap in apostas:
        if ap.get("modo") not in MODOS:  # loteria que saiu do programa
            continue
        r_ant = ap.get("resultado")
        if r_ant and r_ant.get("valores_completos"):
            continue
        sorteadas = resultados.get(ap["modo"], {}).get(ap["concurso"])
        if not sorteadas:
            continue
        cfg = MODOS[ap["modo"]]
        faixas_valor = (premios.get(ap["modo"], {}).get(ap["concurso"]) or {}).get("faixas", {})
        jogos, total, completos = [], 0.0, True
        for j in ap["jogos"]:
            prem, acertos = premios_do_jogo(j, sorteadas, cfg)
            valor = 0.0
            for faixa, qtd in prem.items():
                v = faixas_valor.get(str(faixa))
                if v is None:
                    completos = False  # Caixa ainda não divulgou o valor
                else:
                    valor += qtd * (v[1] or 0.0)
            total += valor
            jogos.append({"acertos": acertos, "premios": {str(k): q for k, q in prem.items()},
                          "valor": valor})
        novo = {"dezenas": sorteadas, "jogos": jogos, "total": total,
                "valores_completos": completos}
        if novo != r_ant:
            ap["resultado"] = novo
            mudaram.append(ap)
    return mudaram


def _reais(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def descrever_premios(prem, cfg):
    partes = []
    for faixa, qtd in sorted(((int(k), q) for k, q in prem.items()), reverse=True):
        nome = cfg["faixas"].get(faixa, f"{faixa} acertos")
        if qtd == 1:
            partes.append(nome)
        elif nome.endswith("pontos"):
            partes.append(f"{qtd}x {nome}")
        else:
            partes.append(f"{qtd} {nome}s")  # 3 quadras, 6 quinas
    return " + ".join(partes)


def texto_aposta(ap):
    cfg = MODOS[ap["modo"]]
    cab = (f"#{ap['id']}  {cfg['nome']}  —  concurso {ap['concurso']}  "
           f"({len(ap['jogos'])} jogo{'s' if len(ap['jogos']) > 1 else ''}, "
           f"{_reais(custo_aposta(ap))}, registrado em {ap['registrado_em']})")
    linhas = [cab]
    res = ap.get("resultado")
    if not res:
        linhas.append("   Aguardando o sorteio.")
        for i, j in enumerate(ap["jogos"], 1):
            linhas.append(f"   Jogo {i:>2}: " + " ".join(f"{d:02d}" for d in j))
        return "\n".join(linhas)

    linhas.append("   Sorteadas: " + " ".join(f"{d:02d}" for d in res["dezenas"]))
    sorteadas = set(res["dezenas"])
    for i, (j, r) in enumerate(zip(ap["jogos"], res["jogos"]), 1):
        marcados = " ".join(f"[{d:02d}]" if d in sorteadas else f" {d:02d} " for d in j)
        info = f"{r['acertos']} acerto{'s' if r['acertos'] != 1 else ''}"
        if r["premios"]:
            info += " → " + descrever_premios(r["premios"], cfg)
            info += f" = {_reais(r['valor'])}" if r["valor"] else " (valor ainda não divulgado)"
        linhas.append(f"   Jogo {i:>2}: {marcados}   {info}")
    if res["total"]:
        linhas.append(f"   TOTAL GANHO: {_reais(res['total'])}")
    elif any(r["premios"] for r in res["jogos"]):
        linhas.append("   Premiado! Valor ainda não divulgado pela Caixa.")
    else:
        linhas.append("   Nenhum prêmio desta vez.")
    return "\n".join(linhas)


def resumo_aviso(mudaram):
    """Texto curto para o aviso que aparece quando sai resultado."""
    linhas = []
    for ap in mudaram:
        cfg = MODOS[ap["modo"]]
        res = ap["resultado"]
        premiados = [(i, r) for i, r in enumerate(res["jogos"], 1) if r["premios"]]
        if not premiados:
            linhas.append(f"{cfg['nome']} {ap['concurso']}: nenhum prêmio "
                          f"({len(ap['jogos'])} jogos conferidos).")
            continue
        partes = [f"jogo {i}: {descrever_premios(r['premios'], cfg)}" for i, r in premiados]
        total = f" — total {_reais(res['total'])}" if res["total"] else ""
        linhas.append(f"{cfg['nome']} {ap['concurso']}: " + "; ".join(partes) + total)
    return "\n".join(linhas)
