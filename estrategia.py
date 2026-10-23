"""Como os jogos são escolhidos e avaliados.

Verdade importante: todo jogo tem a mesma chance de ser sorteado. O que dá para
melhorar é QUANTO se recebe ao ganhar (fugindo dos números que o público mais
aposta, o prêmio é dividido com menos gente) e a distribuição dos jogos do bolão
(jogos que repetem menos números entre si cobrem mais combinações).
"""

import math
import secrets
from fractions import Fraction
from math import comb, floor, log10

from dados import MODOS

ULTIMOS_N = 50  # concursos recentes usados nas estatísticas de quentes/frios

ESTILOS = {
    "populares": "Evitar números populares (recomendado)",
    "aleatorio": "Totalmente aleatório",
    "quentes": "Priorizar números quentes",
}


# ---------- básicos ----------

def numeros_de(cfg):
    return range(cfg["de"], cfg["ate"] + 1)


def ja_saiu(jogo, sorteados, cfg):
    """True se esse jogo já teria acertado o prêmio máximo em algum sorteio."""
    if cfg["aposta"] == cfg["sorteio"]:
        return tuple(jogo) in sorteados
    s = set(jogo)  # Lotomania: 50 marcados contêm os 20 de algum sorteio?
    return any(s.issuperset(d) for d in sorteados)


def frequencia_recente(resultados, cfg, n=ULTIMOS_N):
    freq = {d: 0 for d in numeros_de(cfg)}
    for num in sorted(resultados)[-n:]:
        for d in resultados[num]:
            freq[d] += 1
    return freq


def _sorteio_com_peso(rng, pesos, k):
    """Escolhe k números diferentes; peso maior = mais chance de entrar."""
    restantes = dict(pesos)
    escolhidos = []
    for _ in range(k):
        alvo = rng.uniform(0, sum(restantes.values()))
        acumulado = 0
        for numero, peso in restantes.items():
            acumulado += peso
            if acumulado >= alvo:
                break
        escolhidos.append(numero)
        del restantes[numero]
    return escolhidos


def tem_sequencia(jogo, tamanho=3):
    """Ex.: 21-22-23. Sequências são muito apostadas (gente marca em linha)."""
    seguidos = 1
    for a, b in zip(jogo, jogo[1:]):
        seguidos = seguidos + 1 if b == a + 1 else 1
        if seguidos >= tamanho:
            return True
    return False


# ---------- quais números o público prefere ----------

class ModeloPopularidade:
    """Estima quanto cada número é apostado pelo público.

    Ideia: em cada concurso, a Caixa publica quantas pessoas acertaram a faixa mais
    comum (ex.: quadra na Mega) e quanto foi arrecadado. Quando saem números muito
    apostados, há mais ganhadores que o normal. Uma regressão simples separa o
    "peso" de cada número. Conferido em concursos que o modelo não viu.
    """

    CONCURSOS = 1800

    def __init__(self, resultados, premios, cfg):
        self.cfg = cfg
        self.pesos = None
        linhas = self._linhas(resultados, premios)
        if len(linhas) < 200:
            return
        self.concursos_usados = len(linhas)
        self.pesos = self._ajustar(linhas)
        # normaliza: um jogo sorteado ao acaso vale 1,0 em média
        rng = secrets.SystemRandom()
        amostra = [rng.sample(numeros_de(cfg), cfg["aposta"]) for _ in range(3000)]
        self._norma = sum(math.exp(self._soma(j)) for j in amostra) / len(amostra)

    def _linhas(self, resultados, premios):
        ref = str(self.cfg["ref"])
        brutas = []
        for n in sorted(resultados):
            p = premios.get(n) or {}
            f, arrec = p.get("faixas", {}).get(ref), p.get("arrecadado")
            if f and f[0] > 0 and arrec:
                brutas.append((resultados[n], math.log(f[0] / arrec)))
        brutas = brutas[-self.CONCURSOS:]
        # tira a tendência (preço da aposta muda com o tempo): compara com os vizinhos
        ys = [y for _, y in brutas]
        linhas = []
        for i, (dz, y) in enumerate(brutas):
            viz = sorted(ys[max(0, i - 20):i + 21])
            linhas.append((dz, y - viz[len(viz) // 2]))
        return linhas

    def _ajustar(self, linhas, lam=10.0, voltas=40):
        nums = list(numeros_de(self.cfg))
        b = {d: 0.0 for d in nums}
        prev = [0.0] * len(linhas)
        onde = {d: [] for d in nums}
        for i, (dz, _) in enumerate(linhas):
            for d in dz:
                onde[d].append(i)
        for _ in range(voltas):
            for d in nums:
                s = sum(linhas[i][1] - prev[i] + b[d] for i in onde[d])
                novo = s / (len(onde[d]) + lam)
                for i in onde[d]:
                    prev[i] += novo - b[d]
                b[d] = novo
        return b

    def _soma(self, jogo):
        k = self.cfg["sorteio"] / self.cfg["aposta"]  # Lotomania: só 20 dos 50 contam
        return k * sum(self.pesos[d] for d in jogo)

    def divisao(self, jogo):
        """Quantas pessoas dividiriam o prêmio, comparado a um jogo comum (1,0)."""
        if not self.pesos:
            return 1.0
        return math.exp(self._soma(jogo)) / self._norma

    def premio_relativo(self, jogo):
        """Quanto o prêmio renderia comparado a um jogo comum (2,0 = o dobro)."""
        return 1 / self.divisao(jogo)

    def ranking(self):
        """Números do mais apostado para o menos apostado."""
        return sorted(self.pesos, key=lambda d: -self.pesos[d]) if self.pesos else []


# ---------- geração do bolão ----------

def gerar_bolao(modo, quantidade, resultados, gerados, estilo="populares",
                espalhar=True, modelo=None, fixos=()):
    """Gera jogos novos (nunca sorteados, nunca gerados antes).

    estilo: 'populares' prefere números pouco apostados; 'quentes' prefere os que
    mais saíram nos últimos concursos; 'aleatorio' não prefere nada.
    espalhar: cada jogo novo repete o mínimo possível de números dos anteriores.
    """
    cfg = MODOS[modo]
    rng = secrets.SystemRandom()
    sorteados = {tuple(d) for d in resultados.values()}
    usados = {tuple(j["dezenas"]) for j in gerados.get(modo, [])}
    fixos = tuple(sorted(set(fixos or ())))
    livres = [d for d in numeros_de(cfg) if d not in fixos]
    faltam = cfg["aposta"] - len(fixos)  # quantos o programa escolhe em cada jogo
    usar_modelo = estilo == "populares" and modelo is not None and modelo.pesos
    # sequência que já vem dos números da pessoa não é motivo para recusar o jogo
    filtrar_seq = estilo == "populares" and cfg["aposta"] <= 6 and not tem_sequencia(fixos)

    pesos = None
    if estilo == "quentes" and resultados:
        freq = frequencia_recente(resultados, cfg)
        pesos = {d: 1 + freq[d] ** 2 for d in livres}
    elif usar_modelo:
        # candidatos já puxados para os números pouco apostados
        escala = 4.0 / (max(modelo.pesos.values()) - min(modelo.pesos.values()) or 1)
        topo = max(modelo.pesos.values())
        pesos = {d: math.exp(-escala * (modelo.pesos[d] - topo)) for d in livres}

    tentativas = 600 if cfg["aposta"] <= 15 else 250
    escolhidos, conjuntos = [], []
    rodadas_sem_novo = 0
    while len(escolhidos) < quantidade and rodadas_sem_novo < 8:
        cands = set()
        for i in range(tentativas):
            if pesos and i % 2 == 0:  # metade puxada pelo estilo, metade livre
                resto = _sorteio_com_peso(rng, pesos, faltam)
            else:
                resto = rng.sample(livres, faltam)
            c = tuple(sorted(fixos + tuple(resto)))
            if c in usados:
                continue
            if filtrar_seq and tem_sequencia(c):
                continue
            cands.add(c)
        cands = [c for c in cands if not ja_saiu(c, sorteados, cfg)]
        if not cands:
            rodadas_sem_novo += 1  # com muitos números fixos as opções acabam
            continue
        rodadas_sem_novo = 0

        if espalhar and conjuntos:
            # os fixos estão em todos os jogos; espalha só a parte livre
            repet = {c: sum(len(s.intersection(c)) ** 2 for s in conjuntos) for c in cands}
            corte = sorted(repet.values())[max(0, len(cands) // 10 - 1)]
            cands = [c for c in cands if repet[c] <= corte]
        if usar_modelo:
            cands.sort(key=modelo.divisao)
        elif estilo == "quentes":
            freq = frequencia_recente(resultados, cfg)
            cands.sort(key=lambda c: -sum(freq[d] for d in c))
        else:
            rng.shuffle(cands)

        c = cands[0]
        escolhidos.append(c)
        conjuntos.append(set(c) - set(fixos))
        usados.add(c)
    return escolhidos


def ler_fixos(texto, cfg):
    """'07 13, 22' -> [7, 13, 22]. Levanta ValueError com explicação para a pessoa."""
    partes = texto.replace(",", " ").replace(";", " ").replace("-", " ").split()
    if not partes:
        return []
    try:
        nums = [int(p) for p in partes]
    except ValueError:
        raise ValueError("Em \"Meus números\" só pode ter números separados por espaço.")
    if len(set(nums)) != len(nums):
        raise ValueError("Em \"Meus números\" tem número repetido.")
    fora = [n for n in nums if not cfg["de"] <= n <= cfg["ate"]]
    if fora:
        raise ValueError(f"Na {cfg['nome']} os números vão de {cfg['de']:02d} a "
                         f"{cfg['ate']:02d}. Fora disso: {', '.join(map(str, fora))}.")
    if len(nums) >= cfg["aposta"]:
        raise ValueError(f"Na {cfg['nome']} dá para fixar até {cfg['aposta'] - 1} números "
                         f"(o jogo tem {cfg['aposta']}); o programa completa o resto.")
    return sorted(nums)


def jogos_possiveis(cfg, n_fixos):
    """Quantos jogos diferentes existem com n_fixos números fixos."""
    total = cfg["ate"] - cfg["de"] + 1
    return comb(total - n_fixos, cfg["aposta"] - n_fixos)


# ---------- avaliação ----------

def menor_faixa(cfg):
    return min(a for a in cfg["faixas"] if a > 0)


def chance_pelo_menos_um(jogos, cfg, sorteios):
    """Fração dos sorteios simulados em que o bolão teria pelo menos um prêmio."""
    alvo = menor_faixa(cfg)
    conjuntos = [set(j) for j in jogos]
    ganhou = 0
    for s in sorteios:
        if any(len(c.intersection(s)) >= alvo for c in conjuntos):
            ganhou += 1
    return ganhou / len(sorteios)


def avaliar_bolao(jogos, cfg, modelo=None):
    """Números para o resumo do bolão, comparando com jogos feitos ao acaso."""
    rng = secrets.SystemRandom()
    nums = list(numeros_de(cfg))
    n, total = len(jogos), len(nums)
    alvo = menor_faixa(cfg)
    # chance de 1 jogo ganhar algo (menor faixa ou mais), exata
    p1 = sum(chance_faixa(cfg, a) for a in range(alvo, cfg["sorteio"] + 1))
    # jogos ao acaso são independentes dado o sorteio: conta exata
    chance_acaso = 1 - (1 - p1) ** n
    # o bolão gerado: simulação (mais sorteios quando a chance é pequena)
    n_sim = int(min(250000, max(20000, 3_000_000 // max(1, n * cfg["aposta"] // 6))))
    sorteios = [rng.sample(nums, cfg["sorteio"]) for _ in range(n_sim)]
    chance = chance_pelo_menos_um(jogos, cfg, sorteios)
    erro = math.sqrt(max(chance * (1 - chance), 1e-12) / n_sim)
    pares = [len(set(a) & set(b)) for i, a in enumerate(jogos) for b in jogos[i + 1:]]
    r = {
        "jogos": n,
        "distintos": len(set().union(*map(set, jogos))) if jogos else 0,
        # quantos números diferentes jogos ao acaso usariam, em média
        "distintos_acaso": round(total * (1 - (1 - cfg["aposta"] / total) ** n)),
        "total_numeros": total,
        "maior_repeticao": max(pares, default=0),
        "chance": chance,
        "chance_acaso": chance_acaso,
        "diferenca_real": abs(chance - chance_acaso) > 2.5 * erro,
        "faixa": cfg["faixas"][alvo],
    }
    if modelo is not None and modelo.pesos:
        r["premio_medio"] = sum(modelo.premio_relativo(j) for j in jogos) / len(jogos)
    return r


# ---------- histórico e chances ----------

def contar_acertos(jogo, resultados):
    """{acertos: (vezes, último concurso)} em toda a história."""
    s = set(jogo)
    contagem = {}
    for num, dezenas in resultados.items():
        a = len(s.intersection(dezenas))
        vezes, ultimo = contagem.get(a, (0, 0))
        contagem[a] = (vezes + 1, max(ultimo, num))
    return contagem


def resumo_historico(jogo, resultados, cfg, recuo="           "):
    contagem = contar_acertos(jogo, resultados)
    partes = []
    for acertos, nome in cfg["faixas"].items():
        if acertos == 0:
            continue
        vezes, ultimo = contagem.get(acertos, (0, 0))
        partes.append(f"{nome}: {vezes}x" + (f" (último: conc. {ultimo})" if vezes else ""))
    return ("\n" + recuo).join(partes)


def chance_faixa(cfg, acertos, exata=False):
    total = cfg["ate"] - cfg["de"] + 1
    p = Fraction(comb(cfg["aposta"], acertos)
                 * comb(total - cfg["aposta"], cfg["sorteio"] - acertos),
                 comb(total, cfg["sorteio"]))
    return p if exata else float(p)


def porcentagem(p):
    pct = p * 100
    if pct <= 0:
        return "0%"
    casas = 2 if pct >= 0.01 else 1 - floor(log10(pct))
    return f"{pct:.{casas}f}".replace(".", ",") + "%"


def texto_chances(cfg):
    linhas = []
    for acertos, nome in cfg["faixas"].items():
        p = chance_faixa(cfg, acertos, exata=True)
        um_em = f"{round(1 / p):,}".replace(",", ".")  # igual à tabela da Caixa
        linhas.append(f"  {nome}: 1 em {um_em}  ({porcentagem(float(p))})")
    return "\n".join(linhas)


def texto_quentes_frios(resultados, cfg, n=ULTIMOS_N, quantos=10):
    freq = frequencia_recente(resultados, cfg, n)
    ordem = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    concursos = min(n, len(resultados))
    esperado = cfg["sorteio"] / len(freq) * 100

    def fmt(lista):
        return "\n".join(f"  {d:02d}: saiu {v}x  ({v / concursos * 100:.0f}% dos concursos)"
                         for d, v in lista)

    return (f"Nos últimos {concursos} concursos (o normal seria cada número sair em "
            f"{esperado:.0f}% deles):\n\n"
            f"MAIS SAÍRAM (quentes):\n{fmt(ordem[:quantos])}\n\n"
            f"MENOS SAÍRAM (frios):\n{fmt(ordem[-quantos:][::-1])}")


def texto_populares(modelo, quantos=10):
    r = modelo.ranking()
    if not r:
        return "Ainda não há dados de prêmios suficientes para esta loteria."

    def fmt(lista):
        return "  " + "  ".join(f"{d:02d}" for d in lista)

    return (f"MAIS APOSTADOS pelo público:\n{fmt(r[:quantos])}\n\n"
            f"MENOS APOSTADOS pelo público:\n{fmt(r[-quantos:][::-1])}\n\n"
            f"(medido em {modelo.concursos_usados} concursos, pelo número de ganhadores)")
