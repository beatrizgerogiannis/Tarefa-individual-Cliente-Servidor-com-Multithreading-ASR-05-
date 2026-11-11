# Calculadora/Utilitário Remoto com Sockets TCP: versões single-thread e multithread

Sistemas Distribuídos (UFG). Extensão do exemplo cliente-servidor com sockets TCP da Fig. 2.3
(Cap. 2) do livro *Distributed Systems*, de Tanenbaum & van Steen.

- **ASR 04:** calculadora remota em que cada requisição carrega um **lote de operações**
  (4 numéricas e 3 de texto). Versão *single-threaded* (`server_st.py`, `client_st.py`).
- **ASR 05:** versão **multithread** (`server_mt.py`, `client_mt.py`), geração automática de
  requisições aleatórias e experimento de desempenho comparando três configurações.
  O relato do experimento está em **[RELATO.md](RELATO.md)**.

Só há dois componentes: **cliente** e **servidor**. Apenas a biblioteca padrão do Python 3 é usada
(o `graficos.py` usa também o `matplotlib`).

## Arquivos

| Arquivo            | Papel |
|--------------------|-------|
| `constCS.py`       | `HOST` e `PORT` padrão (`localhost:5678`). |
| `protocolo.py`     | Enquadramento: JSON em UTF-8 terminado em `\n`, leitura com buffer. |
| `operacoes.py`     | Lógica das 7 operações e do processamento do lote. **Usado pelos dois servidores**, que por isso dão respostas idênticas. |
| `server_st.py`     | Servidor single-threaded (ASR 04): atende uma conexão por vez. |
| `server_mt.py`     | Servidor multithread: **uma thread nova por requisição**. |
| `client_st.py`     | Cliente single-threaded: modo interativo, `--demo` e modo automático (sequencial); uma conexão por lote/requisição. |
| `client_mt.py`     | Cliente multithread: **uma thread nova por requisição** (modo automático). |
| `cliente_comum.py` | Código comum do modo automático dos clientes (envio, estatísticas, relatório). |
| `gerador.py`       | Gera N requisições aleatórias reprodutíveis (`--seed`). |
| `verificar.py`     | Verificação funcional: ST × MT, 2 servidores, casos de erro, nenhuma requisição perdida. |
| `benchmark.py`     | Experimento automático (sobe servidores, roda clientes, mede, salva CSV). |
| `graficos.py`      | Gera os gráficos em `results/` a partir de `results/resumo.csv`. |
| `results/`         | `resultados.csv` (cada execução), `resumo.csv` (média e desvio), gráficos `.png` e `complementar/` (variação de `--max-concurrent`). |

## Arquitetura de threads

**Servidor MT** (`server_mt.py`): a thread principal faz `accept()`, lê a requisição da conexão
aceita e cria uma `threading.Thread` que processa, envia a resposta e fecha a conexão. A thread
principal volta imediatamente ao `accept()`, sem `join()`.

```
principal:  accept ─► lê requisição ─► Thread(atender).start() ─► accept ─► ...
                                            │
thread k:                                   └─► processa (+ delay) ─► responde ─► close
```

**Cliente MT** (`client_mt.py`): para cada requisição, a thread principal cria uma thread nova,
que abre a conexão, envia, espera a resposta e guarda resposta e latência. Um
`threading.Semaphore(--max-concurrent)` limita quantas dessas threads ficam ativas ao mesmo tempo,
para não esgotar portas locais nem o backlog do servidor. Ao final, `join()` em todas.
Cada thread grava a resposta na própria posição de uma lista pré-alocada; latências e falhas
vão para listas compartilhadas protegidas por `threading.Lock`.

**Padrão de conexão:** em todos os modos, **os clientes abrem uma conexão TCP nova para cada
requisição** (conecta, envia, recebe, fecha). No interativo e no `--demo`, isso vale para cada
lote enviado. O servidor MT segue o modelo visto em aula (uma requisição por conexão) e o
servidor ST atende esse padrão sem mudanças, então **todos os modos do cliente funcionam com os
dois servidores**. Nos experimentos, a única diferença entre as configurações é o uso de threads.

**Atraso simulado:** os dois servidores aceitam `--delay-ms` (padrão 0), aplicado por requisição
com `time.sleep` em `operacoes.processar_requisicao`. Ele representa trabalho de I/O, como uma
consulta a banco.

## Protocolo de aplicação

Cada mensagem é **um objeto JSON numa única linha terminada por `\n`** (o TCP não preserva
fronteiras de mensagem; o receptor acumula bytes até achar o `\n`). Limite de 1 MiB por mensagem.

Requisição:

```json
{"ops": [{"op": "add", "args": [2, 3]}, {"op": "upper", "args": ["ola"]}]}
```

Resposta (um resultado por operação, na mesma ordem):

```json
{"results": [{"op": "add", "ok": true, "result": 5}, {"op": "upper", "ok": true, "result": "OLA"}]}
```

Uma operação com erro é marcada sozinha (`{"op": "div", "ok": false, "error": "divisão por zero"}`)
e as demais são executadas. Requisição inteira inválida (JSON malformado, sem `"ops"`, maior que
1 MiB) recebe um erro único: `{"ok": false, "error": "..."}`.

## Operações

| Operação      | Argumentos         | Retorno                          | Possíveis erros |
|---------------|--------------------|----------------------------------|-----------------|
| `add`         | `a`, `b` (números) | `a + b`                          | nº de argumentos ≠ 2; argumento não numérico |
| `sub`         | `a`, `b` (números) | `a - b`                          | idem |
| `mul`         | `a`, `b` (números) | `a * b`                          | idem |
| `div`         | `a`, `b` (números) | `a / b` (float)                  | idem; divisão por zero |
| `upper`       | `texto`            | texto em maiúsculas              | nº de argumentos ≠ 1; argumento não é texto |
| `reverse`     | `texto`            | texto invertido                  | idem |
| `count_words` | `texto`            | quantidade de palavras           | idem |

`true`/`false` não são aceitos como números. Para adicionar uma operação, escreva a função em
`operacoes.py` e registre-a em `OPERACOES` (`nome → (função, nº de argumentos)`).

## Como executar

Requer Python 3. Abra terminais na pasta do projeto.

### Uso manual: interativo e demonstração

```bash
python3 server_st.py               # terminal 1 (ou: python3 server_mt.py)
python3 client_st.py --demo        # terminal 2: lotes de exemplo, com casos de erro
python3 client_st.py               # terminal 2: modo interativo
```

Os dois modos funcionam com qualquer um dos servidores, porque cada lote vai numa conexão nova.
Para usar outro endereço: `python3 client_st.py --servers localhost:5679`. Se o servidor
estiver fora do ar, o interativo avisa e mantém o lote para reenviar.

No modo interativo: `<op> <args...>` adiciona ao lote, `enviar`, `lote`, `limpar`, `ajuda`, `sair`.

```
[0 op(s) no lote] > add 2 3
[1 op(s) no lote] > upper "ola mundo"
[2 op(s) no lote] > enviar
  [1] add          ok    -> 5
  [2] upper        ok    -> 'OLA MUNDO'
```

### Modo automático (requisições aleatórias)

Parâmetros comuns aos dois clientes: `--n` (nº de requisições), `--seed` (semente; padrão 42),
`--servers host:porta,host:porta` (round-robin; padrão `localhost:5678`) e `--json` (métricas em
JSON). O cliente MT tem ainda `--max-concurrent` (padrão 64). Os servidores aceitam `--port`,
`--delay-ms` e `--quiet` (não imprime cada requisição).

```bash
# Configuração A: cliente ST + servidor ST
python3 server_st.py --delay-ms 10
python3 client_st.py --n 1000 --seed 42

# Configuração B: cliente ST + servidor MT
python3 server_mt.py --delay-ms 10
python3 client_st.py --n 1000 --seed 42

# Configuração C: cliente MT + servidor MT
python3 server_mt.py --delay-ms 10
python3 client_mt.py --n 1000 --seed 42 --max-concurrent 64

# Cliente MT com dois servidores MT
python3 server_mt.py --port 5678 &
python3 server_mt.py --port 5679 &
python3 client_mt.py --n 1000 --servers localhost:5678,localhost:5679
```

Exemplo de saída real (configuração C, servidor com `--delay-ms 10`):

```
Cliente MT: 1000 requisições para localhost:5678 (seed=42)
  sucessos: 1000   falhas: 0
  tempo total: 0.620 s   vazão: 1611.8 req/s
  latência (ms): média 13.06   p50 12.98   p95 14.59
```

Para ver as requisições que uma semente gera: `python3 gerador.py --n 5 --seed 42`.

### Verificação funcional

```bash
python3 verificar.py
```

O script sobe um servidor ST e dois MT e envia as mesmas requisições (mesma seed) em várias
combinações cliente/servidor. Em seguida compara as respostas **por id da requisição** com a
referência ST→ST, testa os casos de erro nos dois servidores e confere que nenhuma requisição
se perdeu.

### Benchmark e gráficos

```bash
python3 benchmark.py                 # padrão: N=100,1000,5000; delay 0 e 10 ms; 5 repetições
python3 -m venv .venv && .venv/bin/pip install matplotlib   # só uma vez
.venv/bin/python graficos.py         # gera results/*.png
```

O `benchmark.py` sobe os servidores como subprocessos, espera ficarem prontos, roda o cliente,
coleta as métricas (tempo total, vazão, latência média/p50/p95) e encerra os servidores, para
cada combinação. As opções `--reps`, `--ns`, `--delays`, `--configs` e `--max-concurrent` mudam
os parâmetros. Os resultados e a análise estão em [RELATO.md](RELATO.md).
