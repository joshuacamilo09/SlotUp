# Benchmark do CSP

Média de 20 cenários aleatórios por tamanho (sementes fixas). BT = backtracking simples; FC = forward checking; MRV = menor domínio primeiro.

### A) Melhor solução (branch and bound), cenários com solução

| Atividades | BT | BT+FC | BT+MRV | BT+FC+MRV |
|---:|---:|---:|---:|---:|
| 3 | 105 nós · 0.1 ms | 21 nós · 0.1 ms | 105 nós · 0.1 ms | 21 nós · 0.2 ms |
| 4 | 1 270 nós · 1.5 ms | 116 nós · 0.8 ms | 1 086 nós · 1.5 ms | 62 nós · 0.7 ms |
| 5 | 12 053 nós · 17.4 ms | 404 nós · 2.8 ms | 12 625 nós · 19.8 ms | 124 nós · 1.5 ms |
| 6 | 58 292 nós · 90.4 ms * | 715 nós · 6.7 ms | 55 968 nós · 95.7 ms * | 452 nós · 6.0 ms |
| 7 | 123 810 nós · 127.2 ms * | 8 438 nós · 70.0 ms | 92 904 nós · 125.7 ms * | 3 755 nós · 42.2 ms |
| 8 | 142 983 nós · 157.1 ms * | 15 909 nós · 150.4 ms | 128 178 nós · 170.3 ms * | 3 514 nós · 52.6 ms |

### B) Provar que não há solução (vagas muito ocupadas)

| Atividades | BT | BT+FC | BT+MRV | BT+FC+MRV |
|---:|---:|---:|---:|---:|
| 3 | 1 232 nós · 1.9 ms | 9 nós · 0.1 ms | 1 232 nós · 1.9 ms | 9 nós · 0.1 ms |
| 4 | 11 646 nós · 19.0 ms | 9 nós · 0.1 ms | 13 475 nós · 21.1 ms | 18 nós · 0.1 ms |
| 5 | 96 371 nós · 162.1 ms * | 9 nós · 0.1 ms | 95 495 nós · 152.5 ms * | 17 nós · 0.1 ms |
| 6 | 146 070 nós · 241.7 ms * | 9 nós · 0.1 ms | 145 882 nós · 246.0 ms * | 17 nós · 0.2 ms |
| 7 | 150 011 nós · 161.0 ms * | 9 nós · 0.1 ms | 128 943 nós · 188.7 ms * | 17 nós · 0.2 ms |

\* algum cenário atingiu o limite de 200 000 nós: a média real é maior.
