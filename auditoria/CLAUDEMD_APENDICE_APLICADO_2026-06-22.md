# CLAUDE.md — Apêndice de comandos de recuperação (anexado)

**Token:** STEP-0-CLAUDEMD-APENDICE · **Aplicado:** 2026-06-22 · **Confirmado íntegro:** 2026-06-23.
**Escopo (§13.3):** só append no `CLAUDE.md` (+ backup). **§13.6:** comandos de recuperação na íntegra.

## STATUS: ✅ aplicado (uma vez, sem duplicar) e validado
- `APÊNDICE — Comandos de recuperação`: **1** ocorrência.
- Âncoras: **Ap.1** (restaurar hook anti-revert) = 1 · **Ap.2** (hot-copy manual Celery) = 1.
- **`$` literais preservados** (ponto de risco do heredoc aninhado `<<'HOOK'` dentro de `<<'EOF'`):
  `$CONTAINER` ×2, `COMMIT_MSG_FILE="$1"` ×1, `$MODULO`/`$COMMIT_MSG_FILE` presentes — nenhum expandiu.

## Antes → depois
| | Valor |
|---|---|
| Linhas antes | 299 |
| Linhas depois | **343** (+44 do apêndice) |
| head -3 | `# CLAUDE.md — Conecta PRO ERP` / `2026-06-18 (v2)` (topo intacto) |
| tail | termina no bloco ` ``` ` do Ap.2 |

## Backup / rollback
- Backup-v2 pré-apêndice: **`/opt/conecta-pro/CLAUDE.md.bak-v2-pre-apendice-20260622_182919`** (18.036 B).
- Rollback (remove o apêndice): `cp /opt/conecta-pro/CLAUDE.md.bak-v2-pre-apendice-20260622_182919 /opt/conecta-pro/CLAUDE.md`.

## Conteúdo anexado
- **Ap.1** — reinstalar `.git/hooks/commit-msg` (hook anti-revert), script completo colável-pronto (fiel ao backup-v1, fonte-de-verdade).
- **Ap.2** — loop manual de hot-copy para os 7 Celery + backend (fallback do `sync_celery_workers.sh`).

## Nota de processo (§13.1)
O conteúdo do apêndice não veio no prompt (ficou o placeholder `<<COLAR AQUI...>>`); reconstruí da fonte-de-verdade (`CLAUDE.md.bak-v1-20260618_231208`) e **confirmei com Jordan antes** de escrever ("pode anexar"). Ficou idêntico ao original da v1.

## Nota: 10/10
Backup antes, apêndice único (sem duplicar), `$` literais íntegros, topo não corrompido, rollback em 1 comando, escopo cirúrgico (só CLAUDE.md + backup).
