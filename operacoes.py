# Lógica das operações da calculadora remota.
#
# Este módulo é usado pelas DUAS versões do servidor (server_st.py e
# server_mt.py), para que ambas executem exatamente o mesmo código e, portanto,
# deem exatamente as mesmas respostas. A única diferença entre elas é COMO as
# requisições são atendidas (uma por vez ou uma thread por requisição).
#
# Nenhuma função daqui guarda estado global mutável: cada chamada trabalha só
# com os próprios argumentos. Por isso elas podem ser chamadas por várias
# threads ao mesmo tempo sem precisar de locks.

import json
import time


class ErroOperacao(Exception):
    """Erro de uma operação específica (não derruba o lote nem o servidor)."""


def exigir_numero(x):
    # bool é subclasse de int em Python; não queremos aceitar true/false como número
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ErroOperacao(f"argumento {x!r} não é numérico")
    return x


def exigir_texto(x):
    if not isinstance(x, str):
        raise ErroOperacao(f"argumento {x!r} não é texto")
    return x


def op_add(a, b):
    return exigir_numero(a) + exigir_numero(b)

def op_sub(a, b):
    return exigir_numero(a) - exigir_numero(b)

def op_mul(a, b):
    return exigir_numero(a) * exigir_numero(b)

def op_div(a, b):
    a, b = exigir_numero(a), exigir_numero(b)
    if b == 0:
        raise ErroOperacao("divisão por zero")
    return a / b

def op_upper(texto):
    return exigir_texto(texto).upper()

def op_reverse(texto):
    return exigir_texto(texto)[::-1]

def op_count_words(texto):
    return len(exigir_texto(texto).split())


# Tabela de despacho: nome da operação -> (função, número de argumentos).
# Para adicionar uma operação nova basta escrever a função e incluí-la aqui.
OPERACOES = {
    "add":         (op_add, 2),
    "sub":         (op_sub, 2),
    "mul":         (op_mul, 2),
    "div":         (op_div, 2),
    "upper":       (op_upper, 1),
    "reverse":     (op_reverse, 1),
    "count_words": (op_count_words, 1),
}


def executar_operacao(item):
    """Executa UMA operação do lote e devolve o dicionário de resultado."""
    if not isinstance(item, dict):
        return {"op": None, "ok": False, "error": "cada operação deve ser um objeto JSON"}
    nome = item.get("op")
    args = item.get("args", [])
    if nome not in OPERACOES:
        return {"op": nome, "ok": False, "error": f"operação desconhecida: {nome!r}"}
    if not isinstance(args, list):
        return {"op": nome, "ok": False, "error": "'args' deve ser uma lista"}
    funcao, aridade = OPERACOES[nome]
    if len(args) != aridade:
        return {"op": nome, "ok": False,
                "error": f"'{nome}' espera {aridade} argumento(s), recebeu {len(args)}"}
    try:
        return {"op": nome, "ok": True, "result": funcao(*args)}
    except ErroOperacao as e:
        return {"op": nome, "ok": False, "error": str(e)}
    except Exception as e:  # rede de segurança: erro inesperado vira erro da operação
        return {"op": nome, "ok": False, "error": f"erro interno: {e}"}


def processar_requisicao(linha, atraso_s=0.0):
    """Interpreta uma linha JSON e processa TODAS as operações do lote, em ordem.

    atraso_s simula trabalho de I/O por requisição (ex.: consulta a um banco de
    dados). time.sleep bloqueia só a thread que o chama e LIBERA o GIL, então,
    no servidor multithread, outras threads continuam trabalhando enquanto
    esta "espera o banco".
    """
    if atraso_s > 0:
        time.sleep(atraso_s)
    try:
        requisicao = json.loads(linha)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON inválido: {e.msg}"}
    if not isinstance(requisicao, dict) or not isinstance(requisicao.get("ops"), list):
        return {"ok": False, "error": "requisição deve ter o formato {\"ops\": [...]}"}
    return {"results": [executar_operacao(item) for item in requisicao["ops"]]}


def resumir(texto, limite=200):
    """Encurta textos longos só para o log do servidor."""
    return texto if len(texto) <= limite else texto[:limite] + f"... ({len(texto)} caracteres)"
