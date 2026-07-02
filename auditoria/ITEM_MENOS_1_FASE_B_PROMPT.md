# ITEM −1 · FASE B — CONSOLIDAÇÃO (máquina de estados linear com checkpoints + abort/rollback)
**Token:** STEP-0-ITEM-MENOS-1-CONSOLIDA · **Pré-req:** `ITEM_MENOS_1_DIAG_2026-07-01.md` aprovado por Jordan.
**⚠️ Esta fase ESCREVE** (repointa chamadores, quarentena código morto). Backup + bake + §13.6 obrigatórios. NÃO deleta nada (§13.6 = quarentena).
**Forma:** NÃO é loop. É sequência linear STEP 0→1→2→3→4 com **gates-checkpoint** e **ramo de falha = reverter+parar** (não re-iterar) — porque é operação destrutiva; re-iterar pra forçar verde numa mutação é como cavar buraco. Roda **só após o aval** e respeitando as ELEIÇÕES.

---

## ELEIÇÕES (defaults recomendados — Jordan confirma/ajusta antes)
| Decisão | Default | Por quê (evidência FASE A) |
|---|---|---|
| **Motor de folha exibido** | **M1 `calculo_service`** (`/folha/*`, lê Domínio) | único que defere ao golden set; não recalcula com tabela defasada |
| **`/payroll/*` (M3→M2)** | reduzir a **conferência/export**, não fonte exibida | recalcula com tabela 2024 rotulada 2026 |
| **`clt_calculator` (M2)** | **MANTER** — corrigir tabelas via item −0.5 | biblioteca legal (rescisão/férias/13º); matar = perder cálculo legal |
| **`GPEventBus`** | **MANTER o alias** | é alias de `ConectaEventBus` vivo; deletar quebra `handlers/base_agent/gp_websocket` |
| **MessageBus** | **quarentenar** | nada fora de `events.py` consome; nenhum `.start()` no boot |
| **`gp.*` EventTypes + agents órfãos** | **quarentenar juntos** | `gp.*` só usado por `ops_agent` órfão (orchestrator não sobe no boot) |

## PRINCÍPIOS (CLAUDE.md v2 §13)
§13.6 Quarentena, não delete (reversível por item). §13.3 Cirúrgico (só motores/buses de GP; não tocar payload — é Fase 1). §13.5 Dado real (gate = query/rota/boot). §13.1 **Chesterton no ATO, não só no diagnóstico** (re-provar precondição no momento da escrita). §B.6 Bake durável.

## INVARIANTE DA FASE — precondição re-provada no cut-time
> O estado mudou desde a FASE A. **Todo STEP que escreve re-prova sua precondição no instante da execução** (grep/boot frescos), nunca confia no que o diagnóstico disse dias atrás. Vale p/ 0.1, 1.1, 1.4, 2.x.

---

## STEP 0 — ESTADO LIMPO + BLINDAGEM (cirúrgico, antes de escrever 1 linha)

### 0.1 CATEGORIZAR o tree por NATUREZA (nunca tratar como bloco único)
```
0.1.a — Fotografar o estado REAL (não confiar em "356", pode ter mudado):
        git status --short > /tmp/tree_snap.txt ; wc -l /tmp/tree_snap.txt

0.1.b — SEGREDO por CONTEÚDO, não por nome (nome erra .pfx/.p12 e dá falso-positivo em token_service.py):
        # reusar o que o repo JÁ tem (Chesterton): detect-secrets + gitleaks no CONTEÚDO do diff
        detect-secrets scan --baseline .secrets.baseline 2>/dev/null || true
        git diff --staged --no-color | gitleaks detect --pipe 2>/dev/null || true
        # + suplemento por extensão de credencial (não substitui o scan de conteúdo):
        grep -iE "\.(pfx|p12|pem|key|env|crt)($|/)|webhook_secret|credential" /tmp/tree_snap.txt

0.1.c — CLASSIFICAR em 4 baldes COM PRECEDÊNCIA (um arquivo entra em UM só, nesta ordem):
        BALDE 3 SEGREDO   (precede tudo): qualquer hit de 0.1.b
        BALDE 2 CÓDIGO-FOLHA (perigoso): grep "\.py$" | grep -iE "model|calcul|payroll|folha|inss|fgts|values_callable"
        BALDE 1 LIXO         : agents/cto/.*(snapshots|predicao)/.*\.json
        BALDE 4 RESTO        : o que sobrou
        # Precedência: SEGREDO ganha sempre; depois código-folha; depois lixo; resto por último.

0.1.d — GATE HUMANO: se BALDE 3 (segredo) OU BALDE 2 (código-folha) ≠ vazio → PARAR e reportar a Jordan.
        Não prosseguir no automático com segredo ou código de folha solto no tree.

0.1.e — TRATAMENTO por balde + ESTADO GIT (o comando muda se é tracked/untracked/deleted):
        BALDE 3 SEGREDO:
          - tracked   → git rm --cached <arq> + add ao .gitignore
          - untracked → só .gitignore + mover p/ fora do repo (uploads/ 600), NÃO git rm (falha em untracked)
          - se for segredo REAL exposto → AVISAR Jordan p/ ROTACIONAR. Nunca stash, nunca commit.
        BALDE 2 CÓDIGO-FOLHA (decisão consciente de Jordan, NÃO stash cego):
          - verificar se JÁ está em produção: o container roda com values_callable? (comparar com a imagem)
          - se SIM (fix validado pendente) → commit ISOLADO numa branch própria (wip/models-values-callable),
            mensagem própria, ANTES da consolidação. NÃO misturar no commit da FASE B.
          - se NÃO (divergência não-testada) → **branch WIP durável** (git branch wip/models-NAO-TESTADO + guardar),
            NÃO stash (stash some/invisível). Tratar como item próprio DEPOIS da FASE B.
        BALDE 1 LIXO: decidir se a deleção é intencional (git commit da deleção em branch de limpeza)
                      ou acidental (git checkout -- <paths> restaura). NÃO stashar deleção.
        BALDE 4 RESTO: git stash push -m "residuo-diversos-<data>" -- <paths>.

0.1.f — MANIFESTO DE CUSTÓDIA (anti "sumiu"): escrever
        /opt/conecta-pro/auditoria/TREE_CLEANUP_MANIFEST_<data>.md com cada path → destino
        (branch X / stash Y / gitignore / mantido). RECONCILIAR: todo arquivo do snap 0.1.a
        aparece em exatamente 1 destino. Nada silenciosamente perdido.

0.1.g — Confirmar tree limpo: git status --short (só o que Jordan decidiu manter). Reportar antes→depois.
```
### 0.2–0.5 Blindagem
```
0.2 git checkout -b item-1/consolidacao-arquitetura-<data>   (a partir do tree já limpo)
0.3 BACKUP: pg_dump -Fc (mesmo sem migration). Anotar caminho.
0.4 Âncora: docker tag <imagem-backend-atual> pre-item1-<data>
0.5 Baseline da suíte ANTES: guardar passes/falhas p/ comparar no fim.
```

## STEP 1 — MOTOR ÚNICO DE FOLHA (migrar chamadores vivos ANTES de reduzir o perdedor)
```
1.1 RE-GREP fresco (cut-time) dos chamadores de M3 /payroll:
      hr/controllers/payroll_controller.py:137 · payroll_export_controller.py:47,101,149  (confirmar AGORA)
1.2 Por chamador (conforme eleição): tela que EXIBE folha → repontar p/ M1 (lê Domínio);
    export/conferência → manter M3 rotulado "recálculo/conferência", NÃO fonte exibida.
1.3 GATE MOTOR (inforjável — "dois endpoints, um valor"):
      mesmo funcionário+competência: GET /folha/... e a tela consolidada retornam o MESMO
      líquido/INSS/FGTS (o da Domínio). Prova: 2 curls, valor igual. Se ≠ → reverter 1.2, parar.

1.4 QUARENTENAR M4 (dp_agent.PayrollSkill) e M5 (hr/skills payroll_skill) — RE-PROVAR orfandade AGORA:
    1.4.a Re-grep de chamador vivo, estado atual (LITERAL):
        grep -rn "PayrollSkill\|payroll_skill" backend/ frontend/ --include=*.py --include=*.ts --include=*.tsx \
          | grep -v "_quarentena\|test\|register_skill\|class PayrollSkill\|def __"
    1.4.b DINÂMICO (grep literal é necessário, NÃO suficiente):
        grep -rn "\"PAYROLL\"\|'PAYROLL'\|get_skill\|importlib\|getattr(.*[Ss]kill" backend/ --include=*.py \
          | grep -v "_quarentena\|test"
    1.4.c GATE ORFANDADE (inforjável, cut-time): 1.4.a E 1.4.b VAZIOS → órfão confirmado AGORA.
          Qualquer chamador vivo (literal ou dinâmico) → NÃO é órfão → PARAR, reportar quem chama.
    1.4.d MOVER p/ _quarentena/ (não só marcar — o move torna a orfandade PROVÁVEL). §13.6, reversível.
    1.4.e GATE PÓS-QUARENTENA (boot ≠ runtime): configure_mappers + boot limpo + suíte==baseline
          + EXERCITAR as rotas que poderiam carregar M4/M5 por lazy-import (não só subir o boot).
          Se quebrar → a quarentena tocou algo vivo → reverter SÓ este item (§ Ramo de Falha) + reportar.
```

## STEP 2 — EVENT-BUS ÚNICO (sem matar o alias vivo)
```
2.1 ConectaEventBus é o eleito (já vivo; GEDEON registra no boot — main_production.py:113).
2.2 GPEventBus: MANTER o alias (core/events/__init__.py:11). NÃO deletar. (Reapontar imports p/ o nome
    canônico só se Jordan pedir; se sim, handlers.py:6/base_agent.py:22/gp_websocket.py:11 primeiro, boot tem que subir.)
2.3 MessageBus: re-confirmar consumer vivo==0 AGORA (cut-time), então quarentenar infra/message_bus/
    e os publish de events.py:249,286,323 (rotear p/ ConectaEventBus caso a caso se algum for útil).
    GATE: boot sobe sem MessageBus; grep consumer vivo==0.
2.4 EventTypes: eleger `dp.*` (infra/event_bus/bus.py). Quarentenar `core/events/event_types.py` (`gp.*`)
    JUNTO com o ops_agent órfão que o usa. GATE: grep uso vivo de `gp.*`==0 após quarentenar os agents.
2.5 GATE BUS (inforjável): publicar 1 evento ZZE2E real → traço aparece SÓ no ConectaEventBus (Redis
    Streams) e GEDEON registra consumo. Nenhum evento no MessageBus.
```

## STEP 3 — VERIFICAÇÃO (boot + suíte = oráculo)
```
3.1 configure_mappers() efêmero sem erro após as quarentenas.
3.2 Boot limpo (lifespan sobe, GEDEON registra subscribers, sem ImportError).
3.3 Suíte == baseline (0.5). Zero regressão nova; falhas pré-existentes documentadas.
3.4 GATE MOTOR (1.3) e GATE BUS (2.5) verdes, com evidência (curl/query/log).
3.5 Syncs 24/7 intactos (Tangerino, Domínio, GEDEON cron).
```

## STEP 4 — BAKE DURÁVEL + RELATÓRIO
```
4.1 Bake: docker compose build backend + up -d --no-deps (imagem assada, não docker cp). Âncora pós.
4.2 GATE PÓS-BAKE: boot + os 2 gates continuam verdes DEPOIS do recreate (senão a correção evaporou).
4.3 Relatório /opt/conecta-pro/auditoria/ITEM_MENOS_1_FASE_B_<data>.md: repontados + quarentenados (com caminho);
    prova de cada gate; manifesto de custódia (STEP 0.1.f); suíte antes/depois; syncs ok;
    o que ficou p/ item −0.5 (tabelas 2026) e Fase 1 (payload); rollback; Nota 0-10.
```

## RAMO DE FALHA (não re-itera — reverte, do mais cirúrgico ao último recurso)
```
1º (cirúrgico)   — Gate de um STEP reprova → REVERTER SÓ AQUELE item (quarentena/repoint é reversível)
                   → PARAR → reportar a Jordan. NÃO jogar fora os STEPs já verdes.
2º (último recurso) — Tree corrompido / múltiplos itens quebrados → rollback FULL pela âncora pre-item1
                   + branch descartada + pg_restore se preciso.
Nunca: re-iterar a mutação tentando forçar o gate a ficar verde.
```

## GATES HUMANOS (checkpoints)
- **Antes do STEP 1:** Jordan aprova as ELEIÇÕES. + GATE do 0.1.d (para se houver segredo/código-folha).
- **Após 1.3 e 2.5:** Jordan vê a prova dos 2 gates inforjáveis ("dois endpoints, um valor"; "traço só no bus eleito").
- **Antes do bake (4.1):** Jordan confere boot + suíte + syncs verdes.

## FORA DO ESCOPO (registrado, não executado aqui)
- **Item −0.5:** tabelas 2026 do `clt_calculator` (referência legal certificada + assinatura humana).
- **Fase 1/A1:** payload das arestas GEDEON (`name`→`funcionario_nome`, `nome`, `tipo`→`motivo`) + garantir `cliente_id` (revive o hub GEDEON; é módulo, não arquitetura).

---
**Resumo:** executa o mapa do DIAG, sequência linear com abort. As 2 correções do Jordan (0.1 cirúrgico, re-gate de orfandade) + 4 melhorias: segredo por conteúdo (reusa detect-secrets), precedência de baldes, ramificação por estado-git, branch durável>stash, manifesto de custódia, scan dinâmico de orfandade, move>mark, falha por-item antes da âncora. Nada roda sem aval.
