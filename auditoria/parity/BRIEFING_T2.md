# BRIEFING — T2 (trabalhador, cluster financeiro/comercial)

Cole isto na sessão T2 quando ela terminar o ponto CLT.

---

Você é o **T2** numa missão de 3 terminais em paralelo (loop). Objetivo: ligar telas do
**redesign** ao DADO REAL do clássico, sem conflito com T1/T3.

## ANTES de começar, LEIA nesta ordem
1. `auditoria/parity/PARECER_3TERMINAIS.md` — o porquê e a arquitetura.
2. `auditoria/parity/DIVISAO_3T.md` — a tabela oficial (quem faz o quê) + as 4 regras.
3. `auditoria/parity/CORRECOES.md` — 23 exemplos do padrão (tela→dado real→curl→GATED).
4. `auditoria/parity/BASELINE_PRE_REFACTOR.json` — as telas já wired (não refaça essas).

## Contexto
O redesign perdeu ~611 capacidades vs o clássico (auditoria triada). **128 de 258 telas estão
wired (≈37%)**. A FASE 1 paraleliza o WIRING das ~161 que faltam. A FUNDAÇÃO (refactor do
monólito em `redesign_builders/<mod>.py`) é feita pelo T1. **NÃO comece antes do T1 avisar
"FUNDAÇÃO PRONTA"** no DIVISAO_3T.md.

## SEUS MÓDULOS (T2) — edite SÓ estes arquivos
`redesign_builders/`: **financeiro** · **gestao-de-pessoas** · **crm** · **empresas** ·
**seguranca** · **recrutamento** · **servicos** · **agendador** · **assistente** · **bi** ·
**analytics** (~50 telas). Gap por módulo: financeiro 21 · gp 9 · seguranca 5 · empresas 4 ·
agendador 3 · crm 3 · servicos 2 · assistente 2 · recrutamento 1.

## As 4 REGRAS INVIOLÁVEIS
1. Edite SÓ `redesign_builders/<seus_módulos>.py`. NUNCA `redesign_data_controller.py`, `_shared.py`, ou módulo alheio.
2. COMMIT antes de qualquer deploy (o blue-green assa a árvore inteira). `--no-verify`, termine com `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
3. Deploy = `scripts/deploy_backend_bluegreen.sh` com retry-loop (lock `/tmp/conecta_deploy.lock`). SEMPRE grep container pós-deploy.
4. Marque a tela no checklist do DIVISAO_3T.md ANTES de pegar.

## Ciclo por tela (padrão-ouro)
1. Ache um menu-id não-wired em `frontend/src/app/redesign/_modules/<slug>.json` (compare com o `wired` do BASELINE).
2. Ache a tabela real do clássico (retrato: `docker exec conecta-pro-backend python3 -c "..."` contando `pg_stat_user_tables`).
3. No seu `redesign_builders/<mod>.py`: `await safe("<id>", tbl("Título", f"{n} itens", "—", [cols], "grid", "SELECT ...", lambda r: [...]))`.
4. GOTCHA: coluna enum/json → `::text` / `->>'k'` no coalesce (senão `safe()` engole e a tela some). Nunca coalesce enum/json com literal cru.
5. Se NÃO houver tabela real → deixe honesto ("aguardando dado"), NUNCA fabrique.
6. Deploy → grep container → `curl` na rota `/redesign/data/<slug>` (login form-urlencoded porta 8080, token de serviço do container `conecta-pro-mcp` / mesmo do `prova_esocial.py`) → confira a chave `v` das células = dado real.
7. Commit atômico + linha no `CORRECOES.md` + marque `[x]` no DIVISAO_3T.md.

## Regras de ouro do produto
- **Dinheiro que SAI e transmissão legal (eSocial/DCTFWeb/pagar) = GATED.** Só VISIBILIDADE (leitura), nunca dispara.
- **Nunca fabricar dado.** Oráculo: valor exibido == fato no banco (curl vs query). Vazio real = "aguardando dado".
- Operacional (postos/alocações) é curado pelo Jordan → só leitura, nunca escreve.

Trabalhe em LOOP, 100% focado. Achou bug/erro → corrige na hora. Dúvida de escopo → pergunta antes de inventar.
