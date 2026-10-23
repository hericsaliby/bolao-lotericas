"""Conferência de prêmios e custo das apostas (regras da Caixa)."""

import unittest

import conferencia as C
from dados import MODOS

MEGA, LOTOFACIL, QUINA = MODOS["megasena"], MODOS["lotofacil"], MODOS["quina"]


class TestPremios(unittest.TestCase):

    def test_jogo_simples(self):
        premios, acertos = C.premios_do_jogo([1, 2, 3, 4, 50, 51], [1, 2, 3, 4, 5, 6], MEGA)
        self.assertEqual((premios, acertos), ({4: 1}, 4))

    def test_jogo_de_7_numeros_com_4_acertos_vale_3_quadras(self):
        premios, _ = C.premios_do_jogo([1, 2, 3, 4, 50, 51, 52], [1, 2, 3, 4, 5, 6], MEGA)
        self.assertEqual(premios, {4: 3})

    def test_jogo_de_7_numeros_com_sena_leva_tambem_6_quinas(self):
        premios, _ = C.premios_do_jogo([1, 2, 3, 4, 5, 6, 60], [1, 2, 3, 4, 5, 6], MEGA)
        self.assertEqual(premios, {6: 1, 5: 6})

    def test_sem_premio(self):
        premios, acertos = C.premios_do_jogo([10, 20, 30, 40, 50], [1, 2, 3, 4, 5], QUINA)
        self.assertEqual((premios, acertos), ({}, 0))


class TestCusto(unittest.TestCase):
    """Preço = jogo simples x combinações (tabela da Caixa)."""

    def test_precos(self):
        self.assertEqual(C.custo_jogos([list(range(1, 7))], MEGA), 6.0)
        self.assertEqual(C.custo_jogos([list(range(1, 8))], MEGA), 42.0)
        self.assertEqual(C.custo_jogos([list(range(1, 17))], LOTOFACIL), 56.0)
        self.assertEqual(C.custo_jogos([list(range(1, 7))], QUINA), 18.0)


class TestConferir(unittest.TestCase):

    def test_confere_e_soma_o_valor(self):
        apostas = []
        C.registrar(apostas, "megasena", 100, [[1, 2, 3, 4, 50, 51], [10, 11, 12, 13, 14, 15]])
        resultados = {"megasena": {100: [1, 2, 3, 4, 5, 6]}}
        premios = {"megasena": {100: {"arrecadado": 1e8,
                                      "faixas": {"6": [0, 0.0], "5": [10, 40000.0],
                                                 "4": [9000, 950.5]}}}}
        mudaram = C.conferir(apostas, resultados, premios)
        self.assertEqual(len(mudaram), 1)
        self.assertAlmostEqual(apostas[0]["resultado"]["total"], 950.5)
        gasto, ganho = C.balanco(apostas)
        self.assertEqual((gasto, ganho), (12.0, 950.5))
        # conferir de novo não muda nada
        self.assertEqual(C.conferir(apostas, resultados, premios), [])

    def test_concurso_ainda_nao_sorteado_fica_aguardando(self):
        apostas = []
        C.registrar(apostas, "quina", 999, [[1, 2, 3, 4, 5]])
        self.assertEqual(C.conferir(apostas, {"quina": {}}, {}), [])
        self.assertIsNone(apostas[0]["resultado"])

    def test_validar_jogo(self):
        self.assertEqual(C.validar_jogo("01 02 03 04 05 06 07", MEGA), list(range(1, 8)))
        for ruim in ("1 2 3", "1 2 3 4 5 61", "1 1 2 3 4 5", "a b c d e f"):
            with self.assertRaises(ValueError):
                C.validar_jogo(ruim, MEGA)


if __name__ == "__main__":
    unittest.main()
