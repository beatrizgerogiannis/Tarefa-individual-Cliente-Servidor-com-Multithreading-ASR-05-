# ASR 05: Multithreading no cliente e no servidor da calculadora remota

## 1. Objetivo

Acrescentar multithreading à calculadora remota cliente-servidor da ASR 04 (sockets TCP, Python),
automatizar a geração de requisições e medir o efeito das threads no desempenho. Foram comparadas
três configurações:

| Config. | Cliente | Servidor |
|---------|---------|----------|
| **A** | single-threaded (`client_st.py`) | single-threaded (`server_st.py`), versão da ASR 04 |
| **B** | single-threaded (`client_st.py`) | multithread (`server_mt.py`) |
| **C** | multithread (`client_mt.py`) | multithread (`server_mt.py`) |

Também rodei uma configuração extra, **C2**: o cliente MT distribuindo as requisições em
round-robin entre **dois** servidores MT (portas diferentes, mesma máquina).

O comportamento funcional não mudou. A lógica das operações foi movida para um módulo único
(`operacoes.py`), usado pelos dois servidores, e a verificação da seção 3 confirmou respostas
idênticas.

## 2. Arquitetura de threads

**Servidor MT.** A thread principal faz `accept()` e lê a requisição (uma linha JSON) na conexão
aceita. Em seguida cria uma `threading.Thread` que processa as operações, envia a resposta e fecha
a conexão. A thread principal não faz `join()` e volta imediatamente ao `accept()`. As threads
trabalhadoras não compartilham dados (cada uma tem sua conexão e sua requisição), então só o log
usa um `Lock`.

**Cliente MT.** As N requisições são geradas antes do início da medição. Para cada requisição, a
thread principal cria uma thread nova, que abre a conexão (servidor escolhido por round-robin),
envia, espera a resposta e registra resposta e latência. Um `threading.Semaphore(64)` limita a 64
o número de threads de requisição ativas ao mesmo tempo. Continua sendo uma thread por requisição;
o limite só evita esgotar portas locais e o backlog do `listen()` (aumentado para 128 nos dois
servidores). Cada thread grava a resposta na própria posição de uma lista pré-alocada. Latências
e falhas vão para listas protegidas por `Lock`. No fim, `join()` em todas as threads e só então o
cronômetro para.

**Cliente ST.** Envia as mesmas requisições em sequência, uma de cada vez.

**Padrão de conexão.** Nas três configurações, cada requisição usa uma conexão TCP própria:
conecta, envia, recebe e fecha. Assim a única variável entre A, B e C é o uso de threads. O
servidor ST aceita esse padrão sem mudanças, porque continua atendendo uma conexão por vez até o
cliente fechá-la.

**Atraso simulado.** Os servidores aceitam `--delay-ms`, aplicado com `time.sleep` em cada
requisição antes do processamento. Ele representa trabalho de I/O, como uma consulta a banco de
dados.

## 3. Verificação funcional

O script `verificar.py` sobe um servidor ST e dois MT e envia 2000 requisições aleatórias
(seed 7) nas combinações ST→ST (referência), ST→MT, MT→MT, MT→2 servidores MT e MT→ST.
Resultados:

- Todas as combinações tiveram 2000 sucessos e 0 falhas.
- As respostas, comparadas por id da requisição, foram idênticas às da referência em todas as
  combinações. Essas requisições aleatórias incluíram 4 operações com erro (divisões por zero).
- 14 casos de erro enviados aos dois servidores receberam respostas idênticas: divisão por zero,
  operação desconhecida, número errado de argumentos, tipos errados, `true` como número, `args`
  que não é lista, item que não é objeto, erro misturado com sucesso, JSON inválido, requisição
  sem `ops`, lote vazio, mensagem de 50 KB e mensagem acima de 1 MiB.

O modo interativo e o `--demo` da ASR 04 passaram a abrir uma conexão nova a cada lote e
funcionam com os dois servidores. A saída do `--demo` foi idêntica contra o `server_st.py` e
contra o `server_mt.py`.

## 4. Metodologia

- **Requisições:** `gerador.py` gera N requisições com `random.Random(seed)`, seed 42. Cada
  requisição tem de 1 a 3 operações sorteadas entre as 7, com números (inteiros ou floats) e
  textos aleatórios. A mesma seed gera as mesmas requisições em todas as configurações.
- **Variáveis:** N ∈ {100, 1000, 5000}; delay no servidor ∈ {0, 10 ms}.
- **Repetições:** 5 por combinação. Dentro de cada repetição as configurações rodam intercaladas
  (A, B, C, C2), para que variações da máquina afetem todas igualmente.
- **Execução (`benchmark.py`):** para cada execução, sobe o(s) servidor(es) como subprocesso com
  `--quiet`, espera a porta aceitar conexões, roda o cliente como subprocesso e encerra o(s)
  servidor(es). Cada execução usa um processo de servidor novo.
- **Métricas (medidas no cliente com `time.perf_counter`):** tempo total para as N requisições
  (do envio da primeira até a resposta da última), vazão (N / tempo total) e latência por
  requisição (média, p50, p95). A latência vai da abertura da conexão até a leitura da resposta.
  No cliente MT ela não inclui o tempo de espera no semáforo.
- **Concorrência do cliente MT:** nos experimentos principais (C e C2), `--max-concurrent = 64`
  (valor padrão), registrado na coluna `max_concurrent` de `resultados.csv`. A seção 5 traz uma
  varredura complementar de 1 a 128.
- **Ajuste de N:** nenhum foi necessário. A e B com delay 10 ms e N = 5000 levaram de 55 a 60 s
  por execução, o que coube no tempo do experimento. Todas as combinações rodaram com N completo.
- **Máquina:** Intel Core i7-10750H @ 2,60 GHz (6 núcleos físicos, 12 lógicos;
  `os.cpu_count()` = 12). Ubuntu 24.04 no WSL2 (kernel 6.6.87.2-microsoft-standard-WSL2), Python
  3.12.3 (CPython, com GIL). Cliente e servidor rodaram na mesma máquina, via loopback
  (`localhost`).
- **Arquivos:** `results/resultados.csv` (cada uma das 120 execuções, com versão do Python, SO,
  CPU e núcleos), `results/resumo.csv` (média e desvio padrão) e os gráficos em `results/`.

## 5. Resultados

Valores: média ± desvio padrão de 5 repetições. Nenhuma das 120 execuções teve falha ou requisição
perdida.

### Delay = 0 ms (só as operações, curtas e CPU-bound)

| N | Config. | Tempo total (s) | Vazão (req/s) | Latência média (ms) | p50 (ms) | p95 (ms) |
|---|---|---|---|---|---|---|
| 100  | A  | 0,031 ± 0,001 | 3222 ± 150 | 0,30 ± 0,01 | 0,27 | 0,41 |
| 100  | B  | 0,045 ± 0,001 | 2215 ± 29  | 0,44 ± 0,01 | 0,41 | 0,54 |
| 100  | C  | 0,063 ± 0,004 | 1599 ± 86  | 2,86 ± 0,36 | 2,72 | 4,56 |
| 100  | C2 | 0,063 ± 0,003 | 1594 ± 73  | 2,76 ± 0,36 | 2,57 | 5,17 |
| 1000 | A  | 0,285 ± 0,012 | 3509 ± 150 | 0,27 ± 0,01 | 0,27 | 0,33 |
| 1000 | B  | 0,472 ± 0,021 | 2121 ± 93  | 0,46 ± 0,02 | 0,43 | 0,58 |
| 1000 | C  | 0,643 ± 0,031 | 1558 ± 76  | 2,95 ± 0,14 | 2,81 | 4,49 |
| 1000 | C2 | 0,622 ± 0,033 | 1611 ± 83  | 2,71 ± 0,21 | 2,56 | 4,22 |
| 5000 | A  | 1,495 ± 0,049 | 3347 ± 110 | 0,29 ± 0,01 | 0,27 | 0,39 |
| 5000 | B  | 2,265 ± 0,053 | 2209 ± 51  | 0,44 ± 0,01 | 0,42 | 0,56 |
| 5000 | C  | 3,496 ± 0,330 | 1440 ± 130 | 3,19 ± 0,32 | 2,99 | 4,99 |
| 5000 | C2 | 3,320 ± 0,098 | 1507 ± 43  | 2,85 ± 0,07 | 2,73 | 4,40 |

### Delay = 10 ms (simulando I/O no servidor)

| N | Config. | Tempo total (s) | Vazão (req/s) | Latência média (ms) | p50 (ms) | p95 (ms) |
|---|---|---|---|---|---|---|
| 100  | A  | 1,104 ± 0,005  | 90,6 ± 0,4 | 11,00 ± 0,05 | 10,84 | 12,07 |
| 100  | B  | 1,123 ± 0,015  | 89,1 ± 1,2 | 11,20 ± 0,15 | 11,02 | 12,44 |
| 100  | C  | 0,084 ± 0,015  | 1215 ± 200 | 14,04 ± 1,00 | 13,72 | 17,61 |
| 100  | C2 | 0,074 ± 0,004  | 1348 ± 61  | 13,03 ± 0,30 | 12,81 | 15,78 |
| 1000 | A  | 10,97 ± 0,06   | 91,2 ± 0,5 | 10,93 ± 0,06 | 10,72 | 11,93 |
| 1000 | B  | 11,35 ± 0,13   | 88,1 ± 1,0 | 11,31 ± 0,13 | 11,08 | 12,64 |
| 1000 | C  | 0,630 ± 0,045  | 1594 ± 110 | 13,03 ± 0,23 | 12,92 | 14,67 |
| 1000 | C2 | 0,638 ± 0,044  | 1573 ± 110 | 12,86 ± 0,21 | 12,75 | 14,35 |
| 5000 | A  | 56,20 ± 2,00   | 89,0 ± 3,0 | 11,15 ± 0,26 | 10,84 | 11,92 |
| 5000 | B  | 57,08 ± 0,28   | 87,6 ± 0,4 | 11,38 ± 0,05 | 11,20 | 12,79 |
| 5000 | C  | 3,082 ± 0,062  | 1623 ± 32  | 13,00 ± 0,08 | 12,85 | 14,64 |
| 5000 | C2 | 3,143 ± 0,120  | 1593 ± 60  | 12,88 ± 0,12 | 12,72 | 14,41 |

### Gráficos

- `results/tempo_total_delay_0ms.png`: tempo total por configuração e N, delay 0 (escala log).
- `results/tempo_total_delay_10ms.png`: tempo total por configuração e N, delay 10 ms (escala log).
- `results/vazao.png`: vazão por configuração e N, lado a lado para os dois delays.

### Medição complementar: limite de concorrência do cliente MT

Para entender por que C fica perto de 1600 req/s com e sem delay, rodei a configuração C com
N = 1000 e 3 repetições, variando `--max-concurrent` (dados em `results/complementar/`). A
varredura de 1 a 128 foi feita **com delay de 10 ms**; com delay 0 medi apenas 1 e 64.

Duas colunas foram derivadas das medidas:

- **Em voo (média):** número médio de requisições de fato em andamento, estimado pela lei de
  Little como vazão × latência média.
- **Teto (mc / latência):** vazão máxima possível se as `mc` threads permitidas estivessem
  sempre ocupadas, cada uma com a latência medida.

| Delay | max-concurrent | Tempo total (s) | Vazão (req/s) | Latência média (ms) | Em voo (média) | Teto (mc / latência) |
|---|---|---|---|---|---|---|
| 10 ms | 1   | 11,54 ± 0,08  | 86,6 ± 0,6  | 11,13 | 1,0  | 90 req/s |
| 10 ms | 8   | 1,447 ± 0,004 | 691 ± 2     | 11,14 | 7,7  | 718 req/s |
| 10 ms | 16  | 0,765 ± 0,025 | 1309 ± 43   | 11,54 | 15,1 | 1386 req/s |
| 10 ms | 32  | 0,738 ± 0,031 | 1357 ± 58   | 13,60 | 18,5 | 2352 req/s |
| 10 ms | 64  | 0,684 ± 0,032 | 1463 ± 71   | 13,25 | 19,4 | 4829 req/s |
| 10 ms | 128 | 0,653 ± 0,023 | 1532 ± 53   | 13,14 | 20,1 | 9739 req/s |
| 0 ms  | 1   | 0,687 ± 0,009 | 1456 ± 20   | 0,48  | 0,7  | 2094 req/s |
| 0 ms  | 64  | 0,692 ± 0,038 | 1448 ± 81   | 3,18  | 4,6  | 20156 req/s |

Também medi o uso de CPU do cliente MT com `/usr/bin/time` (C, delay 10 ms, N = 5000, 2
execuções): ~3,5 s de tempo real, com ~1,2 s de CPU em modo usuário e ~3,6 a 4,0 s em modo
sistema, ou seja, ~140% de CPU. O servidor MT acumulou 3 s de CPU para as 10 000 requisições
dessas duas execuções. Esse valor foi lido com `ps`, que tem resolução de 1 s, então o valor
real fica entre 3 e 4 s. Foi uma medição pontual, sem repetições.

## 6. Análise

**Com delay 10 ms (I/O-bound), o multithreading nos dois lados ajudou muito.** Em A e B, cada
requisição custa ~11 ms (10 ms de sleep mais ~1 ms de rede e processamento) e as requisições são
atendidas uma após a outra, então o tempo cresce linearmente: ~1,1 s, ~11 s e ~56 s para N = 100,
1000 e 5000, ou ~90 req/s. Em C, muitas requisições ficam "esperando o banco" ao mesmo tempo.
`time.sleep`, assim como uma espera de I/O real, libera o GIL, então as esperas se sobrepõem. O
tempo de C caiu para 0,084 s (N = 100), 0,630 s (N = 1000) e 3,08 s (N = 5000). São ganhos sobre
A de ~13× para N = 100 (1,104 / 0,084), ~17× para N = 1000 (10,97 / 0,630) e ~18× para N = 5000
(56,20 / 3,08). Com N = 100 o ganho é menor, e os dados são compatíveis com o efeito da "rampa"
inicial em uma execução curta. Pela lei de Little, a média de requisições em voo foi 17,1 com
N = 100, contra 20,8 e 21,1 com N = 1000 e N = 5000. A latência
individual em C (~13 ms) é um pouco maior que em A (~11 ms), porque com ~20 requisições
simultâneas cada uma disputa CPU com as outras. O ganho veio da sobreposição de requisições, não
de cada uma ficar mais rápida.

**Com delay 0 (operações curtas e CPU-bound), o multithreading piorou.** O tempo total em
N = 5000 foi 1,50 s (A), 2,27 s (B) e 3,50 s (C): B foi ~1,5× e C ~2,3× mais lento que A. As
operações (somas, `upper`, contar palavras) levam microssegundos. No CPython só uma thread executa
bytecode Python por vez em cada processo (GIL), então várias threads executando essas operações
não ganham paralelismo real. O que resta é o custo das threads:

- **Servidor:** criar e iniciar uma `Thread` por requisição acrescentou ~0,15 ms por requisição
  (com N = 5000, latência média de 0,29 ms em A contra 0,44 ms em B).
- **Cliente:** na medição complementar com delay 0, C com `max-concurrent = 1` (uma thread por
  vez, sem concorrência) levou 0,687 s para 1000 requisições, contra 0,472 s de B no experimento
  principal. São ~0,2 ms a mais por requisição só para criar, iniciar e esperar a thread no
  cliente. Com `max-concurrent = 64`, o tempo foi praticamente o mesmo (0,692 s): a concorrência
  não trouxe ganho nenhum quando não há espera de I/O para sobrepor.
- **Latência:** em C a latência média sobe para ~3 ms (2,86 a 3,19 ms, contra 0,27 a 0,30 ms em A).
  Isso acontece mesmo com poucas requisições em voo: pela lei de Little, ~4,6 em média, longe das
  64 permitidas. Uma explicação compatível com os dados é que as threads de requisição disputam o
  GIL com a thread principal, que está sempre criando threads novas. Essa disputa não foi medida
  diretamente.

**B ≈ A: servidor MT sem cliente paralelo não ganha nada.** O cliente ST só envia a próxima
requisição depois de receber a resposta da anterior, então o servidor MT nunca tem mais de uma
requisição em andamento. Cada thread que ele cria trabalha sozinha e termina antes de a próxima
chegar. Por isso B ficou praticamente igual a A com delay 10 ms (87,6 a 89,1 contra 89,0 a 91,2
req/s; tempo total de B 1,6% a 3,5% maior) e
pior com delay 0 (custo da thread sem benefício). Para o servidor multithread fazer diferença, é
preciso que cheguem várias requisições ao mesmo tempo, ou seja, cliente(s) concorrente(s): a
configuração C.

**Teto de C: ~1500 a 1600 req/s, imposto pelo cliente, não pelo limite de concorrência.** Nos
experimentos principais, C usou `--max-concurrent = 64`. Se as 64 threads permitidas estivessem
sempre ocupadas, com a latência medida de ~13 ms, o teto seria 64 / 0,013 s ≈ 4900 req/s. C ficou
em 1594 e 1623 req/s (N = 1000 e N = 5000), praticamente a mesma vazão de C com delay 0 (1440 a
1599 req/s).

O valor de ~1600 req/s coincide numericamente com 16 / 0,01 s, o teto de 16 threads com 10 ms
cada. Mas o semáforo nos experimentos principais era de 64, e a varredura com delay 10 ms mostra
que essa coincidência não explica o teto:

- **Até 16 threads, a concorrência é o limite.** Com 1, 8 e 16 permitidas, a vazão acompanha o
  teto mc / latência (96%, 96% e 94% dele): 86,6 → 691 → 1309 req/s. Com 16, o teto é 1386 req/s e
  não 1600, porque cada requisição leva ~11,5 ms, não 10 ms.
- **Acima de 16, o limite passa a ser outro.** Permitir 32, 64 e 128 threads (2×, 4× e 8× mais)
  eleva a vazão só de 1309 para 1357, 1463 e 1532 req/s, ou seja, 58%, 30% e 16% do teto
  correspondente.
- **As threads permitidas não são preenchidas.** Pela lei de Little, o número médio de requisições
  em voo fica em 18,5 a 20,1 com 32 a 128 permitidas, e em 17 a 21 nos experimentos principais
  com 64. O cliente não consegue criar e iniciar threads rápido o bastante para ocupar as vagas
  do semáforo.
- **Sem delay e sem concorrência, a vazão é a mesma.** Com delay 0 e uma única thread por vez
  (`max-concurrent = 1`), C já atinge 1456 req/s, praticamente o mesmo patamar.

Assim, acima de ~16 requisições simultâneas o limite deixa de ser a espera de 10 ms e passa a ser
o custo de CPU de cada requisição no cliente: criar a thread, abrir e fechar uma conexão TCP,
serializar o JSON. Na medição de CPU, o cliente usou ~140% de CPU e gastou
~1 ms de CPU por requisição (usuário + sistema), a maior parte em modo sistema (criação de threads
e chamadas de socket). O servidor gastou bem menos, 0,3 a 0,4 ms de CPU por requisição, o que
indica o cliente como o lado que satura primeiro. A alta proporção de tempo de sistema pode ter
influência do WSL2, mas isso não foi isolado neste experimento.

**C2 (dois servidores) ≈ C.** Como o gargalo é o cliente e os dois servidores rodam na mesma
máquina, distribuir as requisições entre dois servidores não mudou o resultado. Em todas as
combinações de N e delay, a diferença entre as médias de C e C2 foi menor que o maior dos dois
desvios padrão. O teste mostra que o cliente MT funciona com mais de um servidor, mas não
mostra ganho. Ganho só seria esperado com servidores em máquinas diferentes e o servidor como
gargalo.

**Custo de conexões.** Todas as configurações abrem uma conexão TCP por requisição (decisão do
experimento, para isolar o efeito das threads). Isso explica a maior parte do ~0,3 ms por
requisição em A com delay 0, em que o processamento em si é desprezível. Reutilizar conexões
reduziria esse custo, mas mudaria a comparação.

**Limitações.** Cliente e servidor dividiram a mesma máquina (12 núcleos lógicos, via loopback),
então não há latência de rede real. O delay é um `sleep`, não um banco de verdade. Os resultados
valem para CPython com GIL; em uma implementação sem GIL o caso CPU-bound poderia ser diferente.
O desvio padrão do tempo total ficou abaixo de 5% da média em A e B em todas as combinações.
As configurações com cliente MT variaram mais (de 5% a 10% em vários casos; 18% em C com
delay 10 ms e N = 100, em que o tempo total é de só ~0,08 s), o que é esperado com o escalonamento
de dezenas de threads. Nenhuma dessas variações muda as conclusões, porque as diferenças entre
as configurações são muito maiores que o desvio.

## 7. Conclusão

O multithreading compensou quando as requisições passam a maior parte do tempo esperando I/O.
Com 10 ms de espera simulada no servidor, cliente e servidor multithread (C) foram mais rápidos
que a versão single-threaded (A): ~13× com N = 100, ~17× com N = 1000 e ~18× com N = 5000. Não
houve nenhuma requisição perdida e as respostas foram idênticas. Quando o trabalho é só CPU e muito curto, as threads pioraram o desempenho (até ~2,3×
mais lento), por causa do GIL e do custo de criar uma thread e uma conexão por requisição.
Multithreading só no servidor (B) não trouxe ganho, porque um cliente sequencial nunca envia
requisições simultâneas. Neste ambiente, o limite da configuração C (~1600 req/s) foi o custo
por requisição no próprio cliente, não o servidor nem o limite de 64 threads do semáforo: em
média, só ~20 requisições chegaram a ficar em voo ao mesmo tempo.
