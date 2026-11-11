# Experimento de desempenho: compara as configurações
#   A = cliente ST + servidor ST
#   B = cliente ST + servidor MT
#   C = cliente MT + servidor MT
#   C2 (extra) = cliente MT + DOIS servidores MT (round-robin)
#
# Para cada combinação (delay, N, repetição, configuração): sobe o(s)
# servidor(es) como subprocesso, espera ficarem prontos, roda o cliente como
# subprocesso (ele mede com time.perf_counter e devolve as métricas em JSON),
# e encerra o(s) servidor(es). As configurações são intercaladas dentro de cada
# repetição para que variações da máquina ao longo do tempo afetem todas igualmente.
#
# Uso: python3 benchmark.py [--reps 5] [--ns 100,1000,5000] [--delays 0,10]
# Saídas: results/resultados.csv (cada execução) e results/resumo.csv (média e desvio)

import argparse
import csv
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import time

PY = sys.executable
AQUI = os.path.dirname(os.path.abspath(__file__))
PORTA_BASE = 7000

CONFIGS = {
    #       cliente           servidor        nº de servidores
    "A":  ("client_st.py", "server_st.py", 1),
    "B":  ("client_st.py", "server_mt.py", 1),
    "C":  ("client_mt.py", "server_mt.py", 1),
    "C2": ("client_mt.py", "server_mt.py", 2),
}


def info_maquina():
    cpu = platform.processor() or "?"
    try:
        with open("/proc/cpuinfo") as f:
            for linha in f:
                if linha.startswith("model name"):
                    cpu = linha.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    return {
        "python": platform.python_version(),
        "so": platform.platform(),
        "cpu": cpu,
        "nucleos": os.cpu_count(),
    }


def esperar_porta(porta, timeout=10.0):
    """Tenta conectar até o servidor aceitar (ele já fez bind+listen)."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            with socket.create_connection(("localhost", porta), timeout=0.5):
                return  # conectou e fechou sem enviar nada: os dois servidores ignoram
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"servidor na porta {porta} não ficou pronto")


def subir_servidores(script, portas, delay_ms):
    procs = []
    for porta in portas:
        procs.append(subprocess.Popen(
            [PY, os.path.join(AQUI, script), "--port", str(porta),
             "--delay-ms", str(delay_ms), "--quiet"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for porta in portas:
        esperar_porta(porta)
    return procs


def encerrar_servidores(procs):
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


def rodar_cliente(script, portas, n, seed, extra=()):
    servers = ",".join(f"localhost:{p}" for p in portas)
    cmd = [PY, os.path.join(AQUI, script), "--n", str(n), "--seed", str(seed),
           "--servers", servers, "--json", *extra]
    saida = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    linhas = [l for l in saida.stdout.splitlines() if l.startswith("{")]
    if not linhas:
        raise RuntimeError(f"cliente não devolveu métricas:\n{saida.stdout}\n{saida.stderr}")
    return json.loads(linhas[-1])


def executar(config, n, delay_ms, seed, porta_base, max_concurrent):
    cliente, servidor, k = CONFIGS[config]
    portas = [porta_base + j for j in range(k)]
    procs = subir_servidores(servidor, portas, delay_ms)
    try:
        extra = ["--max-concurrent", str(max_concurrent)] if cliente == "client_mt.py" else []
        return rodar_cliente(cliente, portas, n, seed, extra)
    finally:
        encerrar_servidores(procs)


def main():
    p = argparse.ArgumentParser(description="Benchmark das configurações A, B, C (e C2)")
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--ns", default="100,1000,5000")
    p.add_argument("--delays", default="0,10", help="atrasos simulados no servidor, em ms")
    p.add_argument("--configs", default="A,B,C,C2")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-concurrent", type=int, default=64)
    p.add_argument("--n-max-sequencial", type=int, default=0,
                   help="se > 0, limita N de A e B quando delay > 0 (documentar no relato)")
    p.add_argument("--saida", default=os.path.join(AQUI, "results"))
    a = p.parse_args()

    ns = [int(x) for x in a.ns.split(",")]
    delays = [float(x) for x in a.delays.split(",")]
    configs = a.configs.split(",")
    maquina = info_maquina()
    os.makedirs(a.saida, exist_ok=True)
    print("Máquina:", maquina, flush=True)

    campos = ["config", "cliente", "servidor", "n_servidores", "n", "delay_ms", "rep",
              "max_concurrent", "tempo_total_s", "vazao_req_s", "lat_media_ms",
              "lat_p50_ms", "lat_p95_ms", "sucessos", "falhas",
              "python", "so", "cpu", "nucleos"]
    linhas = []
    porta = PORTA_BASE
    for delay in delays:
        for n in ns:
            for rep in range(1, a.reps + 1):
                for cfg in configs:
                    cliente, servidor, k = CONFIGS[cfg]
                    n_efetivo = n
                    if (a.n_max_sequencial and delay > 0 and cliente == "client_st.py"
                            and n > a.n_max_sequencial):
                        continue  # combinação pulada (documentada no relato)
                    porta += 2  # porta nova a cada execução: evita esperar a anterior liberar
                    if porta > 7900:
                        porta = PORTA_BASE
                    m = executar(cfg, n_efetivo, delay, a.seed, porta, a.max_concurrent)
                    linha = {
                        "config": cfg, "cliente": cliente, "servidor": servidor,
                        "n_servidores": k, "n": n_efetivo, "delay_ms": delay, "rep": rep,
                        "max_concurrent": m.get("max_concurrent", ""),
                        **{c: m[c] for c in ("tempo_total_s", "vazao_req_s", "lat_media_ms",
                                             "lat_p50_ms", "lat_p95_ms", "sucessos", "falhas")},
                        **maquina,
                    }
                    linhas.append(linha)
                    print(f"delay={delay:>4} N={n_efetivo:>5} rep={rep} {cfg:<2}: "
                          f"{m['tempo_total_s']:8.3f} s  {m['vazao_req_s']:8.1f} req/s  "
                          f"p50={m['lat_p50_ms']:7.2f} ms  falhas={m['falhas']}", flush=True)
                    # grava a cada execução: se algo interromper, o que já rodou fica salvo
                    with open(os.path.join(a.saida, "resultados.csv"), "w", newline="") as f:
                        w = csv.DictWriter(f, fieldnames=campos)
                        w.writeheader()
                        w.writerows(linhas)

    # ---- resumo: média e desvio padrão por (delay, N, config) ----
    grupos = {}
    for l in linhas:
        grupos.setdefault((l["delay_ms"], l["n"], l["config"]), []).append(l)
    metricas = ["tempo_total_s", "vazao_req_s", "lat_media_ms", "lat_p50_ms", "lat_p95_ms"]
    resumo = []
    for (delay, n, cfg), ls in grupos.items():
        r = {"delay_ms": delay, "n": n, "config": cfg, "reps": len(ls),
             "falhas_total": sum(l["falhas"] for l in ls)}
        for mtr in metricas:
            vals = [l[mtr] for l in ls]
            r[mtr + "_media"] = statistics.fmean(vals)
            r[mtr + "_desvio"] = statistics.stdev(vals) if len(vals) > 1 else 0.0
        resumo.append(r)
    with open(os.path.join(a.saida, "resumo.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(resumo[0].keys()))
        w.writeheader()
        w.writerows(resumo)

    print("\nResumo (média ± desvio):")
    for r in resumo:
        print(f"delay={r['delay_ms']:>4} N={r['n']:>5} {r['config']:<2}  "
              f"tempo {r['tempo_total_s_media']:8.3f} ± {r['tempo_total_s_desvio']:.3f} s   "
              f"vazão {r['vazao_req_s_media']:8.1f} req/s   "
              f"lat média {r['lat_media_ms_media']:7.2f} ms   falhas {r['falhas_total']}")


if __name__ == "__main__":
    main()
