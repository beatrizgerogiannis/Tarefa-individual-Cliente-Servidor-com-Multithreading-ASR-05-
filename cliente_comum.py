# Código compartilhado pelo modo automático dos dois clientes (client_st.py e
# client_mt.py): argumentos, envio de UMA requisição em UMA conexão TCP,
# estatísticas e relatório. Assim a única diferença entre os clientes é o uso
# de threads.

import argparse
import json
import socket
import statistics
import sys
import time

from constCS import HOST, PORT
from protocolo import enviar_mensagem, LeitorDeLinhas

TIMEOUT_S = 60.0  # uma requisição que demora mais que isso conta como falha


def argumentos_automaticos(parser):
    """Acrescenta ao parser os parâmetros do modo automático."""
    parser.add_argument("--n", type=int, help="número de requisições aleatórias (ativa o modo automático)")
    parser.add_argument("--seed", type=int, default=42, help="semente do gerador (padrão 42)")
    parser.add_argument("--servers", default=f"{HOST}:{PORT}",
                        help="lista host:porta,host:porta; requisições distribuídas em round-robin")
    parser.add_argument("--json", action="store_true",
                        help="imprime as métricas como uma linha JSON (usado pelo benchmark)")
    parser.add_argument("--salvar-respostas", metavar="ARQ",
                        help="salva {id: resposta} em ARQ (usado na verificação funcional)")


def ler_servidores(texto):
    """'localhost:5678,localhost:5679' -> [('localhost', 5678), ('localhost', 5679)]"""
    servidores = []
    for item in texto.split(","):
        host, porta = item.strip().rsplit(":", 1)
        servidores.append((host, int(porta)))
    return servidores


def enviar_requisicao(endereco, requisicao):
    """Abre uma conexão, envia UMA requisição, espera a resposta e fecha.

    Devolve (resposta, latência em segundos). Lança exceção em caso de falha
    de rede, para quem chamou contar como falha.
    """
    inicio = time.perf_counter()
    with socket.create_connection(endereco, timeout=TIMEOUT_S) as s:
        enviar_mensagem(s, requisicao)
        linha = LeitorDeLinhas(s).ler_linha()
    latencia = time.perf_counter() - inicio
    if linha is None:
        raise ConnectionError("servidor fechou a conexão sem responder")
    return json.loads(linha), latencia


def percentil(valores_ordenados, p):
    """Percentil pelo método do vizinho mais próximo (p entre 0 e 100)."""
    if not valores_ordenados:
        return float("nan")
    k = max(0, min(len(valores_ordenados) - 1,
                   round(p / 100 * len(valores_ordenados) + 0.5) - 1))
    return valores_ordenados[k]


def relatar(args, modo, tempo_total, respostas, latencias, falhas, extra=None):
    """Imprime o resumo (humano ou JSON) e salva as respostas se pedido.

    respostas: lista indexada pelo id da requisição (None = falhou)
    latencias: lista de latências (s) só das requisições bem-sucedidas
    falhas:    lista de (id, mensagem de erro)
    """
    lat = sorted(latencias)
    n = len(respostas)
    sucessos = sum(r is not None for r in respostas)
    metricas = {
        "modo": modo,
        "n": n,
        "sucessos": sucessos,
        "falhas": len(falhas),
        "tempo_total_s": tempo_total,
        "vazao_req_s": n / tempo_total if tempo_total > 0 else float("nan"),
        "lat_media_ms": statistics.fmean(lat) * 1000 if lat else float("nan"),
        "lat_p50_ms": percentil(lat, 50) * 1000,
        "lat_p95_ms": percentil(lat, 95) * 1000,
        "servidores": args.servers,
        "seed": args.seed,
    }
    if extra:
        metricas.update(extra)

    if args.salvar_respostas:
        with open(args.salvar_respostas, "w", encoding="utf-8") as f:
            json.dump({str(i): r for i, r in enumerate(respostas)}, f,
                      ensure_ascii=False, indent=0, sort_keys=True)

    if args.json:
        print(json.dumps(metricas))
    else:
        print(f"Cliente {modo}: {n} requisições para {args.servers} (seed={args.seed})")
        print(f"  sucessos: {sucessos}   falhas: {len(falhas)}")
        print(f"  tempo total: {tempo_total:.3f} s   vazão: {metricas['vazao_req_s']:.1f} req/s")
        print(f"  latência (ms): média {metricas['lat_media_ms']:.2f}   "
              f"p50 {metricas['lat_p50_ms']:.2f}   p95 {metricas['lat_p95_ms']:.2f}")
    for i, erro in falhas[:10]:  # mostra algumas falhas, se houver
        print(f"  falha na requisição {i}: {erro}", file=sys.stderr)
    # Nenhuma requisição pode se perder: toda requisição é sucesso OU falha.
    assert sucessos + len(falhas) == n, "requisição perdida na contagem!"
    return metricas
