# Substituição do CLAUDE.md (v1 → v2) — aplicada e validada

**Data:** 2026-06-18 · **Token:** STEP-0-CLAUDEMD-V2-APPLY · **Escopo:** cirúrgico — só `CLAUDE.md` (+ backup + diff). Nenhum outro arquivo tocado.

---

## RESULTADO: ✅ aplicada com segurança
`/opt/conecta-pro/CLAUDE.md` agora é a **v2** (2026-06-18, 299 linhas, 18.036 bytes). Backup da v1 criado. Diff conferido. Validação OK. Rollback documentado.

## STEP 0 — Estado verificado
- `CLAUDE.md` (v1, 14.767 B, 05/mai) + `CLAUDE.md.v2` (18.036 B, **hoje 23:10**, **299 linhas**).
- v2 íntegra: começa com `# CLAUDE.md — Conecta PRO ERP` / `2026-06-18 (v2)` / branch `fix/crm-qa-aprovado-20260614`; termina com nota de preservação. Sem lixo/HTML/truncamento.

## STEP 1 — Backup (rollback)
- **`/opt/conecta-pro/CLAUDE.md.bak-v1-20260618_231208`** — md5 idêntico à v1 (`46369243…`).
- Rollback: `cp /opt/conecta-pro/CLAUDE.md.bak-v1-20260618_231208 /opt/conecta-pro/CLAUDE.md`.

## STEP 2 — Diff (revisão)
- Diff completo salvo: **`auditoria/DIFF_CLAUDEMD_V1_V2_2026-06-18.txt`** (662 linhas).
- É uma **reescrita quase total** (substituição, não patch incremental).

### O que SAI (v1) × o que ENTRA (v2)
**SAI (descartado por ser falso/perigoso/incompleto):**
- Tabela "todos os módulos 10/10 ✅" (aspiracional/falsa).
- **Senha literal** no comando de token (`JsJ…`).
- Narrativa "ciclo agentes 30min, score 10.0/10".
- Status "branch feature/people-management-reorganization" (desatualizado).

**ENTRA (v2):**
- **CAMADA A — PRINCÍPIOS §13.1–§13.7:** pense antes de codar/Chesterton, simplicidade, mudanças cirúrgicas, execução guiada por objetivo/falsificação, dado real nunca simular, documentar antes/nunca destruir, **STEP 0 obrigatório**.
- **CAMADA B — OPERAÇÃO:** identidade; auth sem senha literal (`ADMIN_PASSWORD` por env); **B.3 três caminhos de deploy** (hot-copy / frontend script / rebuild manual) + **B.3.4 compose canônico**; B.4 hot-copy p/ todos Celery; B.5 ChunkLoadError; **B.6 zonas proibidas com override por missão**; **B.7 durabilidade** (env_file + rede); B.8 governança; **B.9 estado REAL medido**; **B.10 features novas (José Luís + Campo OS)**; **B.11 80 agentes existem mas MOTOR QUARENTENADO**; B.12 infra-notas.

### Seções de VALOR preservadas (não se perderam — foram reestruturadas)
ChunkLoadError (×4), `deploy_frontend.sh` (×2), `sync_celery_workers.sh` (×2), celery (×16), `kill -HUP` (×2), zonas proibidas (×2), `git revert` (×4). Os headers v1 "REGRA CRÍTICA DEPLOY/HOT-COPY" sumiram, mas o conteúdo migrou para B.4/B.5.

### Único ponto checado antes de trocar (resolvido)
- `REVERT BLOQUEADO` = 0 na v2 → **não é perda crítica**: o hook anti-revert **está instalado e ativo** em `.git/hooks/commit-msg` (independe do CLAUDE.md); a v2 documenta o hook + a regra (B.8 l.223); o script de restauração verboso fica no backup-v1. Condição STEP 3.1 satisfeita → prosseguido.

## STEP 3 — Substituição
- `cp CLAUDE.md.v2 → CLAUDE.md`. md5 do ativo == v2 (`2a4b8f58…`). head: `2026-06-18 (v2)`. wc: 299 linhas.

## STEP 4 — Validação de integridade
| Checagem | Resultado |
|---|---|
| §13.1 / §13.7 | ✅ presentes |
| compose canônico | ✅ ×2 |
| José Luís | ✅ ×2 |
| MOTOR QUARENTENADO | ✅ ×1 |
| **Senha literal (`JsJ`/`password=Js`)** | ✅ **AUSENTE (0)** |

## STEP 5 — Rollback & arquivos
- Ativo: `/opt/conecta-pro/CLAUDE.md` = v2.
- Backup-v1: `/opt/conecta-pro/CLAUDE.md.bak-v1-20260618_231208` (rollback 1 comando).
- `CLAUDE.md.v2` ainda existe (cópia idêntica ao ativo). **Sugestão (não decidido):** pode remover a `.v2` agora que o conteúdo é o oficial — ou manter como referência. **Sua decisão.**
- Backups antigos preexistentes (`CLAUDE.md.backup`, `.backup-20260111…`) não foram tocados.

## NOTA: 10/10
Backup antes, diff conferido, perda potencial (hook anti-revert) investigada e descartada com evidência, substituição limpa (md5 match), validação positiva (seções presentes + senha ausente), rollback documentado, escopo cirúrgico (só CLAUDE.md). Zero efeito colateral.
