# Metodologia e resultados

Este documento explica as decisões do programa e os testes feitos com os dados
oficiais da Caixa. Números calculados em 23/10/2026.

## 1. Dados

- **Fonte:** planilha oficial de resultados da Caixa (botão *Download de resultados*
  de cada loteria), com todos os concursos: dezenas sorteadas, ganhadores e prêmio
  de cada faixa e valor arrecadado.
- **Volume:** Mega-Sena 3.073 concursos, Lotofácil 3.811 e Quina 7.149.
- **Conferência:** os 17.020 concursos foram comparados com uma segunda fonte
  pública. **0 diferenças** em dezenas e em número de ganhadores.
- **Detalhes técnicos:** a planilha `.xlsx` é lida sem bibliotecas externas (ela tem
  células numéricas com "-", que quebram leitores comuns). O endereço do serviço da
  Caixa é lido da própria página, porque a Caixa mudou de servidor
  (`servicebus2` → `servicebus3`) e o endereço antigo passou a responder 404. O último
  concurso vem da consulta oficial, e o programa tenta de novo quando a Caixa
  limita o número de pedidos (HTTP 429).

## 2. "Números quentes" não preveem nada

Hipótese testada: os 6 números que mais saíram nos últimos 50 concursos acertam
mais no concurso seguinte?

| Estratégia (Mega-Sena, 2.972 concursos) | Acertos médios por jogo |
|---|---|
| 6 números mais quentes | 0,639 |
| 6 números ao acaso | 0,601 |
| 6 números mais frios | 0,568 |
| Teoria (6 × 6/60) | 0,600 |

A diferença inicial **não se sustenta**:
- Nos concursos recentes (2.001 a 3.072) cai para 0,625, dentro da variação normal.
- Com janela de 10 concursos, os "quentes" acertam **menos** que o acaso (0,583).
- Com janela de 300 concursos, ficam iguais ao acaso (0,601).

**Conclusão:** cada sorteio é independente. O programa mostra quentes e frios
apenas como curiosidade e avisa que eles não aumentam a chance.

## 3. O que funciona: fugir dos números que o público mais aposta

O prêmio é **dividido** entre os ganhadores. A chance de ganhar não muda, mas o
**valor recebido** depende de quantas pessoas apostaram nos mesmos números.

### Evidência direta (Mega-Sena, 2.003 concursos)

Ganhadores de quadra por real arrecadado, comparados com os concursos vizinhos
(1,0 = normal):

| Números até 31 no sorteio | Ganhadores |
|---|---|
| 0 de 6 | 0,71 |
| 1 de 6 | 0,74 |
| 2 de 6 | 0,88 |
| 3 de 6 | 1,00 |
| 4 de 6 | 1,12 |
| 5 de 6 | 1,42 |
| 6 de 6 | 1,69 |

O público aposta muito em datas de aniversário (1 a 31). Exemplo real: o concurso
3.073 (04 13 23 28 41 58) teve 13.143 ganhadores de quadra, 1,36x o normal, e a
quadra pagou **R$ 510,55**. No concurso anterior, com números menos populares,
ela pagou **R$ 954,26**.

### Modelo de popularidade por número

Para cada concurso:

```
y = log(ganhadores da faixa mais comum / valor arrecadado)
    − mediana de y nos 20 concursos de cada lado    (tira o efeito de preço e da época)
```

Depois, uma regressão aditiva com regularização (ajustada por *backfitting*)
estima o "peso" de cada número: `y ≈ Σ peso(número sorteado)`. O modelo usa os
1.800 concursos mais recentes e a faixa com mais ganhadores (quadra na Mega,
11 pontos na Lotofácil, duque na Quina).

**Validação fora da amostra**, treinando nos concursos antigos e testando nos 300
mais recentes:

| Loteria | Correlação prevista × real | Ganhadores: 20% mais populares × 20% menos |
|---|---|---|
| Mega-Sena | **0,84** | 1,46x × 0,73x (≈ 2x de diferença) |
| Quina | **0,96** | 1,22x × 0,83x (≈ 1,5x) |
| Lotofácil | 0,81 | 1,09x × 0,93x (≈ 15%) |

Na Lotofácil o padrão é bem medido, mas o efeito no prêmio é pequeno: em 15 de 25
números todo mundo acaba marcando quase os mesmos números.

### Resultado no bolão

Bolão de 10 jogos com "evitar números populares" e "espalhar" ligados: se ganhar,
o prêmio esperado é **~1,5x** o de um jogo comum na Mega-Sena e **~1,25x** na Quina.

## 4. Espalhar os jogos do bolão

Os jogos são escolhidos um a um. Entre centenas de candidatos, ficam os 10% que
menos repetem números dos jogos já escolhidos (soma dos quadrados das
interseções); entre esses, vence o de menor popularidade. Isso não muda a chance
de cada jogo, mas reduz a dependência entre eles e aumenta a chance de **pelo
menos um** prêmio no bolão:

| Bolão de 10 jogos | Jogos ao acaso | Gerados pelo programa |
|---|---|---|
| Lotofácil (11+ pontos) | ~67% | ~73% |
| Quina (duque ou mais) | ~25,7% | ~27% |
| Mega-Sena (quadra ou mais) | 0,43% | 0,43% (sem diferença) |

Para jogos ao acaso, a referência é exata: `1 − (1 − p)^n`. Para o bolão gerado,
são simulados até 250 mil sorteios, e o programa só mostra diferença quando ela
passa de 2,5 erros-padrão.

Cuidado observado nos testes: "evitar populares" **sem** espalhar concentra os
jogos nos mesmos números (na Lotofácil, a chance de algum prêmio cai para 29%).
Por isso as duas opções vêm ligadas.

## 5. Quantos jogos fazer (simulação de 150 mil sorteios)

| Lotofácil (R$ 3,50) | Algum prêmio | 13+ pontos |
|---|---|---|
| 5 jogos (R$ 17,50) | 46% | 0,8% |
| 10 jogos (R$ 35) | 72% | 1,6% |
| 20 jogos (R$ 70) | 93% | 3,0% |

Em média, os prêmios menores devolvem 10% a 30% do valor apostado, conforme a
loteria. O restante é a chance do prêmio principal. O programa trata loteria como
diversão, não como investimento.

## 6. Limitações

- A popularidade é medida nas faixas menores (quadra, duque, 11 pontos) e usada
  como estimativa para o prêmio principal.
- As preferências do público mudam com o tempo, por isso o modelo usa só os
  concursos recentes e é recalculado a cada atualização.
- As chances seguem a tabela da Caixa, que arredonda para o inteiro mais próximo.
  Única diferença: na quadra da Quina, a conta dá 64.106,7, que arredonda para
  64.107, e a Caixa publica 64.106.
