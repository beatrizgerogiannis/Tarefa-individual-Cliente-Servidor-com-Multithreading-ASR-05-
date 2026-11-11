# Verificação funcional antes do experimento:
#   1. mesmas requisições (mesma seed) no servidor ST e no MT -> respostas
#      idênticas, comparadas pelo id da requisição;
#   2. cliente MT contra DOIS servidores MT em portas diferentes;
#   3. casos de erro (div por zero, operação desconhecida, JSON inválido,
#      mensagem grande demais...) respondidos igual pelos dois servidores;
#   4. nenhuma requisição perdida (sucessos + falhas = N, falhas = 0).
#
# Uso: python3 verificar.py [--n 2000] [--seed 7]

import argparse
import json
import os
import socket
import sys
import tempfile

from benchmark import subir_servidores, encerrar_servidores, rodar_cliente
from protocolo import LeitorDeLinhas, TAM_MAX_MENSAGEM

P_ST, P_MT1, P_MT2 = 7951, 7952, 7953

# Linhas enviadas "cruas" (cada uma em sua própria conexão) aos dois servidores.
CASOS_DE_ERRO = [
    ("divisão por zero",          '{"ops": [{"op": "div", "args": [5, 0]}]}'),
    ("operação desconhecida",     '{"ops": [{"op": "pow", "args": [2, 8]}]}'),
    ("nº de argumentos errado",   '{"ops": [{"op": "add", "args": [1]}]}'),
    ("tipo errado (num)",         '{"ops": [{"op": "mul", "args": ["3", 4]}]}'),
    ("tipo errado (texto)",       '{"ops": [{"op": "upper", "args": [123]}]}'),
    ("bool não é número",         '{"ops": [{"op": "add", "args": [true, 1]}]}'),
    ("args não é lista",          '{"ops": [{"op": "add", "args": 3}]}'),
    ("item não é objeto",         '{"ops": [42]}'),
    ("erro misturado com ok",     '{"ops": [{"op": "div", "args": [1, 0]}, {"op": "add", "args": [100, 200]}]}'),
    ("JSON inválido",             '{"ops": [{"op": "add", "args": [1, 2]'),
    ("sem a chave ops",           '{"op": "add", "args": [1, 2]}'),
    ("lote vazio",                '{"ops": []}'),
    ("mensagem grande (~50 KB)",  json.dumps({"ops": [{"op": "count_words", "args": ["palavra " * 6000]}]})),
    ("mensagem > 1 MiB",          '{"ops": [{"op": "upper", "args": ["' + "x" * (TAM_MAX_MENSAGEM + 10) + '"]}]}'),
]


def enviar_cru(porta, linha):
    with socket.create_connection(("localhost", porta), timeout=10) as s:
        s.sendall(linha.encode("utf-8") + b"\n")
        return LeitorDeLinhas(s).ler_linha()


def carregar(arq):
    with open(arq, encoding="utf-8") as f:
        return json.load(f)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=2000)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    ok = True
    tmp = tempfile.mkdtemp(prefix="verif_")

    procs = subir_servidores("server_st.py", [P_ST], 0) + \
            subir_servidores("server_mt.py", [P_MT1, P_MT2], 0)
    try:
        # --- 1 e 2: mesmas requisições em várias combinações ------------------
        execucoes = {
            "ST cliente -> ST servidor (referência)": ("client_st.py", [P_ST], []),
            "ST cliente -> MT servidor":               ("client_st.py", [P_MT1], []),
            "MT cliente -> MT servidor":               ("client_mt.py", [P_MT1], []),
            "MT cliente -> 2 MT servidores":           ("client_mt.py", [P_MT1, P_MT2], []),
            "MT cliente -> ST servidor":               ("client_mt.py", [P_ST], []),
        }
        respostas = {}
        for nome, (cliente, portas, extra) in execucoes.items():
            arq = os.path.join(tmp, f"{len(respostas)}.json")
            m = rodar_cliente(cliente, portas, a.n, a.seed, [*extra, "--salvar-respostas", arq])
            respostas[nome] = carregar(arq)
            perdeu = m["sucessos"] + m["falhas"] != a.n or m["falhas"] > 0
            ok &= not perdeu
            print(f"[{'OK' if not perdeu else 'FALHOU'}] {nome}: "
                  f"{m['sucessos']} sucessos, {m['falhas']} falhas de {a.n}")

        ref_nome = next(iter(respostas))
        ref = respostas[ref_nome]
        for nome, resp in respostas.items():
            if nome == ref_nome:
                continue
            diferentes = [i for i in ref if ref[i] != resp.get(i)]
            ok &= not diferentes and len(resp) == len(ref)
            print(f"[{'OK' if not diferentes else 'FALHOU'}] respostas de '{nome}' == referência "
                  f"(comparadas por id; {len(diferentes)} diferentes)")

        # quantas operações com erro as requisições aleatórias geraram (ex.: div por 0)
        erros_ops = sum(not r["ok"] for resp in ref.values() for r in resp["results"])
        print(f"      (as {a.n} requisições aleatórias incluíram {erros_ops} operação(ões) com erro)")

        # --- 3: casos de erro ---------------------------------------------------
        print("\nCasos de erro (servidor ST x servidor MT):")
        for nome, linha in CASOS_DE_ERRO:
            r_st, r_mt = enviar_cru(P_ST, linha), enviar_cru(P_MT1, linha)
            igual = r_st == r_mt and r_st is not None
            ok &= igual
            mostra = r_st if len(r_st or "") < 110 else r_st[:107] + "..."
            print(f"  [{'OK' if igual else 'FALHOU'}] {nome:<26} {mostra}")
    finally:
        encerrar_servidores(procs)

    print("\nRESULTADO:", "tudo OK" if ok else "HÁ DIFERENÇAS/FALHAS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
