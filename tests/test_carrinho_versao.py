"""Carrinho e comparação de versões."""

import unittest

import atualizacao as A
import carrinho as K


class TestCarrinho(unittest.TestCase):

    def test_adicionar_sem_duplicar(self):
        itens = []
        self.assertEqual(K.adicionar(itens, "megasena", [[6, 5, 4, 3, 2, 1], [7, 8, 9, 10, 11, 12]]), 2)
        self.assertEqual(K.adicionar(itens, "megasena", [[1, 2, 3, 4, 5, 6]]), 0)
        self.assertEqual(itens[0]["dezenas"], [1, 2, 3, 4, 5, 6])
        # mesmo jogo em outra loteria é outro item
        self.assertEqual(K.adicionar(itens, "quina", [[1, 2, 3, 4, 5]]), 1)

    def test_remover_e_agrupar(self):
        itens = []
        K.adicionar(itens, "quina", [[1, 2, 3, 4, 5]])
        K.adicionar(itens, "megasena", [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]])
        grupos = K.por_loteria(itens)
        self.assertEqual(list(grupos), ["megasena", "quina"])  # ordem das loterias
        itens = K.remover(itens, [itens[1]["id"]])
        self.assertEqual(len(itens), 2)


class TestVersao(unittest.TestCase):

    def test_comparacao(self):
        self.assertGreater(A._tupla("v1.10.0"), A._tupla("1.9.3"))
        self.assertEqual(A._tupla("v1.0.0"), A._tupla("1.0.0"))


if __name__ == "__main__":
    unittest.main()
