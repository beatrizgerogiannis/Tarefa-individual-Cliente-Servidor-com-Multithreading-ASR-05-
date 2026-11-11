# Servidor SINGLE-THREADED (versão da ASR 04).
#
# Atende um cliente por vez: accept() -> lê requisições até o cliente fechar ->
# volta para o accept(). Enquanto atende uma conexão, as outras esperam na fila
# do listen(). Aceita os dois padrões de uso:
#   - várias requisições na mesma conexão (client_st.py interativo e --demo);
#   - uma conexão por requisição (modo automático dos clientes / benchmark).
#
# Uso: python3 server_st.py [--port 5678] [--delay-ms 0] [--quiet]

from socket  import *
from constCS import * #-
import argparse
import json
from protocolo import enviar_mensagem, LeitorDeLinhas
from operacoes import processar_requisicao, resumir

parser = argparse.ArgumentParser(description="Servidor single-threaded da calculadora remota")
parser.add_argument("--host", default=HOST)
parser.add_argument("--port", type=int, default=PORT)
parser.add_argument("--delay-ms", type=float, default=0.0,
                    help="atraso simulado (I/O) por requisição, em ms (padrão 0)")
parser.add_argument("--quiet", action="store_true",
                    help="não imprime cada requisição (usado no benchmark)")
args = parser.parse_args()
atraso_s = args.delay_ms / 1000.0

def log(msg):
    if not args.quiet:
        print(msg, flush=True)

# ---------------------------------------------------------------------------
# Laço principal (mesma estrutura do exemplo do livro: socket, bind, listen,
# accept, recv/send), aceitando várias conexões em sequência.
# ---------------------------------------------------------------------------

s = socket(AF_INET, SOCK_STREAM)
s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)  # permite reiniciar o servidor sem esperar a porta liberar
s.bind((args.host, args.port))  #-
s.listen(128)  # backlog maior: no benchmark muitas conexões chegam ao mesmo tempo
print(f"Servidor ST ouvindo em {args.host}:{args.port} (delay={args.delay_ms} ms; Ctrl+C para encerrar)", flush=True)

try:
  while True:                    # aceita um cliente por vez, para sempre
    (conn, addr) = s.accept()    # returns new socket and addr. client
    log(f"Conexão de {addr}")
    leitor = LeitorDeLinhas(conn)
    try:
      while True:                # várias requisições na mesma conexão
        try:
          linha = leitor.ler_linha()
        except ValueError as e:  # mensagem grande demais: avisa e encerra a conexão
          enviar_mensagem(conn, {"ok": False, "error": str(e)})
          break
        if linha is None: break  # stop if client stopped
        log(f"  <- {resumir(linha)}")
        resposta = processar_requisicao(linha, atraso_s)
        log(f"  -> {resumir(json.dumps(resposta, ensure_ascii=False))}")
        enviar_mensagem(conn, resposta)
    except OSError as e:         # cliente caiu no meio: segue atendendo os próximos
      log(f"Erro na conexão com {addr}: {e}")
    finally:
      conn.close()               # close the connection
      log(f"Conexão com {addr} encerrada")
except KeyboardInterrupt:
  print("\nServidor encerrado.")
finally:
  s.close()
