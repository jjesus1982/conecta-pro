# Arsenal — página operacional (1 página)

**O que roda, quando, e como ler.** As lições e a história estão em `docs/ARSENAL_SKILLS.md`;
esta página é só operação. `backend/scripts/qa/checar_arsenal.py` confere as duas contra o disco.

## O que roda sozinho

| Quando | O quê | Onde ler |
|---|---|---|
| 00:00 (cron do host) | `scripts/oraculos_diarios.sh` → varredura dos oráculos `test_*.py` de `backend/scripts/orq/` | `/var/log/conecta-oraculos.log` |
| logo depois | `backend/scripts/qa/checar_regressao.py` → caçadores contra a linha de base + travas de sim/não | mesmo log |
| domingo, na mesma rodada | gates `fechado_*.py` e `varredura_op_acoes.py` — conta condições ✅, acusa quando CAI | mesmo log |
| beat do Celery | `orq.checar_varredura_ausente` — grita se a varredura não rodou em 30h | sino |

**Sino só recebe NOVIDADE**: vermelho novo, resolvido, oráculo que passou a bloqueado, trava que
passou a falhar ou voltou a passar. O mesmo vermelho repetido fica no log e volta ao sino na
segunda-feira. Medido em 06/09/2026: 5.387 avisos em 30 dias, 19 abertos — avisar todo dia é
o mesmo que não avisar.

## Como ler o log

```
[oraculos] 118 verdes, 2 vermelhos, 2 bloqueados, 0 não rodados em 2100s
  x test_x.py — AssertionError: …          ← VERMELHO: divergência (defeito, ou oráculo congelado)
  ? test_y.py — BLOQUEADO: LLM sem crédito  ← não deu para medir hoje; não é defeito, não é verde
  - test_z.py — não rodou (lote estourou)   ← o teto de 90min foi batido; ver "mais lentos"
[oraculos] Comparado à rodada anterior: 1 NOVO(s): test_x.py; 1 resolvido(s).
── travas mecânicas ──
  cacar_fabricacao.py: 37 (estável)         ← dívida conhecida, base em /var/lib/conecta/qa_baseline.json
  x checar_vocabulario.py: 11 -> 13 REGRESSÃO   ← código novo trouxe pista nova
  x checar_beats.py: NÃO VERIFICADO           ← a trava não respondeu; NÃO é verde
```

Três estados por oráculo, e nenhum se confunde com o outro:

| Estado | Exit | Significa |
|---|---|---|
| verde | 0 | exibido == banco |
| vermelho | ≠0, ≠3 | divergência — ou defeito de produto, ou o oráculo ficou preso a uma versão antiga |
| BLOQUEADO | 3 (`_fixtures.bloqueado`) | pré-condição ausente ou dependência externa fora; "não deu para medir" |

## Os caçadores (`backend/scripts/qa/`)

**Contados** (têm linha de base; acusam quando a dívida CRESCE):

| Caçador | Onde roda | Linha canônica | Pergunta |
|---|---|---|---|
| `cacar_fabricacao.py` | container | `N pista(s) em` | valor inventado quando a fonte falha? |
| `checar_vocabulario.py` | container | `(N crítica(s)` | lista literal que a coluna não tem? |
| `checar_varchar_teto.py` | container | `TOTAL: N coluna(s) no teto` | varchar(N) com valor encostado no teto? |
| `checar_repositorio.py` | host | `TOTAL: N` | chamada a método que o repositório não tem? |
| `checar_rotas_frontend.py` | host | `TOTAL: N` | front chamando rota que o backend não tem? |
| `checar_oraculo_externo.py` | host | `TOTAL: N` | número que ninguém de fora confirma? |
| `checar_uso_real.py` | host (delega banco ao container) | `TOTAL: N tabela(s) com 0 linhas` | quem escreve, quem chama, e quando? tabela nascida morta? |

Sem a linha canônica a rodada é **NÃO VERIFICADA**: acusa e a base não se move (foi assim que a
base caiu a 0 em 23/08 e acusou "0 → 25" por dez noites).

**Sim/não** (exit code decide; teto por trava): `checar_beats.py` (rotina agendada que não
produz), `checar_periodo_do_servidor.py` (data vinda do modelo), `checar_desmonte_comportamento.py`
(oráculo que deixa linha em produção — ~1h, só `test_*`), `checar_sucesso_vazio.py` (motor responde
200 sem frase), `checar_arsenal.py` (este documento mentindo), `checar_mcp_tools.py` (peça de
parede fora do git ou da imagem).

**Gates semanais** (condições ✅ entram na base; acusa quando o número cai): `fechado_bartolo.py`,
`fechado_contratos.py`, `fechado_fiscal.py`, `fechado_gedeon.py`, `fechado_operacional.py`,
`varredura_op_acoes.py`.

**À mão** (com argumentos): `provar_desmonte.py <oráculo> <tabela>` — prova de desmonte de um
oráculo recém-escrito. Mutação em produção: sempre via `_mutacao.Mutacao` (ensaio, `--aplicar`).

## Comandos

```bash
# rodar a rodada da noite agora (leva 1–2h; não rode com deploy em curso)
/opt/conecta-pro/scripts/oraculos_diarios.sh && tail -80 /var/log/conecta-oraculos.log

# um oráculo
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_<nome>.py

# só os caçadores contados, e aceitar a dívida atual como base (decisão vai na mensagem do commit)
python3 backend/scripts/qa/checar_regressao.py --gravar

# forçar os gates semanais
python3 backend/scripts/qa/checar_regressao.py --gates

# uso real por família (o instrumento do mapa VIVO · DESLIGADO · MORTO)
python3 backend/scripts/qa/checar_uso_real.py            # famílias
python3 backend/scripts/qa/checar_uso_real.py --tabelas  # + por tabela
python3 backend/scripts/qa/checar_uso_real.py --mortas   # só as com 0 linhas
```

## Regras que valem sempre

- Trava nova entra em `checar_regressao.py` (contada, sim/não ou gate) **ou** em `ORFAS_DECLARADAS`
  com dono e motivo. Trava que ninguém invoca reprova a rodada.
- Oráculo que não pode medir hoje chama `bloqueado("motivo")`, nunca `assert False`.
- Número em comentário leva a data em que foi medido.
- `git commit -m … -- <arquivos>`; arquivo novo exige `git add` nomeado; confira o EXIT CODE.
- Dinheiro que sai e governo: nunca happy-path. Operacional: relatório, nunca correção.
