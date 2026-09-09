# Arsenal — página operacional (1 página)

**O que roda, quando, e como ler.** As lições e a história estão em `docs/ARSENAL_SKILLS.md`;
esta página é só operação. `backend/scripts/qa/checar_arsenal.py` confere as duas contra o disco.

## O que roda sozinho

| Quando | O quê | Onde ler |
|---|---|---|
| 00:00 (cron do host) | `scripts/oraculos_diarios.sh` → varredura dos oráculos `test_*.py` de `backend/scripts/orq/` | `/var/log/conecta-oraculos.log` |
| logo depois | `backend/scripts/qa/checar_regressao.py` → caçadores contra a linha de base + travas de sim/não | mesmo log |
| domingo, na mesma rodada | gates `fechado_*.py` e `varredura_op_acoes.py` — conta condições ✅, acusa quando CAI | mesmo log |
| logo depois | `checar_bake_pendente.py --assar` — assa o que está por docker cp se: lock livre, 01–05h, `backend/` limpo no git, WhatsApp quieto 30 min, sem migration pendente | `/var/log/conecta-bake-auto.log` |
| beat do Celery | `orq.checar_varredura_ausente` — grita se a varredura não rodou em 30h | sino |

**Sino: corte automático.** `checar_sino_surdo` corta sozinho a origem surda há 14 medições
seguidas (gatilho `sino_corte_bi`; nunca o arsenal nem o digest) e avisa uma vez. Comandos:
`--cortar <origem>` · `--religar <origem>` · `--cortadas`.

**Leitura de tela com pessoa.** `crm_audit_log` passa a receber `GET /api/v1/redesign/data/<slug>`
(middleware) — `checar_uso_real` mostra quem abriu qual tela e quando. Vale a partir do bake.

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
| `checar_uso_real.py` | host (delega banco ao container) | `TOTAL: N tabela(s) com 0 linhas` | quem escreve, quem chama, e quando? tabela nascida morta? `--quem <email>` · `--mortas` mostra nascimento |
| `checar_sino_surdo.py` | container | `TOTAL: N origem(ns) surda(s)` | origem do sino com volume e ninguém abre? |
| `checar_llm_martelando.py` | container | `TOTAL: N origem(ns) martelando` | origem chamando o LLM em loop com <5% de sucesso nas últimas 24h? |
| `checar_nao_vigiado.py` | container (~5 min) | `TOTAL: N tela(s) sem vigia` | tela do redesign sem oráculo nem regra que a cite? |
| `checar_irreversivel.py` | host | `TOTAL: N função(ões) que disparam antes de gravar` | registro criado depois do disparo externo? |
| `checar_dominio.py` | host (banco via docker) | `TOTAL: N divergência(s) de domínio` | o código diz o que `verdades_dominio.py` diz? a verdade venceu? |
| `checar_beat_engole_falha.py` | host | `TOTAL: N task(s) que engolem falha` | beat que absorve a própria falha? (linha de base) |
| `checar_botao_morto.py` | container | `TOTAL: N botão(ões) morto(s)` | tela do redesign chamando endpoint que o app não tem? (linha de base) |
| `checar_tabela_fantasma.py` | container | `fantasmas N (U usadas · E entulho)` | modelo declara tabela que não existe? (linha de base, ~90 s) |
| `checar_cobertura_rotas.py` | host (enumera as rotas dentro do container) | `TOTAL nenhum: N · classico: M · rotas: R` (binária: 0 · 0) | rota montada sem tela no redesign e sem chamador interno? alias/externo/dono contam à parte |
| `checar_chamadas_sem_rota.py` | host (enumera as rotas dentro do container) | `TOTAL chamadas sem rota: N (alcançável pelo redesign) · M (só clássico)` (binária: N = 0) | o frontend chama rota que o backend não tem? inversa da cobertura; só clássico é dívida contada |
| `checar_fantasmas_container.py` | host (lista o container) | `TOTAL fantasmas no container: N` (binária: N = 0) | o container tem `.py` que o repositório não tem? `docker cp` não apaga — o fantasma faz as duas travas acima medirem rota que o bake vai derrubar (09/09) |
| `checar_oraculos_no_container.py` | host (lista o container) | `TOTAL instrumentos fora do container: N` (binária: N = 0) | oráculo (`scripts/orq`) ou caçador (`scripts/qa`) que está no git e não está na imagem NÃO roda — a varredura e o checar_regressao chamam de dentro do container; contar pelo disco é afirmar sobre o repositório, não sobre quem vigia (09/09) |
| `checar_import_orfao.py` | host | `OK checar_import_orfao` / `FAIL checar_import_orfao` | algum import de topo aponta para módulo apagado? (binária) |
| `checar_bake_pendente.py` | host | `TOTAL: N arquivo(s) no ar fora da imagem` | o que está por docker cp? (`--assar`: assa na madrugada se as 6 guardas passam) |

Sem a linha canônica a rodada é **NÃO VERIFICADA**: acusa e a base não se move (foi assim que a
base caiu a 0 em 23/08 e acusou "0 → 25" por dez noites).

**Sim/não** (exit code decide; teto por trava): `checar_beats.py` (rotina agendada que não
produz), `checar_periodo_do_servidor.py` (data vinda do modelo), `checar_desmonte_comportamento.py`
(oráculo que deixa linha em produção — ~1h, só `test_*`), `checar_sucesso_vazio.py` (motor responde
200 sem frase), `checar_registros_servidor.py` (registro vazio ou encolhido no processo do servidor;
memória em `system_configs`, `--aceitar` para encolhimento deliberado), `checar_arsenal.py` (este documento mentindo), `checar_mcp_tools.py` (peça de
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

## Cobertura rotas × telas (08/09/2026)
`python3 backend/scripts/qa/checar_cobertura_rotas.py [--tsv saida.tsv]` — enumera as rotas montadas dentro do container (método, path, handler) e classifica cada uma pelo chamador, nesta precedência: **redesign** (builders, `redesign_data_controller`, apps vivos: `/redesign`, `/modulos/meu-espaco`, área do cliente, assinar, homologação, painel de ponto, login, candidato, PJ, primeiro acesso) · **interna** (MCP, agents, tasks, orquestrador, serviços, core, scripts, robôs, cron, nginx — inclusive handler reusado por import ou referência) · **alias** (montagem dupla: mesmo handler já coberto) · **externo** (webhook/callback/oauth) · **dono** (`/api/v1/reimbursements/*`, decisão de 07/09) · **classico** (só `/modulos` antigo) · **nenhum**. Casa path literal, prefixo, rota com parâmetro por regex, URL montada em pedaços (constante de prefixo, concatenação implícita, `portalFetch`).
Linha canônica: `TOTAL nenhum: N · classico: M · rotas: R`. Alvo: `nenhum: 0 · classico: 0`. Série de 08/09 em `auditoria/qa/revisao_20260908/cobertura_rotas_T{0..6}.tsv`: T0 1752 · 569 · 249 → T6 **1220 · 0 · 0** (redesign 819 · interna 357 · alias 23 · externo 15 · dono 6). Leva ~1 min. Trava declarada com dono (sessão fase5) até entrar no `checar_regressao.py`; rota nova sem chamador volta a aparecer aqui no dia seguinte.
