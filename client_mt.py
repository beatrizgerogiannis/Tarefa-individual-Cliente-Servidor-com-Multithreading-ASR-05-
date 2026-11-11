# Cliente MULTITHREAD: cada requisição é enviada por uma NOVA thread.
#
# Arquitetura (como mostrado em aula):
#
#   thread principal                          uma thread por requisição
#   ----------------                          -------------------------
#   gera as N requisições (gerador.py)
#   para cada requisição i:
#     semaforo.acquire()  (espera vaga)
#     cria Thread(enviar i) e start() ──────► abre a conexão (servidor i % k)
#   join() em todas as threads                envia a requisição
#   relatório                                 espera a resposta
#                                             guarda resposta e latência
#                                             semaforo.release()
#
# Uso:
#   python3 client_mt.py --n 1000 --seed 42 [--servers h:p,h:p] [--max-concurrent 64]

import argparse
import sys
import threading
import time

import cliente_comum
from gerador import gerar_requisicoes


def main():
    parser = argparse.ArgumentParser(description="Cliente multithread da calculadora remota")
    cliente_comum.argumentos_automaticos(parser)
    parser.add_argument("--max-concurrent", type=int, default=64,
                        help="máximo de threads de requisição ativas ao mesmo tempo (padrão 64)")
    args = parser.parse_args()
    if args.n is None:
        parser.error("o cliente MT só tem modo automático: informe --n")

    servidores = cliente_comum.ler_servidores(args.servers)
    requisicoes = gerar_requisicoes(args.n, args.seed)  # gerado ANTES de medir

    # --- Estruturas compartilhadas entre as threads -------------------------
    # respostas[i] é escrita SOMENTE pela thread da requisição i (cada thread
    # tem sua própria posição, pré-alocada), então não há disputa nessa lista.
    respostas = [None] * args.n
    # latencias e falhas recebem dados de TODAS as threads; o lock torna cada
    # atualização atômica (não dependemos de detalhes do GIL para isso).
    latencias, falhas = [], []
    lock_resultados = threading.Lock()

    # O semáforo limita quantas threads de requisição ficam ATIVAS ao mesmo
    # tempo. Continua sendo uma thread nova por requisição; o limite só evita
    # abrir milhares de conexões simultâneas (esgotar portas locais e estourar
    # o backlog do listen() do servidor).
    semaforo = threading.Semaphore(args.max_concurrent)

    def enviar(i, req):
        """Corpo de cada thread: uma requisição, uma conexão."""
        endereco = servidores[i % len(servidores)]  # round-robin entre servidores
        try:
            resposta, lat = cliente_comum.enviar_requisicao(endereco, req)
            respostas[i] = resposta
            with lock_resultados:
                latencias.append(lat)
        except Exception as e:
            with lock_resultados:
                falhas.append((i, f"{type(e).__name__}: {e}"))
        finally:
            semaforo.release()  # libera a vaga mesmo se a requisição falhou

    threads = []
    inicio = time.perf_counter()
    for i, req in requisicoes:
        semaforo.acquire()  # bloqueia a thread principal se já houver max_concurrent ativas
        # Criação de uma NOVA thread para esta requisição:
        t = threading.Thread(target=enviar, args=(i, req), name=f"req-{i}")
        t.start()
        threads.append(t)
    # join(): a thread principal espera TODAS as requisições terminarem antes
    # de parar o cronômetro; sem isso mediríamos só o tempo de disparo.
    for t in threads:
        t.join()
    tempo_total = time.perf_counter() - inicio

    cliente_comum.relatar(args, "MT", tempo_total, respostas, latencias, falhas,
                          extra={"max_concurrent": args.max_concurrent})
    return 0 if not falhas else 1


if __name__ == "__main__":
    sys.exit(main())
