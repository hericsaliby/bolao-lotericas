"""Leitura dos formatos da Caixa (sem internet: planilha montada no próprio teste)."""

import io
import unittest
import zipfile

import dados as D


def planilha(linhas):
    """Monta um .xlsx mínimo, no mesmo formato que a Caixa publica."""
    textos, xml_linhas = [], []
    for r, linha in enumerate(linhas, 1):
        celulas = []
        for c, valor in enumerate(linha):
            ref = f"{chr(65 + c)}{r}"
            if isinstance(valor, str) and not valor.replace(".", "").isdigit():
                textos.append(valor)
                celulas.append(f'<c r="{ref}" t="s"><v>{len(textos) - 1}</v></c>')
            else:
                celulas.append(f'<c r="{ref}"><v>{valor}</v></c>')
        xml_linhas.append(f'<row r="{r}">{"".join(celulas)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(
            f"<si><t>{t}</t></si>" for t in textos) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml",
                   f"<worksheet {ns}><sheetData>{''.join(xml_linhas)}</sheetData></worksheet>")
    return buf.getvalue()


class TestFormatos(unittest.TestCase):

    def test_numero(self):
        self.assertEqual(D._numero("R$1.234,56"), 1234.56)
        self.assertEqual(D._numero("12"), 12.0)
        self.assertIsNone(D._numero("-"))
        self.assertIsNone(D._numero(None))

    def test_acertos(self):
        self.assertEqual(D._acertos("6 acertos"), 6)
        self.assertEqual(D._acertos("Ganhadores 15 acertos"), 15)
        self.assertEqual(D._acertos("Ganhadores Nenhum Número"), 0)
        self.assertIsNone(D._acertos("Cidade / UF"))

    def test_planilha_da_caixa(self):
        conteudo = planilha([
            ["Concurso", "Data do Sorteio", "Bola1", "Bola2", "Bola3", "Bola4", "Bola5",
             "Bola6", "Ganhadores 6 acertos", "Rateio 6 acertos", "Ganhadores 5 acertos",
             "Rateio 5 acertos", "Ganhadores 4 acertos", "Rateio 4 acertos",
             "Arrecadação Total"],
            [3073, "22/10/2026", "04", "13", "23", "28", "41", "58", 0, "R$0,00", 203,
             "R$23.138,67", 13143, "R$510,55", "R$153.236.202,00"],
        ])
        saida = D.ler_planilha_caixa(conteudo)
        dezenas, premio = saida[3073]
        self.assertEqual(dezenas, [4, 13, 23, 28, 41, 58])
        self.assertEqual(premio["arrecadado"], 153236202.0)
        self.assertEqual(premio["faixas"]["4"], [13143, 510.55])
        self.assertEqual(premio["faixas"]["5"], [203, 23138.67])

    def test_consulta_da_caixa(self):
        num, dez, premio, info = D._ler_caixa({
            "numero": 3073, "dataApuracao": "22/10/2026",
            "listaDezenas": ["58", "04", "13", "23", "28", "41"],
            "listaRateioPremio": [{"descricaoFaixa": "4 acertos", "numeroDeGanhadores": 13143,
                                   "valorPremio": 510.55}],
            "valorArrecadado": 153236202.0, "numeroConcursoProximo": 3074,
            "dataProximoConcurso": "24/10/2026", "valorEstimadoProximoConcurso": 2.3e8,
            "acumulado": True})
        self.assertEqual((num, dez), (3073, [4, 13, 23, 28, 41, 58]))
        self.assertEqual(premio["faixas"]["4"], [13143, 510.55])
        self.assertEqual(info["proximo"], 3074)


if __name__ == "__main__":
    unittest.main()
