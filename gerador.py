# Gerador automático de requisições aleatórias.
#
# gerar_requisicoes(n, seed) devolve SEMPRE a mesma lista para a mesma semente
# (usa um random.Random próprio, sem depender do estado global do módulo
# random). Assim as configurações A, B e C do experimento recebem exatamente
# as mesmas requisições.
#
# Uso direto (imprime as requisições, uma por linha):
#   python3 gerador.py --n 5 --seed 42

import argparse
import json
import random

PALAVRAS = ("sistemas distribuídos thread socket servidor cliente rede mensagem "
            "processo latência vazão concorrência paralelismo goiânia ufg "
            "requisição resposta protocolo tcp porta").split()

OPS_NUMERICAS = ["add", "sub", "mul", "div"]
OPS_TEXTO = ["upper", "reverse", "count_words"]


def numero_aleatorio(rng):
    """Inteiro (70%) ou float com 2 casas (30%). Pode sair 0: div por zero acontece às vezes."""
    if rng.random() < 0.7:
        return rng.randint(-50, 50)
    return round(rng.uniform(-1000, 1000), 2)


def texto_aleatorio(rng):
    return " ".join(rng.choice(PALAVRAS) for _ in range(rng.randint(1, 12)))


def operacao_aleatoria(rng):
    op = rng.choice(OPS_NUMERICAS + OPS_TEXTO)
    if op in OPS_NUMERICAS:
        return {"op": op, "args": [numero_aleatorio(rng), numero_aleatorio(rng)]}
    return {"op": op, "args": [texto_aleatorio(rng)]}


def gerar_requisicoes(n, seed):
    """Lista de n pares (id, requisição); cada requisição tem de 1 a 3 operações."""
    rng = random.Random(seed)
    return [(i, {"ops": [operacao_aleatoria(rng) for _ in range(rng.randint(1, 3))]})
            for i in range(n)]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Gera requisições aleatórias reprodutíveis")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    for i, req in gerar_requisicoes(a.n, a.seed):
        print(i, json.dumps(req, ensure_ascii=False))
