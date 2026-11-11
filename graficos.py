# Gera os gráficos do experimento a partir de results/resumo.csv.
#
#   results/tempo_total_delay_<d>ms.png  tempo total por configuração e N (um por delay)
#   results/vazao.png                    vazão (req/s) por configuração, N e delay
#
# Uso: python3 graficos.py   (requer matplotlib: pip install matplotlib)

import csv
import os

import matplotlib
matplotlib.use("Agg")  # gera arquivos sem abrir janela
import matplotlib.pyplot as plt

AQUI = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(AQUI, "results")

# Cor fixa por configuração (a cor segue a configuração em todos os gráficos).
CORES = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a", "C2": "#eda100"}
NOMES = {
    "A": "A: cliente ST + servidor ST",
    "B": "B: cliente ST + servidor MT",
    "C": "C: cliente MT + servidor MT",
    "C2": "C2: cliente MT + 2 servidores MT",
}
TINTA, TINTA_2, GRADE = "#0b0b0b", "#52514e", "#e4e3df"


def carregar():
    with open(os.path.join(RES, "resumo.csv")) as f:
        linhas = list(csv.DictReader(f))
    for l in linhas:
        l["n"] = int(l["n"])
        l["delay_ms"] = float(l["delay_ms"])
        for k in list(l):
            if k.endswith("_media") or k.endswith("_desvio"):
                l[k] = float(l[k])
    return linhas


def estilo(ax):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRADE)
    ax.tick_params(colors=TINTA_2, labelsize=9)
    ax.yaxis.grid(True, color=GRADE, linewidth=0.8)
    ax.set_axisbelow(True)


def barras(ax, linhas, metrica, fmt):
    configs = [c for c in CORES if any(l["config"] == c for l in linhas)]
    ns = sorted({l["n"] for l in linhas})
    largura = 0.8 / len(configs)
    for j, cfg in enumerate(configs):
        xs, ys, es = [], [], []
        for i, n in enumerate(ns):
            l = next((l for l in linhas if l["config"] == cfg and l["n"] == n), None)
            if l is None:
                continue
            xs.append(i + (j - (len(configs) - 1) / 2) * largura)
            ys.append(l[metrica + "_media"])
            es.append(l[metrica + "_desvio"])
        ax.bar(xs, ys, width=largura * 0.92, color=CORES[cfg], label=NOMES[cfg],
               yerr=es, error_kw={"elinewidth": 1, "capsize": 2, "ecolor": TINTA_2})
        for x, y, e in zip(xs, ys, es):  # rótulo com o valor, acima da barra de erro
            ax.annotate(fmt(y), (x, y + e), xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=7, color=TINTA_2)
    ax.set_xticks(range(len(ns)))
    ax.set_xticklabels([f"N = {n}" for n in ns], color=TINTA)
    estilo(ax)


def main():
    linhas = carregar()
    delays = sorted({l["delay_ms"] for l in linhas})

    for d in delays:
        sub = [l for l in linhas if l["delay_ms"] == d]
        fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150)
        barras(ax, sub, "tempo_total_s", lambda y: f"{y:.2f}" if y < 10 else f"{y:.1f}")
        ax.set_yscale("log")
        ax.set_ylabel("tempo total (s, escala log)", color=TINTA_2)
        reps = int(sub[0]["reps"])
        ax.set_title(f"Tempo total para N requisições — delay no servidor = {d:g} ms\n"
                     f"(média de {reps} repetições; barras de erro = desvio padrão)",
                     fontsize=10, color=TINTA, loc="left")
        ax.legend(frameon=False, fontsize=8, loc="upper left")
        fig.tight_layout()
        arq = os.path.join(RES, f"tempo_total_delay_{d:g}ms.png")
        fig.savefig(arq)
        plt.close(fig)
        print("gerado:", arq)

    fig, axs = plt.subplots(1, len(delays), figsize=(5 * len(delays), 4.4), dpi=150, sharey=True)
    if len(delays) == 1:
        axs = [axs]
    for ax, d in zip(axs, delays):
        barras(ax, [l for l in linhas if l["delay_ms"] == d], "vazao_req_s", lambda y: f"{y:.0f}")
        ax.set_title(f"delay = {d:g} ms", fontsize=10, color=TINTA, loc="left")
    axs[0].set_ylabel("vazão (req/s)", color=TINTA_2)
    handles, labels = axs[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, ncol=len(labels),
               loc="lower center", bbox_to_anchor=(0.5, 0))
    reps = int(linhas[0]["reps"])
    fig.suptitle(f"Vazão por configuração (média de {reps} repetições)", fontsize=11,
                 color=TINTA, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    arq = os.path.join(RES, "vazao.png")
    fig.savefig(arq)
    plt.close(fig)
    print("gerado:", arq)


if __name__ == "__main__":
    main()
