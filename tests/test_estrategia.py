"""Regras de geração e as chances de cada prêmio."""

import random
import unittest

import estrategia as E
from dados import MODOS

MEGA, LOTOFACIL, QUINA = MODOS["megasena"], MODOS["lotofacil"], MODOS["quina"]


def resultados_falsos(cfg, n=400, semente=1):
    rng = random.Random(semente)
    nums = list(range(cfg["de"], cfg["ate"] + 1))
    return {i: sorted(rng.sample(nums, cfg["sorteio"])) for i in range(1, n + 1)}


class TestChances(unittest.TestCase):
    """Os valores "1 em X" têm que bater com a tabela publicada pela Caixa."""

    def um_em(self, cfg, acertos):
        return round(1 / E.chance_faixa(cfg, acertos, exata=True))

    def test_mega_sena(self):
        self.assertEqual(self.um_em(MEGA, 6), 50_063_860)
        self.assertEqual(self.um_em(MEGA, 5), 154_518)
        self.assertEqual(self.um_em(MEGA, 4), 2_332)

    def test_lotofacil(self):
        esperado = {15: 3_268_760, 14: 21_792, 13: 692, 12: 60, 11: 11}
        for acertos, valor in esperado.items():
            self.assertEqual(self.um_em(LOTOFACIL, acertos), valor)

    def test_quina(self):
        self.assertEqual(self.um_em(QUINA, 5), 24_040_016)
        self.assertEqual(self.um_em(QUINA, 3), 866)
        self.assertEqual(self.um_em(QUINA, 2), 36)

    def test_probabilidades_somam_um(self):
        for cfg in (MEGA, LOTOFACIL, QUINA):
            total = sum(E.chance_faixa(cfg, a) for a in range(cfg["sorteio"] + 1))
            self.assertAlmostEqual(total, 1.0)


class TestGeracao(unittest.TestCase):

    def test_jogos_validos_unicos_e_nunca_sorteados(self):
        for modo, cfg in (("megasena", MEGA), ("lotofacil", LOTOFACIL), ("quina", QUINA)):
            res = resultados_falsos(cfg)
            for estilo in E.ESTILOS:
                jogos = E.gerar_bolao(modo, 15, res, {}, estilo=estilo)
                self.assertEqual(len(jogos), 15)
                self.assertEqual(len(set(jogos)), 15, "jogo repetido")
                sorteados = {tuple(d) for d in res.values()}
                for j in jogos:
                    self.assertEqual(len(set(j)), cfg["aposta"])
                    self.assertTrue(all(cfg["de"] <= d <= cfg["ate"] for d in j))
                    self.assertNotIn(tuple(j), sorteados)

    def test_nao_repete_jogo_ja_gerado(self):
        res = resultados_falsos(QUINA)
        primeiros = E.gerar_bolao("quina", 20, res, {})
        gerados = {"quina": [{"dezenas": list(j)} for j in primeiros]}
        segundos = E.gerar_bolao("quina", 20, res, gerados)
        self.assertFalse(set(primeiros) & set(segundos))

    def test_numeros_fixos_em_todos_os_jogos(self):
        res = resultados_falsos(MEGA)
        jogos = E.gerar_bolao("megasena", 10, res, {}, fixos=[7, 13])
        self.assertTrue(all({7, 13} <= set(j) for j in jogos))

    def test_para_quando_acabam_as_opcoes(self):
        # 5 fixos na Mega: só existem 55 jogos possíveis
        self.assertEqual(E.jogos_possiveis(MEGA, 5), 55)
        jogos = E.gerar_bolao("megasena", 80, {}, {}, fixos=[1, 2, 3, 4, 5])
        self.assertEqual(len(jogos), 55)

    def test_espalhar_repete_menos_numeros(self):
        res = resultados_falsos(MEGA)
        jogos = E.gerar_bolao("megasena", 10, res, {}, estilo="aleatorio", espalhar=True)
        pares = [len(set(a) & set(b)) for i, a in enumerate(jogos) for b in jogos[i + 1:]]
        self.assertLessEqual(max(pares), 2)

    def test_ler_fixos(self):
        self.assertEqual(E.ler_fixos("07 13, 22", MEGA), [7, 13, 22])
        self.assertEqual(E.ler_fixos("", MEGA), [])
        for ruim in ("61", "07 07", "abc", "1 2 3 4 5 6"):
            with self.assertRaises(ValueError):
                E.ler_fixos(ruim, MEGA)

    def test_resumo_historico_mostra_0x(self):
        texto = E.resumo_historico([1, 2, 3, 4, 5, 6], {1: [10, 11, 12, 13, 14, 15]}, MEGA)
        self.assertIn("SENA: 0x", texto)
        self.assertNotIn("nunca", texto)


class TestModeloPopularidade(unittest.TestCase):
    """Com dados simulados em que 1..10 são 'populares', o modelo tem que achá-los."""

    def test_encontra_os_numeros_populares(self):
        rng = random.Random(3)
        resultados, premios = {}, {}
        for n in range(1, 900):
            dz = sorted(rng.sample(range(1, 61), 6))
            populares = sum(d <= 10 for d in dz)
            ganhadores = int(5000 * (1.3 ** populares) * rng.uniform(0.9, 1.1))
            resultados[n] = dz
            premios[n] = {"arrecadado": 1e8, "faixas": {"4": [ganhadores, 900.0]}}
        modelo = E.ModeloPopularidade(resultados, premios, MEGA)
        acertou = set(modelo.ranking()[:10]) & set(range(1, 11))
        self.assertGreaterEqual(len(acertou), 9)
        jogo_popular, jogo_raro = [1, 2, 3, 4, 5, 6], [41, 45, 50, 52, 55, 58]
        self.assertGreater(modelo.premio_relativo(jogo_raro), modelo.premio_relativo(jogo_popular))


if __name__ == "__main__":
    unittest.main()
