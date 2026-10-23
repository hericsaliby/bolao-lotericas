"""Gerador do bolão: Mega-Sena, Lotofácil e Quina.

- Gera jogos nunca sorteados e nunca repetidos.
- Foge dos números que o público mais aposta (se ganhar, divide com menos gente).
- Espalha os jogos do bolão para repetirem o mínimo de números entre si.
- Guarda as apostas feitas e confere sozinho quando sai o resultado.

Partes: dados.py (Caixa e cache), estrategia.py (escolha dos jogos),
conferencia.py (apostas e prêmios), este arquivo (tela).
"""

import json
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk

import atualizacao as A
import carrinho as K
import conferencia as C
import estrategia as E
from dados import (MODOS, PASTA, atualizar_resultados, carregar_premios, carregar_proximos,
                   carregar_resultados, salvar_proximos)

ARQ_GERADOS = PASTA / "jogos_gerados.json"
ATUALIZA_MIN = 15  # de quantos em quantos minutos busca resultados sozinho
RECUO = "           "
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]

# Quão forte é o efeito de fugir dos números populares em cada loteria
# (medido em concursos que o modelo não viu; ver estrategia.ModeloPopularidade)
FORCA_EFEITO = {
    "megasena": "forte: sorteios com números populares têm ~2x mais ganhadores",
    "quina": "médio: sorteios com números populares têm ~1,5x mais ganhadores",
    "lotofacil": "pequeno: diferença de ~15% no número de ganhadores",
}


def reais(valor):
    if valor is None:
        return "—"
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def vezes(x):
    return f"{x:.2f}".replace(".", ",") + "x"


def n_jogos(n):
    """1 jogo / 2 jogos."""
    return f"{n} jogo" + ("s" if n != 1 else "")


def descrever_data(data_txt):
    try:
        d = datetime.strptime(data_txt, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return data_txt or "—"
    dias = (d - datetime.now().date()).days
    prefixo = "HOJE, " if dias == 0 else "amanhã, " if dias == 1 else ""
    return f"{prefixo}{DIAS[d.weekday()]}, {data_txt}"


def formatar(jogo, por_linha=None, marcar=()):
    """Números lado a lado; os de 'marcar' (números da pessoa) ganham um *."""
    if marcar:
        dez, sep = [f"{d:02d}{'*' if d in marcar else ' '}" for d in jogo], " "
    else:
        dez, sep = [f"{d:02d}" for d in jogo], "  "
    if not por_linha or len(dez) <= por_linha:
        return sep.join(dez)
    return ("\n" + RECUO).join(sep.join(dez[i:i + por_linha])
                               for i in range(0, len(dez), por_linha))


ARQ_PREFS = PASTA / "preferencias.json"


def carregar_prefs():
    try:
        return json.loads(ARQ_PREFS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar_prefs(prefs):
    try:
        ARQ_PREFS.write_text(json.dumps(prefs, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def carregar_gerados():
    try:
        return json.loads(ARQ_GERADOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar_gerados(gerados):
    ARQ_GERADOS.write_text(json.dumps(gerados, ensure_ascii=False, indent=1), encoding="utf-8")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Bolão da Sala - Gerador de Jogos  (versão {A.VERSAO})")
        self.geometry("820x860")
        self.minsize(700, 600)
        self.modo = tk.StringVar(value="megasena")
        self.qtd = tk.IntVar(value=10)
        self.estilo = tk.StringVar(value=E.ESTILOS["populares"])
        self.espalhar = tk.BooleanVar(value=True)
        self.prefs = carregar_prefs()
        self.prefs.setdefault("fixos", {})
        self.fixos_txt = tk.StringVar(value=self.prefs["fixos"].get("megasena", ""))
        self.resultados = {m: carregar_resultados(m) for m in MODOS}
        self.premios = {m: carregar_premios(m) for m in MODOS}
        self.modelos = {}
        self.proximos = carregar_proximos()
        self.gerados = carregar_gerados()
        for m in MODOS:
            self.gerados.setdefault(m, [])
        self.apostas = C.carregar_apostas()
        self.online = False
        self.hora_atualizacao = None
        self.atualizando = False
        self.gerando = False
        self.ultimos = []        # textos para copiar
        self.ultimos_jogos = []  # (modo, jogos) gerados por último
        self.marcados = []       # um BooleanVar por jogo gerado (caixinhas)
        self._widgets_saida = []  # caixinhas embutidas no texto
        self.carrinho = K.carregar_carrinho()
        self.janela_apostas = None
        self.janela_carrinho = None
        self._montar()
        self._trocar_modo()
        self._auto_atualizar()
        self._checar_versao()

    # ---------- montagem da tela ----------

    def _montar(self):
        # Aviso de versão nova (só aparece quando há uma publicada no GitHub)
        self.aviso_versao = tk.Label(self, bg="#ffd54f", fg="#000", cursor="hand2",
                                     font=("Segoe UI", 10, "bold"), pady=6)
        self.aviso_versao.bind("<Button-1>", lambda e: self._baixar_versao_nova())
        self.versao_nova = None

        topo = tk.Frame(self, padx=12, pady=10)
        self.topo = topo
        topo.pack(fill="x")
        self.botoes = {}
        for m, cfg in MODOS.items():
            b = tk.Radiobutton(topo, text=f"{cfg['nome']}\n{cfg['aposta']} números",
                               variable=self.modo, value=m, indicatoron=False,
                               font=("Segoe UI", 11, "bold"), padx=10, pady=6,
                               command=self._trocar_modo, cursor="hand2")
            b.pack(side="left", padx=3, expand=True, fill="x")
            self.botoes[m] = b

        self.painel = tk.Frame(self, padx=14, pady=10)
        self.painel.pack(fill="x", padx=12, pady=(0, 10))
        self.lbl_proximo = tk.Label(self.painel, font=("Segoe UI", 12, "bold"), anchor="w")
        self.lbl_proximo.pack(fill="x")
        self.lbl_premio = tk.Label(self.painel, font=("Segoe UI", 20, "bold"), anchor="w")
        self.lbl_premio.pack(fill="x")
        self.lbl_ultimo = tk.Label(self.painel, font=("Segoe UI", 10), anchor="w",
                                   justify="left", wraplength=760)
        self.lbl_ultimo.pack(fill="x")
        self.lbl_atualizado = tk.Label(self.painel, font=("Segoe UI", 8), anchor="w")
        self.lbl_atualizado.pack(fill="x", pady=(4, 0))

        linha = tk.Frame(self, padx=12)
        linha.pack(fill="x")
        tk.Label(linha, text="Jogos:", font=("Segoe UI", 10)).pack(side="left")
        ttk.Spinbox(linha, from_=1, to=50, width=4, textvariable=self.qtd).pack(side="left", padx=(4, 12))
        tk.Label(linha, text="Estilo:", font=("Segoe UI", 10)).pack(side="left")
        combo = ttk.Combobox(linha, textvariable=self.estilo, values=list(E.ESTILOS.values()),
                             state="readonly", width=40)
        combo.pack(side="left", padx=4)
        combo.bind("<<ComboboxSelected>>", lambda e: self._explicar_estilo())
        tk.Checkbutton(linha, text="Espalhar os jogos do bolão", variable=self.espalhar,
                       font=("Segoe UI", 10), command=self._explicar_estilo).pack(side="left", padx=8)

        # Números que a pessoa gosta: entram em todos os jogos
        linha_fixos = tk.Frame(self, padx=12)
        linha_fixos.pack(fill="x", pady=(6, 0))
        tk.Label(linha_fixos, text="Meus números (opcional):",
                 font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(linha_fixos, textvariable=self.fixos_txt, width=34,
                 font=("Consolas", 11)).pack(side="left", padx=6)
        tk.Button(linha_fixos, text="Escolher no volante",
                  command=self.abrir_volante).pack(side="left")
        tk.Button(linha_fixos, text="Limpar",
                  command=lambda: self.fixos_txt.set("")).pack(side="left", padx=4)
        self.fixos_txt.trace_add("write", lambda *a: self._fixos_mudou())

        # Explicação da opção escolhida, para ninguém ficar em dúvida
        self.lbl_estilo = tk.Label(self, anchor="w", justify="left", padx=14, pady=4,
                                   font=("Segoe UI", 9), bg="#f3f3f3", fg="#333",
                                   wraplength=780)
        self.lbl_estilo.pack(fill="x", padx=12, pady=(6, 0))
        self._explicar_estilo()

        linha2 = tk.Frame(self, padx=12)
        linha2.pack(fill="x", pady=(8, 0))
        self.btn_gerar = tk.Button(linha2, text="GERAR JOGOS", font=("Segoe UI", 11, "bold"),
                                   fg="white", padx=16, pady=4, command=self.gerar, cursor="hand2")
        self.btn_gerar.pack(side="left")
        self.btn_por_carrinho = tk.Button(linha2, text="Pôr marcados no carrinho",
                                          command=self.por_no_carrinho, state="disabled")
        self.btn_por_carrinho.pack(side="left", padx=6)
        tk.Button(linha2, text="Copiar", command=self.copiar).pack(side="left")
        tk.Button(linha2, text="Atualizar", command=self.atualizar).pack(side="right")
        tk.Button(linha2, text="Estatísticas",
                  command=self.mostrar_estatisticas).pack(side="right", padx=6)
        self.btn_apostas = tk.Button(linha2, text="Minhas apostas", command=self.abrir_apostas,
                                     font=("Segoe UI", 9, "bold"))
        self.btn_apostas.pack(side="right")
        self.btn_carrinho = tk.Button(linha2, text="Carrinho", command=self.abrir_carrinho,
                                      font=("Segoe UI", 9, "bold"))
        self.btn_carrinho.pack(side="right", padx=6)

        quadro = tk.Frame(self)
        quadro.pack(fill="both", expand=True, padx=12, pady=10)
        barra = tk.Scrollbar(quadro)
        barra.pack(side="right", fill="y")
        self.saida = tk.Text(quadro, font=("Consolas", 11), padx=10, pady=8,
                             state="disabled", wrap="none", yscrollcommand=barra.set)
        self.saida.pack(fill="both", expand=True)
        barra.config(command=self.saida.yview)
        self.saida.tag_configure("titulo", font=("Consolas", 11, "bold"))
        self.saida.tag_configure("bom", foreground="#1a7f37")
        self.saida.tag_configure("ultimo", background="#ffd54f", foreground="#000000")

        self.status = tk.Label(self, anchor="w", padx=12, pady=6, fg="#555",
                               font=("Segoe UI", 9))
        self.status.pack(fill="x")

    EXPLICA_ESTILO = {
        "populares": "Usa números que pouca gente aposta (foge de datas de aniversário e sequências). "
                     "A chance de ganhar é a mesma de qualquer jogo, mas se ganhar o prêmio é "
                     "dividido com menos gente, então tende a ser maior.",
        "aleatorio": "Números sorteados ao acaso, como a Surpresinha da lotérica. "
                     "Mesma chance de qualquer outro jogo.",
        "quentes": "Usa os números que mais saíram nos últimos 50 concursos. Só para quem gosta: "
                   "não aumenta a chance, porque o sorteio não tem memória.",
    }

    def _explicar_estilo(self):
        texto = "ℹ  " + self.EXPLICA_ESTILO[self._estilo_chave()]
        if self.espalhar.get():
            texto += ("\n✔  Espalhar: os jogos do bolão repetem o mínimo de números entre si, "
                      "cobrindo mais números e aumentando a chance de o grupo levar algum prêmio.")
            cor = "#333"
        else:
            texto += ("\n⚠  Espalhar desmarcado: os jogos podem repetir muitos números entre si "
                      "e o grupo tem menos chance de levar algum prêmio. Recomendado deixar marcado.")
            cor = "#a15c00"
        m = self.modo.get()
        cfg = MODOS[m]
        try:
            fixos = E.ler_fixos(self.fixos_txt.get(), cfg)
        except ValueError as e:
            texto += f"\n⚠  {e}"
            cor = "#a15c00"
        else:
            if fixos:
                lista = " ".join(f"{d:02d}" for d in fixos)
                texto += (f"\n★  Seus números ({lista}) entram em todos os jogos; o programa "
                          f"escolhe os outros {cfg['aposta'] - len(fixos)} de cada jogo.")
                modelo = self.modelos.get(m)
                if modelo is not None and modelo.pesos:
                    top = set(modelo.ranking()[:10])
                    pop = [f"{d:02d}" for d in fixos if d in top]
                    if pop:
                        texto += (f" Obs.: {', '.join(pop)} "
                                  f"{'está' if len(pop) == 1 else 'estão'} entre os mais "
                                  f"apostados pelo público (não muda a chance, só a divisão).")
        self.lbl_estilo.config(text=texto, fg=cor)

    def _fixos_mudou(self):
        """Guarda os números da pessoa para a loteria atual e atualiza a explicação."""
        self.prefs["fixos"][self.modo.get()] = self.fixos_txt.get().strip()
        salvar_prefs(self.prefs)
        self._explicar_estilo()

    def _fixos_atuais(self):
        """Lista dos números fixos da loteria atual (levanta ValueError se inválido)."""
        return E.ler_fixos(self.fixos_txt.get(), MODOS[self.modo.get()])

    def abrir_volante(self):
        """Volante na tela: clica nos números para marcar/desmarcar."""
        m = self.modo.get()
        cfg = MODOS[m]
        try:
            marcados = set(self._fixos_atuais())
        except ValueError:
            marcados = set()
        limite = cfg["aposta"] - 1
        d = tk.Toplevel(self)
        d.title(f"Meus números — {cfg['nome']}")
        d.transient(self)
        d.resizable(False, False)
        info = tk.Label(d, font=("Segoe UI", 10), padx=10, pady=8)
        info.pack()
        grade = tk.Frame(d, padx=10)
        grade.pack()
        colunas = 5 if cfg["ate"] <= 25 else 10
        botoes = {}

        def atualizar():
            for n, b in botoes.items():
                b.config(bg=cfg["cor"] if n in marcados else "#f2f2f2",
                         fg="white" if n in marcados else "black")
            info.config(text=f"Clique nos números de que você gosta "
                             f"({len(marcados)} de no máximo {limite}).")

        def clicar(n):
            if n in marcados:
                marcados.discard(n)
            elif len(marcados) < limite:
                marcados.add(n)
            else:
                d.bell()
            atualizar()

        for i, n in enumerate(range(cfg["de"], cfg["ate"] + 1)):
            b = tk.Button(grade, text=f"{n:02d}", width=4, font=("Segoe UI", 10, "bold"),
                          relief="groove", command=lambda n=n: clicar(n), cursor="hand2")
            b.grid(row=i // colunas, column=i % colunas, padx=2, pady=2)
            botoes[n] = b

        def ok():
            self.fixos_txt.set(" ".join(f"{n:02d}" for n in sorted(marcados)))
            d.destroy()

        rodape = tk.Frame(d, pady=10)
        rodape.pack()
        tk.Button(rodape, text="OK", width=10, command=ok, bg=cfg["cor"], fg="white",
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=4)
        tk.Button(rodape, text="Limpar", width=10,
                  command=lambda: (marcados.clear(), atualizar())).pack(side="left", padx=4)
        tk.Button(rodape, text="Cancelar", width=10, command=d.destroy).pack(side="left", padx=4)
        atualizar()
        d.grab_set()

    def _trocar_modo(self):
        cfg = MODOS[self.modo.get()]
        # cada loteria guarda os seus números; troca o campo sem regravar a anterior
        self.fixos_txt.set(self.prefs["fixos"].get(self.modo.get(), ""))
        for m, b in self.botoes.items():
            ativo = m == self.modo.get()
            b.config(bg=MODOS[m]["cor"] if ativo else "#e8e8e8",
                     fg="white" if ativo else "black", selectcolor=MODOS[m]["cor"])
        self.btn_gerar.config(bg=cfg["cor"], activebackground=cfg["cor"])
        self._mostrar_painel()
        self._mostrar_status()

    def _mostrar_painel(self):
        m = self.modo.get()
        cor = MODOS[m]["cor"]
        self.painel.config(bg=cor)
        for lbl in (self.lbl_proximo, self.lbl_premio, self.lbl_ultimo, self.lbl_atualizado):
            lbl.config(bg=cor, fg="white")
        info = self.proximos.get(m)
        if not info:
            self.lbl_proximo.config(text="Próximo sorteio: buscando na Caixa...")
            self.lbl_premio.config(text="")
            self.lbl_ultimo.config(text="")
        else:
            self.lbl_proximo.config(
                text=f"Próximo sorteio: {descrever_data(info.get('data'))}"
                     f"   •   concurso {info.get('proximo') or '—'}")
            self.lbl_premio.config(
                text=f"Prêmio estimado: {reais(info.get('valor'))}"
                     + ("   ACUMULOU!" if info.get("acumulou") else ""))
            dez = "  ".join(f"{d:02d}" for d in info.get("dezenas_ultimo", []))
            self.lbl_ultimo.config(
                text=f"Último resultado (concurso {info.get('ultimo')}, {info.get('data_ultimo')}): {dez}")
        if self.atualizando:
            txt = "Atualizando..."
        elif self.hora_atualizacao and self.online:
            txt = (f"Dados da Caixa às {self.hora_atualizacao}  •  "
                   f"busca sozinho a cada {ATUALIZA_MIN} minutos")
        elif self.hora_atualizacao:
            txt = (f"Sem internet às {self.hora_atualizacao} — mostrando os últimos dados salvos. "
                   f"Tenta de novo em {ATUALIZA_MIN} minutos.")
        else:
            txt = ""
        self.lbl_atualizado.config(text=txt)

    def _mostrar_status(self, extra=""):
        m = self.modo.get()
        r = self.resultados[m]
        validas = [a for a in self.apostas if a.get("modo") in MODOS]
        aguardando = sum(1 for a in validas if not a.get("resultado"))
        base = (f"{MODOS[m]['nome']}: {len(r)} sorteios conferidos"
                + (f" (último {max(r)})" if r else " — ainda sem resultados")
                + f" | {len(self.gerados[m])} jogos já gerados"
                + (f" | {aguardando} aposta(s) aguardando sorteio" if aguardando else ""))
        self.status.config(text=base + (f"  •  {extra}" if extra else ""))
        self.btn_apostas.config(text=f"Minhas apostas ({len(validas)})")
        self.btn_carrinho.config(text=f"Carrinho ({len(self.carrinho)})")

    def _escrever(self, partes):
        """partes: texto ou lista de (texto, tag); tag "widget" embute um controle."""
        if isinstance(partes, str):
            partes = [(partes, None)]
        for w in self._widgets_saida:
            w.destroy()
        self._widgets_saida = []
        self.saida.config(state="normal")
        self.saida.delete("1.0", "end")
        for texto, tag in partes:
            if tag == "widget":
                self.saida.window_create("end", window=texto)
                self._widgets_saida.append(texto)
            else:
                self.saida.insert("end", texto, tag or ())
        self.saida.config(state="disabled")

    # ---------- atualização e conferência ----------

    def atualizar(self):
        if self.atualizando:
            return
        self.atualizando = True
        self._mostrar_painel()
        self.status.config(text="Buscando resultados na Caixa...")

        def tarefa():
            novos, prem, modelos = {}, {}, {}
            proximos, algum_online = dict(self.proximos), False
            for m in MODOS:
                novos[m], prem[m], info, online, _ = atualizar_resultados(m)
                if info:
                    proximos[m] = info
                algum_online = algum_online or online
                modelos[m] = E.ModeloPopularidade(novos[m], prem[m], MODOS[m])
            if algum_online:
                salvar_proximos(proximos)
            self.after(0, lambda: self._fim_atualizacao(novos, prem, modelos, proximos,
                                                        algum_online))

        threading.Thread(target=tarefa, daemon=True).start()

    def _fim_atualizacao(self, novos, prem, modelos, proximos, online):
        self.resultados.update(novos)
        self.premios.update(prem)
        self.modelos.update(modelos)
        self.proximos = proximos
        self.online = online
        self.hora_atualizacao = datetime.now().strftime("%H:%M")
        self.atualizando = False
        self._mostrar_painel()
        self._mostrar_status("Resultados atualizados" if online else "Sem internet")
        self._explicar_estilo()  # agora com o modelo, avisa se os números fixos são populares
        self._conferir_apostas()

    def _checar_versao(self):
        """Procura versão nova no GitHub agora e a cada 6 horas."""
        def tarefa():
            nova = A.buscar_versao_nova()
            if nova:
                self.after(0, lambda: self._mostrar_versao_nova(nova))
        threading.Thread(target=tarefa, daemon=True).start()
        self.after(6 * 60 * 60 * 1000, self._checar_versao)

    def _mostrar_versao_nova(self, nova):
        self.versao_nova = nova
        self.aviso_versao.config(
            text=f"↑  Nova versão {nova['versao']} disponível (você está na {A.VERSAO}) — "
                 f"clique aqui para baixar")
        if not self.aviso_versao.winfo_ismapped():
            self.aviso_versao.pack(fill="x", before=self.topo)

    def _baixar_versao_nova(self):
        if not self.versao_nova:
            return
        webbrowser.open(self.versao_nova["download"])
        messagebox.showinfo(
            "Versão nova",
            "O download da versão nova começou no navegador.\n\n"
            "1. Feche este programa.\n"
            "2. Extraia o zip NA MESMA PASTA de antes e aceite substituir os arquivos.\n"
            "3. Abra o Gerador Bolao.exe de novo.\n\n"
            "Suas apostas, jogos gerados e números favoritos continuam guardados.")

    def _auto_atualizar(self):
        self.atualizar()
        self.after(ATUALIZA_MIN * 60 * 1000, self._auto_atualizar)

    def _conferir_apostas(self):
        self.apostas = C.carregar_apostas()  # outra janela pode ter registrado algo
        mudaram = C.conferir(self.apostas, self.resultados, self.premios)
        if not mudaram:
            return
        C.salvar_apostas(self.apostas)
        self._mostrar_status()
        self._atualizar_janela_apostas()
        self.deiconify()
        self.lift()
        messagebox.showinfo("Resultado das apostas do bolão", C.resumo_aviso(mudaram)
                            + "\n\nDetalhes em \"Minhas apostas\".")

    # ---------- geração ----------

    def _estilo_chave(self):
        return next((k for k, v in E.ESTILOS.items() if v == self.estilo.get()), "populares")

    def _sincronizar_gerados(self):
        """Junta o histórico do arquivo com o desta janela (duas janelas não se apagam)."""
        disco = carregar_gerados()
        for m in MODOS:
            lista = disco.setdefault(m, [])
            vistos = {tuple(j["dezenas"]) for j in lista}
            for j in self.gerados.get(m, []):
                if tuple(j["dezenas"]) not in vistos:
                    lista.append(j)
                    vistos.add(tuple(j["dezenas"]))
        self.gerados = disco

    def gerar(self):
        if self.gerando:
            return
        m = self.modo.get()
        if not self.resultados[m] and not messagebox.askyesno(
                "Sem resultados", "Ainda não há resultados baixados para conferir.\n"
                                  "Gerar mesmo assim (só evita repetir jogos do próprio bolão)?"):
            return
        try:
            qtd = max(1, min(50, int(self.qtd.get())))
        except (tk.TclError, ValueError):
            qtd = 10
        try:
            fixos = self._fixos_atuais()
        except ValueError as e:
            messagebox.showerror("Meus números", str(e))
            return
        estilo, espalhar = self._estilo_chave(), self.espalhar.get()
        self._sincronizar_gerados()
        self.gerando = True
        self.btn_gerar.config(state="disabled", text="GERANDO...")
        resultados, premios, gerados = self.resultados[m], self.premios[m], self.gerados

        def tarefa():
            try:
                modelo = self.modelos.get(m) or E.ModeloPopularidade(resultados, premios, MODOS[m])
                jogos = E.gerar_bolao(m, qtd, resultados, gerados, estilo, espalhar, modelo,
                                      fixos=fixos)
                if not jogos:
                    raise ValueError("Com esses números fixos não sobrou nenhum jogo novo "
                                     "(todos já foram gerados ou sorteados). "
                                     "Tire um ou mais números de \"Meus números\".")
                avaliacao = E.avaliar_bolao(jogos, MODOS[m], modelo)
                self.after(0, lambda: self._mostrar_jogos(m, jogos, estilo, modelo, avaliacao,
                                                          fixos, qtd))
            except Exception as e:
                self.after(0, lambda: self._erro_geracao(e))

        threading.Thread(target=tarefa, daemon=True).start()

    def _erro_geracao(self, erro):
        self.gerando = False
        self.btn_gerar.config(state="normal", text="GERAR JOGOS")
        messagebox.showerror("Erro ao gerar", str(erro))

    def _mostrar_jogos(self, m, jogos, estilo, modelo, av, fixos=(), pedidos=None):
        self.gerando = False
        self.btn_gerar.config(state="normal", text="GERAR JOGOS")
        self.modelos[m] = modelo
        cfg = MODOS[m]
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        for j in jogos:
            self.gerados[m].append({"dezenas": list(j), "gerado_em": agora})
        salvar_gerados(self.gerados)
        self.ultimos = [formatar(j) for j in jogos]
        self.ultimos_jogos = (m, [list(j) for j in jogos])
        self.marcados = [tk.BooleanVar(value=False) for _ in jogos]
        for v in self.marcados:
            v.trace_add("write", lambda *a: self._contar_marcados())
        self.btn_por_carrinho.config(state="disabled")

        p = []
        p.append((f"{cfg['nome']} — {agora} — {E.ESTILOS[estilo]}"
                  + (", espalhados" if self.espalhar.get() else "") + "\n", "titulo"))
        if fixos:
            p.append((f"Seus números em todos os jogos: "
                      f"{' '.join(f'{d:02d}' for d in fixos)}  (marcados com *)\n", "bom"))
        if pedidos and len(jogos) < pedidos:
            p.append((f"Só deu para gerar {len(jogos)} de {pedidos} jogos novos com esses "
                      f"números fixos (os outros já foram gerados ou sorteados).\n", None))
        r = self.resultados[m]
        ultimo = set(r[max(r)]) if r else set()
        if ultimo:
            p.append((f"Em destaque, os números do último sorteio (concurso {max(r)}):\n  ", None))
            p.append((" " + " ".join(f"{d:02d}" for d in sorted(ultimo)) + " ", "ultimo"))
            p.append(("\n", None))
        p.append(("\n", None))
        todos = tk.BooleanVar(value=False)
        p.append((self._caixinha(todos, "Marcar todos", lambda: [
            v.set(todos.get()) for v in self.marcados]), "widget"))
        p.append(("  marque os jogos de que gostou e clique em \"Pôr marcados no carrinho\"\n\n",
                  None))
        for i, j in enumerate(jogos, 1):
            p.append((self._caixinha(self.marcados[i - 1]), "widget"))
            p.append((f"Jogo {i:>2}:  ", "titulo"))
            p += self._numeros_destacados(j, set(fixos), ultimo)
            p.append(("\n", None))
            p.append((f"{RECUO}No histórico: " + E.resumo_historico(
                j, self.resultados[m], cfg, RECUO + "              ") + "\n\n", None))

        p.append(("RESUMO DO BOLÃO\n", "titulo"))
        p.append((f"  Números diferentes usados: {av['distintos']} de {av['total_numeros']}"
                  f"  (jogos ao acaso usariam ~{av['distintos_acaso']})\n", None))
        if av["jogos"] > 1:
            p.append((f"  Máximo de números repetidos entre dois jogos: "
                      f"{av['maior_repeticao']}\n", None))
        comp = (f"jogos ao acaso: {E.porcentagem(av['chance_acaso'])}"
                if av["diferenca_real"] else "igual a jogos ao acaso")
        p.append((f"  Chance de pelo menos um prêmio ({av['faixa']} ou mais): "
                  f"{E.porcentagem(av['chance'])}  ({comp})\n",
                  "bom" if av["diferenca_real"] and av["chance"] > av["chance_acaso"] else None))
        if "premio_medio" in av:
            p.append((f"  Se ganhar, prêmio em média ~{vezes(av['premio_medio'])} o normal "
                      f"(menos gente para dividir)\n",
                      "bom" if av["premio_medio"] >= 1.05 else None))
            p.append((f"  Efeito nesta loteria: {FORCA_EFEITO[m]}\n", None))
        p.append(("\n✔ Nenhum desses jogos já foi sorteado.\n"
                  "✔ Nenhum repete jogo gerado antes pelo bolão.\n\n", "bom"))
        p.append(("CHANCE REAL DE CADA JOGO NO PRÓXIMO SORTEIO\n", "titulo"))
        p.append((E.texto_chances(cfg) + "\n"
                  "  (igual para qualquer jogo: sorteio não tem memória. O que muda com\n"
                  "   a escolha dos números é com quantas pessoas o prêmio é dividido.)\n", None))
        self._escrever(p)
        self._mostrar_status(f"{len(jogos)} jogos novos — marque os que gostou e "
                             f"ponha no carrinho")

    def _caixinha(self, var, texto="", comando=None):
        """Caixinha de marcar para embutir no texto da saída."""
        return tk.Checkbutton(self.saida, variable=var, text=texto, command=comando,
                              bg=self.saida.cget("bg"), activebackground=self.saida.cget("bg"),
                              font=("Segoe UI", 9), cursor="hand2", padx=0, pady=0)

    def _contar_marcados(self):
        n = sum(v.get() for v in self.marcados)
        self.btn_por_carrinho.config(
            state="normal" if n else "disabled",
            text=f"Pôr {n} no carrinho" if n else "Pôr marcados no carrinho")

    def _jogos_marcados(self):
        if not self.ultimos_jogos:
            return None, []
        m, jogos = self.ultimos_jogos
        return m, [j for j, v in zip(jogos, self.marcados) if v.get()]

    def por_no_carrinho(self):
        m, jogos = self._jogos_marcados()
        if not jogos:
            return
        self.carrinho = K.carregar_carrinho()  # outra janela pode ter mexido
        novos = K.adicionar(self.carrinho, m, jogos)
        K.salvar_carrinho(self.carrinho)
        for v in self.marcados:
            v.set(False)
        if novos == 0:
            self._mostrar_status("Esses jogos já estavam no carrinho")
        else:
            self._mostrar_status(f"{n_jogos(novos)} no carrinho" +
                                 (" (os outros já estavam lá)" if novos < len(jogos) else "") +
                                 " — abra o Carrinho para registrar ou remover")
        self._atualizar_janela_carrinho()

    @staticmethod
    def _numeros_destacados(jogo, fixos, ultimo, por_linha=10):
        """Partes (texto, tag) de um jogo: quem saiu no último sorteio fica destacado."""
        partes = []
        for k, d in enumerate(jogo):
            if k and k % por_linha == 0:
                partes.append(("\n" + RECUO, None))
            elif k:
                partes.append((" " if fixos else "  ", None))
            tag = ("titulo", "ultimo") if d in ultimo else "titulo"
            partes.append((f"{d:02d}", tag))
            if fixos:
                partes.append(("*" if d in fixos else " ", "titulo"))
        return partes

    def _texto_whatsapp(self, m, jogos):
        """Mensagem pronta para o grupo: loteria, concurso, data, prêmio, jogos e custo."""
        cfg = MODOS[m]
        info = self.proximos.get(m) or {}
        linhas = [f"*Bolão {cfg['nome']}*"]
        if info.get("proximo"):
            linhas[0] += f" — concurso {info['proximo']} ({descrever_data(info.get('data'))})"
        if info.get("valor"):
            linhas.append(f"Prêmio estimado: {reais(info['valor'])}"
                          + (" (acumulou!)" if info.get("acumulou") else ""))
        linhas.append("")
        for i, j in enumerate(jogos, 1):
            linhas.append(f"Jogo {i:02d}: " + " ".join(f"{d:02d}" for d in j))
        linhas += ["", f"{len(jogos)} jogo{'s' if len(jogos) > 1 else ''} • "
                       f"{reais(C.custo_jogos(jogos, cfg))}"]
        return "\n".join(linhas)

    def _copiar_texto(self, texto, aviso):
        self.clipboard_clear()
        self.clipboard_append(texto)
        self._mostrar_status(aviso)

    def copiar(self):
        """Copia os jogos marcados (ou todos, se nenhum marcado) para o WhatsApp."""
        if not self.ultimos or not self.ultimos_jogos:
            self._mostrar_status("Gere os jogos primeiro; depois clique em Copiar")
            return
        m, marcados = self._jogos_marcados()
        jogos = marcados or self.ultimos_jogos[1]
        self._copiar_texto(self._texto_whatsapp(m, jogos),
                           f"Mensagem com {n_jogos(len(jogos))} copiada: é só colar no WhatsApp")

    def mostrar_estatisticas(self):
        m = self.modo.get()
        cfg = MODOS[m]
        if not self.resultados[m]:
            self._escrever("Ainda não há resultados baixados.")
            return
        modelo = self.modelos.get(m) or E.ModeloPopularidade(self.resultados[m],
                                                             self.premios[m], cfg)
        self.modelos[m] = modelo
        self.ultimos = []
        self._escrever([
            (f"{cfg['nome']} — números quentes, frios e populares\n\n", "titulo"),
            ("O QUE O PÚBLICO MAIS APOSTA (isso muda o prêmio, não a chance)\n", "titulo"),
            (E.texto_populares(modelo) + "\n\n", None),
            ("O QUE MAIS SAIU NOS ÚLTIMOS CONCURSOS (curiosidade, não previsão)\n", "titulo"),
            (E.texto_quentes_frios(self.resultados[m], cfg) + "\n\n", None),
            ("Cada sorteio é independente: um número quente não tem mais chance de sair.\n"
             "Já fugir dos números populares faz diferença no valor do prêmio.", None),
        ])

    # ---------- apostas ----------

    # ---------- carrinho ----------

    def abrir_carrinho(self):
        if self.janela_carrinho and self.janela_carrinho.winfo_exists():
            self.janela_carrinho.lift()
            return
        j = tk.Toplevel(self)
        j.title("Carrinho")
        j.geometry("720x560")
        tk.Label(j, justify="left", anchor="w", padx=12, pady=8, font=("Segoe UI", 10),
                 text="Jogos que você separou. Marque os jogos e escolha: registrar como "
                      "apostados\n(o programa confere sozinho quando sair o resultado) ou "
                      "remover do carrinho.").pack(fill="x")
        barra = tk.Frame(j, padx=10)
        barra.pack(fill="x")
        j.todos = tk.BooleanVar(value=False)
        tk.Checkbutton(barra, text="Marcar todos", variable=j.todos,
                       command=lambda: [v.set(j.todos.get()) for v in j.vars.values()]
                       ).pack(side="left")
        tk.Button(barra, text="Registrar marcados como apostados", font=("Segoe UI", 9, "bold"),
                  command=self.registrar_do_carrinho).pack(side="left", padx=6)
        tk.Button(barra, text="Remover marcados",
                  command=self.remover_do_carrinho).pack(side="left")
        tk.Button(barra, text="Copiar marcados",
                  command=self.copiar_do_carrinho).pack(side="left", padx=6)
        j.resumo = tk.Label(j, anchor="w", padx=12, pady=4, font=("Segoe UI", 9), fg="#333")
        j.resumo.pack(fill="x")
        quadro = tk.Frame(j)
        quadro.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        sb = tk.Scrollbar(quadro)
        sb.pack(side="right", fill="y")
        j.texto = tk.Text(quadro, font=("Consolas", 11), wrap="none", padx=8, pady=6,
                          yscrollcommand=sb.set, cursor="arrow")
        j.texto.pack(fill="both", expand=True)
        sb.config(command=j.texto.yview)
        j.texto.tag_configure("titulo", font=("Consolas", 11, "bold"))
        j.vars, j.widgets = {}, []
        self.janela_carrinho = j
        self._atualizar_janela_carrinho()

    def _atualizar_janela_carrinho(self):
        self.btn_carrinho.config(text=f"Carrinho ({len(self.carrinho)})")
        j = self.janela_carrinho
        if not (j and j.winfo_exists()):
            return
        for w in j.widgets:
            w.destroy()
        j.widgets, j.vars = [], {}
        j.todos.set(False)
        t = j.texto
        t.config(state="normal")
        t.delete("1.0", "end")
        if not self.carrinho:
            t.insert("end", "O carrinho está vazio.\n\nNa tela principal, gere os jogos, marque "
                            "os de que gostou\ne clique em \"Pôr marcados no carrinho\".")
        for m, itens in K.por_loteria(self.carrinho).items():
            cfg = MODOS[m]
            prox = (self.proximos.get(m) or {}).get("proximo")
            t.insert("end", f"{cfg['nome']} — {n_jogos(len(itens))}"
                            + (f" — próximo concurso {prox}" if prox else "") + "\n", "titulo")
            for it in itens:
                v = tk.BooleanVar(value=False)
                v.trace_add("write", lambda *a: self._resumo_carrinho())
                cb = tk.Checkbutton(t, variable=v, bg=t.cget("bg"),
                                    activebackground=t.cget("bg"), cursor="hand2")
                t.window_create("end", window=cb)
                j.vars[it["id"]], j.widgets = v, j.widgets + [cb]
                t.insert("end", " " + "  ".join(f"{d:02d}" for d in it["dezenas"])
                         + f"    (separado em {it['adicionado_em']})\n")
            t.insert("end", "\n")
        t.config(state="disabled")
        self._resumo_carrinho()

    def _itens_marcados_carrinho(self):
        j = self.janela_carrinho
        if not (j and j.winfo_exists()):
            return []
        ids = {i for i, v in j.vars.items() if v.get()}
        return [it for it in self.carrinho if it["id"] in ids]

    def _resumo_carrinho(self):
        j = self.janela_carrinho
        if not (j and j.winfo_exists()):
            return
        marcados = self._itens_marcados_carrinho()
        custo = sum(C.custo_jogos([it["dezenas"]], MODOS[it["modo"]]) for it in marcados)
        j.resumo.config(text=f"{n_jogos(len(self.carrinho))} no carrinho  •  marcados: "
                             f"{len(marcados)}  •  custo dos marcados: {reais(custo)}")

    def registrar_do_carrinho(self):
        marcados = self._itens_marcados_carrinho()
        pai = self.janela_carrinho
        if not marcados:
            messagebox.showinfo("Carrinho", "Marque os jogos que você apostou.", parent=pai)
            return
        registrados = []
        for m, itens in K.por_loteria(marcados).items():
            cfg = MODOS[m]
            prox = (self.proximos.get(m) or {}).get("proximo")
            conc = simpledialog.askinteger(
                "Registrar aposta",
                (f"Em qual concurso da {cfg['nome']} " + ("esse jogo foi apostado?" if len(itens) == 1 else f"esses {len(itens)} jogos foram apostados?")),
                initialvalue=prox, minvalue=1, parent=pai)
            if not conc:
                continue  # cancelou esta loteria; os jogos ficam no carrinho
            self.apostas = C.carregar_apostas()
            C.registrar(self.apostas, m, conc, [it["dezenas"] for it in itens])
            C.salvar_apostas(self.apostas)
            registrados += [it["id"] for it in itens]
        if not registrados:
            return
        self.carrinho = K.remover(K.carregar_carrinho(), registrados)
        K.salvar_carrinho(self.carrinho)
        self._atualizar_janela_carrinho()
        self._atualizar_janela_apostas()
        self._mostrar_status(f"{n_jogos(len(registrados))} em Minhas apostas; "
                             f"o programa confere sozinho quando sair o resultado")
        self._conferir_apostas()  # se o concurso já saiu, confere na hora

    def remover_do_carrinho(self):
        marcados = self._itens_marcados_carrinho()
        pai = self.janela_carrinho
        if not marcados:
            messagebox.showinfo("Carrinho", "Marque os jogos que quer remover.", parent=pai)
            return
        if not messagebox.askyesno("Carrinho", f"Remover {n_jogos(len(marcados))} do carrinho?",
                                   parent=pai):
            return
        self.carrinho = K.remover(K.carregar_carrinho(), [it["id"] for it in marcados])
        K.salvar_carrinho(self.carrinho)
        self._atualizar_janela_carrinho()

    def copiar_do_carrinho(self):
        marcados = self._itens_marcados_carrinho() or self.carrinho
        if not marcados:
            return
        textos = [self._texto_whatsapp(m, [it["dezenas"] for it in itens])
                  for m, itens in K.por_loteria(marcados).items()]
        self._copiar_texto("\n\n".join(textos),
                           f"Mensagem com {n_jogos(len(marcados))} do carrinho copiada")

    def abrir_apostas(self):
        if self.janela_apostas and self.janela_apostas.winfo_exists():
            self.janela_apostas.lift()
            return
        j = tk.Toplevel(self)
        j.title("Minhas apostas")
        j.geometry("860x600")
        barra = tk.Frame(j, padx=10, pady=8)
        barra.pack(fill="x")
        tk.Button(barra, text="Adicionar jogos feitos fora do programa",
                  command=self.adicionar_manual).pack(side="left")
        tk.Button(barra, text="Excluir uma aposta", command=self.excluir_aposta).pack(side="left", padx=6)
        tk.Button(barra, text="Conferir agora", command=self.atualizar).pack(side="right")
        quadro = tk.Frame(j)
        quadro.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        sb = tk.Scrollbar(quadro)
        sb.pack(side="right", fill="y")
        texto = tk.Text(quadro, font=("Consolas", 10), state="disabled", wrap="none",
                        yscrollcommand=sb.set, padx=8, pady=6)
        texto.pack(fill="both", expand=True)
        sb.config(command=texto.yview)
        j.texto = texto
        self.janela_apostas = j
        self._atualizar_janela_apostas()

    def _atualizar_janela_apostas(self):
        j = self.janela_apostas
        if not (j and j.winfo_exists()):
            return
        validas = [a for a in self.apostas if a.get("modo") in MODOS]
        if validas:
            corpo = "\n\n".join(C.texto_aposta(a) for a in reversed(validas))
            gasto, ganho = C.balanco(self.apostas)
            saldo = ganho - gasto
            corpo = (f"Gasto pelo bolão: {reais(gasto)}   •   Ganho: {reais(ganho)}   •   "
                     f"Saldo: {'-' if saldo < 0 else ''}{reais(abs(saldo))}\n"
                     f"Números entre [ ] são os que saíram.\n\n" + corpo)
        else:
            corpo = ("Nenhuma aposta registrada ainda.\n\n"
                     "Gere os jogos, ponha os que gostou no Carrinho e, lá, clique em\n"
                     "\"Registrar marcados como apostados\".\n"
                     "Jogos feitos na lotérica ou no app da Caixa entram pelo botão acima.")
        j.texto.config(state="normal")
        j.texto.delete("1.0", "end")
        j.texto.insert("1.0", corpo)
        j.texto.config(state="disabled")

    def adicionar_manual(self):
        m = self.modo.get()
        cfg = MODOS[m]
        pai = self.janela_apostas or self
        d = tk.Toplevel(pai)
        d.title(f"Adicionar jogos — {cfg['nome']}")
        d.transient(pai)
        tk.Label(d, justify="left", padx=10, pady=8, font=("Segoe UI", 10),
                 text=(f"Loteria: {cfg['nome']} (para outra, troque o botão na tela principal)\n"
                       f"Um jogo por linha, números separados por espaço. "
                       f"Pode ter de {cfg['aposta']} a {cfg['max_aposta']} números.")).pack(anchor="w")
        linha = tk.Frame(d, padx=10)
        linha.pack(fill="x")
        tk.Label(linha, text="Concurso:").pack(side="left")
        conc_var = tk.StringVar(value=str((self.proximos.get(m) or {}).get("proximo") or ""))
        tk.Entry(linha, textvariable=conc_var, width=8).pack(side="left", padx=6)
        caixa = tk.Text(d, width=70, height=12, font=("Consolas", 11))
        caixa.pack(padx=10, pady=8)

        def salvar():
            try:
                if not conc_var.get().strip().isdigit():
                    raise ValueError("Digite o número do concurso (só números, ex.: 3074).")
                conc = int(conc_var.get())
                linhas =[l for l in caixa.get("1.0", "end").splitlines() if l.strip()]
                if not linhas:
                    raise ValueError("Digite pelo menos um jogo.")
                jogos = [C.validar_jogo(l, cfg) for l in linhas]
            except ValueError as e:
                messagebox.showerror("Confira os jogos", str(e) or "Concurso inválido.", parent=d)
                return
            self.apostas = C.carregar_apostas()
            C.registrar(self.apostas, m, conc, jogos, origem="manual")
            C.salvar_apostas(self.apostas)
            d.destroy()
            self._conferir_apostas()
            self._atualizar_janela_apostas()
            self._mostrar_status(f"{len(jogos)} jogos adicionados ao concurso {conc}")

        tk.Button(d, text="Salvar", command=salvar, padx=20).pack(pady=(0, 10))

    def excluir_aposta(self):
        if not self.apostas:
            return
        pai = self.janela_apostas or self
        num = simpledialog.askinteger("Excluir aposta", "Número da aposta (o # na lista):",
                                      parent=pai, minvalue=1)
        if not num:
            return
        self.apostas = C.carregar_apostas()
        ap = next((a for a in self.apostas if a["id"] == num), None)
        if not ap:
            messagebox.showinfo("Excluir aposta", f"Não existe aposta #{num}.", parent=pai)
            return
        if messagebox.askyesno("Excluir aposta", f"Excluir a aposta #{num} "
                               f"({MODOS.get(ap['modo'], {}).get('nome', ap['modo'])}, "
                               f"concurso {ap['concurso']})?",
                               parent=pai):
            self.apostas.remove(ap)
            C.salvar_apostas(self.apostas)
            self._atualizar_janela_apostas()
            self._mostrar_status()


if __name__ == "__main__":
    App().mainloop()
