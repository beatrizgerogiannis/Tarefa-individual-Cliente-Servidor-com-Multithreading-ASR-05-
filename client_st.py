# Cliente SINGLE-THREADED (versão da ASR 04 + modo automático).
#
# Modos:
#   python3 client_st.py                 interativo
#   python3 client_st.py --demo          demonstração com casos de erro
#   python3 client_st.py --n 1000 --seed 42 [--servers h:p,h:p]
#                                        automático: requisições aleatórias enviadas
#                                        UMA DE CADA VEZ
#
# Em todos os modos, cada lote/requisição usa uma conexão TCP NOVA (conecta,
# envia, recebe, fecha). Assim o cliente funciona tanto com server_st.py quanto
# com server_mt.py, que atende uma requisição por conexão. No interativo e no
# --demo, o servidor é o primeiro de --servers (padrão: HOST:PORT de constCS.py).

from socket  import *
from constCS import * #-
import argparse
import json
import shlex
import sys
import time
from protocolo import enviar_linha_bruta, LeitorDeLinhas
from gerador import gerar_requisicoes
import cliente_comum


def mostrar_resposta(resposta):
    """Imprime a resposta do servidor de forma legível."""
    if "results" not in resposta:  # erro da requisição como um todo (ex.: JSON inválido)
        print(f"  ERRO NA REQUISIÇÃO: {resposta.get('error')}")
        return
    for i, r in enumerate(resposta["results"], 1):
        if r.get("ok"):
            print(f"  [{i}] {r['op']:<12} ok    -> {r['result']!r}")
        else:
            print(f"  [{i}] {str(r.get('op')):<12} ERRO  -> {r['error']}")


def enviar_e_receber(endereco, texto):
    """Abre uma conexão NOVA, envia uma linha, lê a resposta e fecha a conexão."""
    s = socket(AF_INET, SOCK_STREAM)
    s.connect(endereco)         # connect to server (block until accepted)
    try:
        enviar_linha_bruta(s, texto)
        resposta = LeitorDeLinhas(s).ler_linha()
    finally:
        s.close()               # close the connection
    if resposta is None:
        raise ConnectionError("servidor fechou a conexão sem responder")
    return json.loads(resposta)


def requisitar(endereco, ops, mostrar=None):
    """Envia um lote de operações (numa conexão nova) e mostra a resposta."""
    texto = json.dumps({"ops": ops}, ensure_ascii=False)
    print(f"Enviando: {mostrar or texto}")
    mostrar_resposta(enviar_e_receber(endereco, texto))


# ---------------------------------------------------------------------------
# Modo demonstração: lotes fixos, incluindo casos de erro.
# ---------------------------------------------------------------------------

LOTES_DEMO = [
    ("Lote 1: várias operações numéricas e de texto numa só requisição", [
        {"op": "add", "args": [2, 3]},
        {"op": "sub", "args": [10, 4.5]},
        {"op": "mul", "args": [6, 7]},
        {"op": "div", "args": [1, 4]},
        {"op": "upper", "args": ["olá, mundo"]},
        {"op": "reverse", "args": ["sistemas distribuídos"]},
        {"op": "count_words", "args": ["o rato roeu a roupa do rei de roma"]},
    ]),
    ("Lote 2: erros por operação (as demais continuam funcionando)", [
        {"op": "div", "args": [5, 0]},             # divisão por zero
        {"op": "pow", "args": [2, 8]},             # operação desconhecida
        {"op": "add", "args": [1]},                # número de argumentos errado
        {"op": "mul", "args": ["3", 4]},           # tipo errado
        {"op": "upper", "args": [123]},            # tipo errado
        {"op": "add", "args": [100, 200]},         # esta deve dar certo
    ]),
    ("Lote 3: mensagem grande (texto de ~50 KB, bem maior que recv(1024))", [
        {"op": "count_words", "args": ["palavra " * 6000]},
    ]),
]


def modo_demo(endereco):
    for titulo, ops in LOTES_DEMO:
        print(f"\n=== {titulo}")
        if titulo.startswith("Lote 3"):  # não imprime o texto gigante inteiro
            resumo = f"{{\"ops\": [{{\"op\": \"count_words\", \"args\": [\"palavra palavra ...\" ({len(ops[0]['args'][0])} caracteres)]}}]}}"
            requisitar(endereco, ops, mostrar=resumo)
        else:
            requisitar(endereco, ops)

    print("\n=== Lote 4: JSON inválido (o servidor responde erro e segue vivo)")
    bruto = '{"ops": [{"op": "add", "args": [1, 2]'  # falta fechar colchetes/chaves
    print(f"Enviando: {bruto}")
    mostrar_resposta(enviar_e_receber(endereco, bruto))

    print("\n=== Lote 5: formato errado (sem a chave \"ops\")")
    bruto = '{"op": "add", "args": [1, 2]}'
    print(f"Enviando: {bruto}")
    mostrar_resposta(enviar_e_receber(endereco, bruto))

    print("\n=== Lote 6: depois dos erros, o servidor continua atendendo normalmente")
    requisitar(endereco, [{"op": "mul", "args": [3, 3]}, {"op": "reverse", "args": ["fim"]}])


# ---------------------------------------------------------------------------
# Modo interativo: o usuário monta um lote e envia.
# ---------------------------------------------------------------------------

AJUDA = """Comandos:
  <op> <arg1> [arg2]  adiciona uma operação ao lote. Ex.: add 2 3 | upper "ola mundo"
  lote                mostra o lote atual
  enviar              envia o lote ao servidor (e o esvazia)
  limpar              esvazia o lote sem enviar
  ajuda               mostra esta ajuda
  sair                encerra o cliente
Operações do servidor: add, sub, mul, div, upper, reverse, count_words
Argumentos que parecem números são enviados como números; use aspas para textos com espaço."""


def converter_argumento(token):
    """Converte '3' -> 3, '2.5' -> 2.5; o resto fica como texto."""
    for tipo in (int, float):
        try:
            return tipo(token)
        except ValueError:
            pass
    return token


def modo_interativo(endereco):
    print(AJUDA)
    print(f"Servidor: {endereco[0]}:{endereco[1]} (uma conexão nova a cada envio)")
    lote = []
    while True:
        try:
            linha = input(f"\n[{len(lote)} op(s) no lote] > ").strip()
        except EOFError:
            break
        if not linha:
            continue
        try:
            partes = shlex.split(linha)
        except ValueError as e:
            print(f"Entrada inválida: {e}")
            continue
        comando = partes[0]
        if comando == "sair":
            break
        elif comando == "ajuda":
            print(AJUDA)
        elif comando == "lote":
            for i, op in enumerate(lote, 1):
                print(f"  [{i}] {json.dumps(op, ensure_ascii=False)}")
            if not lote:
                print("  (vazio)")
        elif comando == "limpar":
            lote = []
        elif comando == "enviar":
            if not lote:
                print("Lote vazio; adicione operações antes de enviar.")
                continue
            try:
                requisitar(endereco, lote)
                lote = []
            except (OSError, ValueError) as e:  # servidor fora do ar, resposta inválida...
                print(f"Falha ao falar com o servidor ({type(e).__name__}: {e}); o lote foi mantido.")
        else:
            # Qualquer outro comando vira uma operação; quem valida é o servidor.
            lote.append({"op": comando, "args": [converter_argumento(t) for t in partes[1:]]})


# ---------------------------------------------------------------------------
# Modo automático: N requisições aleatórias, enviadas em sequência (sem threads).
# ---------------------------------------------------------------------------

def modo_automatico(args):
    servidores = cliente_comum.ler_servidores(args.servers)
    requisicoes = gerar_requisicoes(args.n, args.seed)  # gerado ANTES de medir
    respostas = [None] * args.n
    latencias, falhas = [], []

    inicio = time.perf_counter()
    for i, req in requisicoes:
        endereco = servidores[i % len(servidores)]  # round-robin
        try:
            respostas[i], lat = cliente_comum.enviar_requisicao(endereco, req)
            latencias.append(lat)
        except Exception as e:
            falhas.append((i, f"{type(e).__name__}: {e}"))
    tempo_total = time.perf_counter() - inicio

    cliente_comum.relatar(args, "ST", tempo_total, respostas, latencias, falhas)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente single-threaded da calculadora remota")
    parser.add_argument("--demo", action="store_true", help="envia lotes de demonstração")
    cliente_comum.argumentos_automaticos(parser)
    args = parser.parse_args()

    if args.n is not None:
        modo_automatico(args)
        sys.exit(0)

    endereco = cliente_comum.ler_servidores(args.servers)[0]
    if args.demo:
        modo_demo(endereco)
    else:
        modo_interativo(endereco)
