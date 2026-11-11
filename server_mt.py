# Servidor MULTITHREAD: uma nova thread para cada requisição recebida.
#
# Arquitetura (como mostrado em aula):
#
#   thread principal                         threads trabalhadoras
#   ----------------                         ---------------------
#   accept()  ──► conexão nova
#   lê a requisição (uma linha JSON)
#   cria Thread(atender) e start() ────────► processa as operações (+ atraso)
#   volta IMEDIATAMENTE para o accept()      envia a resposta
#                                            fecha a conexão
#
# Padrão de conexão: UMA requisição por conexão (o que o modo automático dos
# clientes faz). A lógica das operações é a mesma do servidor ST (operacoes.py),
# então as respostas são idênticas.
#
# Uso: python3 server_mt.py [--port 5678] [--delay-ms 0] [--quiet]

from socket  import *
from constCS import * #-
import argparse
import json
import threading
from protocolo import enviar_mensagem, LeitorDeLinhas
from operacoes import processar_requisicao, resumir

parser = argparse.ArgumentParser(description="Servidor multithread da calculadora remota")
parser.add_argument("--host", default=HOST)
parser.add_argument("--port", type=int, default=PORT)
parser.add_argument("--delay-ms", type=float, default=0.0,
                    help="atraso simulado (I/O) por requisição, em ms (padrão 0)")
parser.add_argument("--quiet", action="store_true",
                    help="não imprime cada requisição (usado no benchmark)")
args = parser.parse_args()
atraso_s = args.delay_ms / 1000.0

# print() de várias threads ao mesmo tempo pode embaralhar as linhas na tela;
# o lock garante que cada mensagem de log saia inteira.
lock_log = threading.Lock()

def log(msg):
    if not args.quiet:
        with lock_log:
            print(msg, flush=True)


def atender(conn, addr, linha):
    """Corpo de cada thread trabalhadora: processa UMA requisição, responde e fecha.

    Cada thread recebe a sua própria conexão (conn) e a sua própria linha, e
    processar_requisicao não usa estado compartilhado; logo, as threads não
    disputam nenhum dado e não precisam de lock (exceto para o log).
    """
    try:
        resposta = processar_requisicao(linha, atraso_s)
        log(f"  [{threading.current_thread().name}] {addr} -> {resumir(json.dumps(resposta, ensure_ascii=False))}")
        enviar_mensagem(conn, resposta)
    except OSError as e:  # cliente caiu antes de receber a resposta
        log(f"Erro ao responder {addr}: {e}")
    finally:
        conn.close()      # a própria thread fecha a conexão que atendeu


s = socket(AF_INET, SOCK_STREAM)
s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
s.bind((args.host, args.port))
s.listen(128)  # backlog maior: muitos clientes conectando ao mesmo tempo
print(f"Servidor MT ouvindo em {args.host}:{args.port} (delay={args.delay_ms} ms; Ctrl+C para encerrar)", flush=True)

try:
    while True:
        conn, addr = s.accept()
        # A thread principal recebe a requisição dentro da conexão aceita...
        try:
            linha = LeitorDeLinhas(conn).ler_linha()
        except ValueError as e:      # mensagem grande demais: mesmo erro do servidor ST
            try:
                enviar_mensagem(conn, {"ok": False, "error": str(e)})
            except OSError:
                pass
            conn.close()
            continue
        except OSError as e:         # cliente caiu durante o envio
            log(f"Erro ao receber de {addr}: {e}")
            conn.close()
            continue
        if linha is None:            # cliente conectou e fechou sem mandar nada
            conn.close()
            continue
        log(f"  <- {addr} {resumir(linha)}")

        # ...e dispara uma NOVA thread para processar e responder essa requisição.
        # daemon=True: se o servidor for encerrado (Ctrl+C / benchmark), as
        # threads ainda ativas não impedem o processo de terminar.
        t = threading.Thread(target=atender, args=(conn, addr, linha), daemon=True)
        t.start()
        # Não fazemos join() aqui: a thread principal volta imediatamente para o
        # accept(), enquanto a trabalhadora segue em paralelo.
except KeyboardInterrupt:
    print("\nServidor encerrado.")
finally:
    s.close()
