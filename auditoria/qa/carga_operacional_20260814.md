# Carga — Operacional · 14/08/2026, 18h50 (sexta)

Rodado **contra produção**, com gente usando. O teste foi desenhado para parar antes de
atrapalhar, não para achar o limite a qualquer custo.

```bash
export QA_TOKEN=...
python3 scripts/qa_carga_operacional.py
```

## Contexto de escala — sem isso, número de carga não decide nada

```
75 usuários ativos no cadastro
53 funcionários ativos (app de ponto)
 9 batidas na hora anterior ao teste
```

Pico realista de uso simultâneo do redesign: **bem abaixo de 20**. É a régua que
interessa, não o limite teórico da máquina.

## Resultado

Todas as rampas: **1 → 2 → 5 → 10 → 20 simultâneos**, 20 requisições por degrau.

| endpoint | 1 req | p50 @20 | p95 @20 | vazão | erros 5xx |
|---|---:|---:|---:|---:|---:|
| `/redesign/data/operacional` (~100 telas) | 487 ms | 1.699 ms | 2.862 ms | ~10 req/s | **0** |
| `/operacional/presenca/hoje` | 30 ms | 352 ms | 458 ms | ~67 req/s | **0** |
| `/operacional/dashboard/` | 50 ms | 292 ms | 528 ms | ~71 req/s | **0** |

**Zero erro 5xx em qualquer degrau.** Memória do backend: 3,95 GiB de teto 6, com pico
momentâneo de 4,48 — nunca perto do corte de segurança (5,2).

## Carga sustentada — o teste que importa mais

10 simultâneos por 60 segundos contra o endpoint mais caro:

```
+15s  n= 73  p50=1299ms  p95=4061ms  mem=3.95GiB  erros=0
+31s  n=109  p50=1342ms  p95=2435ms  mem=3.95GiB  erros=0
+47s  n= 98  p50=1276ms  p95=4580ms  mem=4.19GiB  erros=0
memória final: 3,95 GiB — voltou à linha de base
```

p50 **plano** ao longo do minuto e memória que volta ao ponto de partida: não há
vazamento nem esgotamento de pool de conexão. Era o risco real, e não se confirmou.

## O que os números dizem de verdade

**Capacidade não é problema neste porte.** Com 75 usuários e pico realista abaixo de 20
simultâneos, ~10 req/s no endpoint mais pesado sobra.

**O achado não é carga, é latência de UM usuário.** O dispatcher leva **487 ms para uma
única requisição sem concorrência nenhuma** — ele monta ~100 telas de uma vez. Isso é o
que o gerente sente ao abrir o módulo, sozinho, às 3 da manhã. Se algum dia doer, o
caminho é montar sob demanda a tela pedida em vez das 100, não comprar máquina.

## ⛔ O que NÃO foi testado, de propósito

**O caminho de escrita do ponto.** É o que não pode falhar numa troca de turno, e testá-lo
significaria gravar batida falsa em produção. Ficou fora.

Vale a conta, porém: 53 funcionários batendo numa troca de turno espalhada em alguns
minutos dá **menos de 1 req/s**. Três ordens de grandeza abaixo do que o sistema
aguentou lendo. Carga não é o risco do ponto — geocerca e facial são, e esses já foram
medidos em separado.

## Também não coberto

- Limite superior real (parei em 20; não há motivo para achar o ponto de ruptura de uma
  operação de 75 pessoas às 18h de sexta).
- Carga sobre banco de dados isolada do backend.
- Pico de eSocial/fiscal concorrendo com o operacional.
- Frontend sob carga (medi API; o navegador tem o próprio custo de render).

## Correção de rumo

A primeira rodada acusou `/operacional/dashboard` como **404**. Era erro meu: a rota real
tem barra no fim (`/operacional/dashboard/`). Com o caminho certo ela responde em 50 ms e
sustenta ~71 req/s.
