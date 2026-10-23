"""Resultados e prêmios das loterias: download da Caixa e cache local.

Fontes, em ordem:
1. Site da Caixa: planilha oficial com o histórico completo (botão "Download de
   resultados" da página de cada loteria) e a consulta do último concurso.
2. Cópia pública (loteriascaixa-api), só se a Caixa estiver fora do ar.
"""

import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

# Arquivos ficam ao lado do programa (do .exe, quando empacotado)
PASTA = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent

# aposta = quantos números o jogo simples marca; sorteio = quantos a Caixa sorteia
# max_aposta = maior aposta permitida (jogos com mais números, comuns em bolão)
# ref = faixa com mais ganhadores, usada para medir quais números o público prefere
# planilha = nome da loteria no download da Caixa
# preco = jogo simples na Caixa (out/2026); jogo com mais números = preço x combinações
MODOS = {
    "megasena": {"nome": "Mega-Sena", "planilha": "Mega-Sena", "preco": 6.00, "aposta": 6, "max_aposta": 20,
                 "sorteio": 6, "de": 1, "ate": 60, "cor": "#209869", "ref": 4,
                 "faixas": {6: "SENA", 5: "quina", 4: "quadra"}},
    "lotofacil": {"nome": "Lotofácil", "planilha": "Lotofácil", "preco": 3.50, "aposta": 15, "max_aposta": 20,
                  "sorteio": 15, "de": 1, "ate": 25, "cor": "#930089", "ref": 11,
                  "faixas": {15: "15 pontos", 14: "14 pontos", 13: "13 pontos",
                             12: "12 pontos", 11: "11 pontos"}},
    "quina": {"nome": "Quina", "planilha": "Quina", "preco": 3.00, "aposta": 5, "max_aposta": 15,
              "sorteio": 5, "de": 1, "ate": 80, "cor": "#260085", "ref": 2,
              "faixas": {5: "QUINA", 4: "quadra", 3: "terno", 2: "duque"}},
}

URL_PARAMS = "https://loterias.caixa.gov.br/Style%20Library/json/params.txt"
API_CAIXA_PADRAO = "https://servicebus3.caixa.gov.br/portaldeloterias"
URL_COPIA = "https://loteriascaixa-api.herokuapp.com/api/{modo}"

_api_caixa = None


# ---------- download ----------

def baixar(url, timeout=30, tentativas=4):
    """GET com nova tentativa quando a Caixa pede para esperar (erro 429)."""
    for i in range(tentativas):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tentativas - 1:
                raise
            time.sleep(1.5 * (i + 1))


def baixar_json(url, timeout=30):
    return json.loads(baixar(url, timeout).decode("utf-8-sig"))


def api_caixa():
    """Endereço do serviço da Caixa, lido da própria página (a Caixa às vezes muda)."""
    global _api_caixa
    if _api_caixa is None:
        try:
            _api_caixa = baixar_json(URL_PARAMS, 15)["urlapiloterias"].rstrip("/")
        except Exception:
            _api_caixa = API_CAIXA_PADRAO
    return _api_caixa


# ---------- leitura dos formatos ----------

def _numero(txt):
    """'R$1.234,56' -> 1234.56; '12' -> 12.0; '-' ou vazio -> None."""
    if txt is None:
        return None
    t = str(txt).replace("R$", "").strip()
    if not t or t == "-":
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _acertos(descricao):
    d = descricao or ""
    if re.search(r"nenhum", d, re.I):
        return 0
    m = re.search(r"(\d+)\s*acerto", d, re.I)
    return int(m.group(1)) if m else None


def _ler_caixa(d):
    """Concurso da consulta da Caixa -> (numero, dezenas, premio, info do próximo)."""
    num = int(d["numero"])
    dezenas = sorted(int(x) for x in d["listaDezenas"])
    faixas = {}
    for p in d.get("listaRateioPremio") or []:
        a = _acertos(p.get("descricaoFaixa"))
        if a is not None:
            faixas[str(a)] = [p.get("numeroDeGanhadores") or 0, p.get("valorPremio") or 0.0]
    premio = {"arrecadado": d.get("valorArrecadado"), "faixas": faixas}
    info = {"ultimo": num, "data_ultimo": d.get("dataApuracao"), "dezenas_ultimo": dezenas,
            "proximo": d.get("numeroConcursoProximo"), "data": d.get("dataProximoConcurso"),
            "valor": d.get("valorEstimadoProximoConcurso"), "acumulou": d.get("acumulado")}
    return num, dezenas, premio, info


def _ler_copia(c):
    faixas = {}
    for p in c.get("premiacoes") or []:
        a = _acertos(p.get("descricao"))
        if a is not None:
            faixas[str(a)] = [p.get("ganhadores") or 0, p.get("valorPremio") or 0.0]
    return (int(c["concurso"]), sorted(int(x) for x in c["dezenas"]),
            {"arrecadado": c.get("valorArrecadado"), "faixas": faixas})


_XL = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _linhas_xlsx(conteudo):
    """Lê a 1ª aba de um .xlsx sem bibliotecas extras. Retorna lista de listas de texto."""
    z = zipfile.ZipFile(io.BytesIO(conteudo))
    textos = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(_XL + "si"):
            textos.append("".join(t.text or "" for t in si.iter(_XL + "t")))
    linhas = []
    for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(_XL + "row"):
        linha, i = [], -1
        for c in row.iter(_XL + "c"):
            ref = c.get("r")
            if ref:
                i = 0
                for ch in re.match(r"[A-Z]+", ref).group():
                    i = i * 26 + ord(ch) - 64
                i -= 1
            else:
                i += 1
            tipo, v = c.get("t"), c.find(_XL + "v")
            if tipo == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(_XL + "t"))
            elif v is None:
                val = None
            elif tipo == "s":
                val = textos[int(v.text)]
            else:
                val = v.text
            linha.extend([None] * (i - len(linha)))
            linha.append(val)
        linhas.append(linha)
    return linhas


def ler_planilha_caixa(conteudo):
    """Planilha de resultados da Caixa -> {concurso: (dezenas, premio)}."""
    linhas = _linhas_xlsx(conteudo)
    cab = [(c or "").strip() for c in linhas[0]]
    col_conc = cab.index("Concurso")
    col_bolas = [i for i, c in enumerate(cab) if re.fullmatch(r"Bola\s*\d+", c)]
    col_arrec = next(i for i, c in enumerate(cab) if c.lower().startswith("arrecada"))
    ganh = {_acertos(c): i for i, c in enumerate(cab) if c.lower().startswith("ganhadores")}
    rate = {_acertos(c): i for i, c in enumerate(cab) if c.lower().startswith("rateio")}
    saida = {}
    for lin in linhas[1:]:
        lin = lin + [None] * (len(cab) - len(lin))
        if not lin[col_conc] or not str(lin[col_conc]).strip().isdigit():
            continue
        dezenas = sorted(int(lin[i]) for i in col_bolas if lin[i] not in (None, ""))
        faixas = {}
        for a, i in ganh.items():
            g = _numero(lin[i])
            if a is not None and g is not None:
                faixas[str(a)] = [int(g), _numero(lin[rate[a]]) or 0.0 if a in rate else 0.0]
        saida[int(lin[col_conc])] = (dezenas, {"arrecadado": _numero(lin[col_arrec]),
                                               "faixas": faixas})
    return saida


# ---------- cache local ----------

def _arq(nome, modo):
    return PASTA / f"{nome}_{modo}.json"


def _ler(arq, padrao):
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def carregar_resultados(modo):
    """{concurso: [dezenas]}"""
    return {int(k): v for k, v in _ler(_arq("resultados", modo), {}).items()}


def carregar_premios(modo):
    """{concurso: {"arrecadado": valor, "faixas": {"4": [ganhadores, valor do prêmio]}}}"""
    return {int(k): v for k, v in _ler(_arq("premios", modo), {}).items()}


def _salvar(nome, modo, dados):
    _arq(nome, modo).write_text(
        json.dumps({str(k): v for k, v in sorted(dados.items())}), encoding="utf-8")


ARQ_PROXIMO = PASTA / "proximos_concursos.json"


def carregar_proximos():
    return _ler(ARQ_PROXIMO, {})


def salvar_proximos(proximos):
    ARQ_PROXIMO.write_text(json.dumps(proximos, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- atualização ----------

def _premio_vazio(p):
    return not p or not p.get("faixas")


def _faltando(resultados, premios, ultimo):
    falta = {n for n in range(1, ultimo + 1) if n not in resultados or n not in premios}
    # prêmios dos últimos dias às vezes saem depois do resultado: busca de novo
    falta |= {n for n in range(max(1, ultimo - 3), ultimo + 1) if _premio_vazio(premios.get(n))}
    return falta


def atualizar_resultados(modo):
    """Traz tudo em dia. Retorna (resultados, premios, info_proximo, online, fonte)."""
    cfg = MODOS[modo]
    resultados = carregar_resultados(modo)
    premios = carregar_premios(modo)
    info, fonte = None, ""

    # 1) Último concurso e próximo sorteio, direto da Caixa
    try:
        num, dez, prem, info = _ler_caixa(baixar_json(f"{api_caixa()}/api/{modo}/"))
        resultados[num], premios[num] = dez, prem
        fonte = "Caixa"
    except Exception:
        try:  # Caixa fora do ar: cópia pública
            c = baixar_json(URL_COPIA.format(modo=modo) + "/latest")
            num, dez, prem = _ler_copia(c)
            resultados[num], premios[num] = dez, prem
            info = {"ultimo": num, "data_ultimo": c.get("data"), "dezenas_ultimo": dez,
                    "proximo": c.get("proximoConcurso"), "data": c.get("dataProximoConcurso"),
                    "valor": c.get("valorEstimadoProximoConcurso"), "acumulou": c.get("acumulou")}
            fonte = "cópia pública (Caixa fora do ar)"
        except Exception:
            pass

    if info:
        falta = _faltando(resultados, premios, info["ultimo"])

        # 2) Falta mais que uns poucos: planilha oficial completa da Caixa
        if len(falta) > 5:
            try:
                url = (f"{api_caixa()}/api/resultados/download?modalidade="
                       + urllib.parse.quote(cfg["planilha"]))
                for num, (dez, prem) in ler_planilha_caixa(baixar(url, 90)).items():
                    resultados[num] = dez
                    if not _premio_vazio(prem) or num not in premios:
                        premios[num] = prem
            except Exception:
                try:  # reserva: cópia pública
                    for c in baixar_json(URL_COPIA.format(modo=modo), timeout=90):
                        num, dez, prem = _ler_copia(c)
                        resultados[num] = dez
                        if not _premio_vazio(prem) or num not in premios:
                            premios[num] = prem
                except Exception:
                    pass
            falta = _faltando(resultados, premios, info["ultimo"])

        # 3) O que ainda falta: concurso a concurso na Caixa (só os mais recentes)
        for n in sorted(falta, reverse=True)[:20]:
            try:
                num, dez, prem, _ = _ler_caixa(baixar_json(f"{api_caixa()}/api/{modo}/{n}"))
                resultados[num], premios[num] = dez, prem
            except Exception:
                break

    if resultados:
        _salvar("resultados", modo, resultados)
        _salvar("premios", modo, premios)
    online = info is not None
    if not online:
        info = carregar_proximos().get(modo)
    return resultados, premios, info, online, fonte
