# Validação do Backup Automático — ciclo forçado

**Data:** 2026-05-31 · **Status:** ✅ **FUNCIONA DE PONTA A PONTA** (ciclo forçado gerou dump válido).

## 1. Cron ativo
- `0 3 * * * ...backup_database.sh` (com alerta Telegram — hardening da Frente 1) + `30 3 * * * ...backup_retention.sh`.
- cron daemon: **active**. Script: `/opt/conecta-pro/scripts/backup_database.sh` (pg_dump via docker exec + timeout 600 + integridade + retenção).

## 2. SSH PasswordAuthentication
- **`passwordauthentication = yes`** ✅ (conforme decisão do Jordan: manter senha+chave). PermitRootLogin yes, PubkeyAuthentication yes. **Nenhum hardening deixou 'no'.** (Apenas reportado — não alterei.)

## 3-4. Ciclo forçado AGORA (sem esperar o cron)
- Executei o script manualmente → **"BACKUP CONCLUÍDO COM SUCESSO"**.
- Dump gerado: **`/opt/conecta-pro/backups/postgresql/backup_20260531_023825.sql.gz`**
  - Tamanho: **1.8M (1.798.857 bytes, >0 ✓)**
  - Integridade: `gunzip -t` → **GZIP VÁLIDO**
  - Conteúdo: `-- PostgreSQL database dump` → **SQL VÁLIDO** · 75.848 linhas · **525 CREATE TABLE**
  - *(Formato = `pg_dump plain | gzip`. `pg_restore --list` não se aplica a este formato — é para dumps custom `.dump`; a validação correta aqui é gunzip -t + conteúdo.)*

## 5. Rotação / retenção / espaço
- **11 dumps** automáticos (timeline 03/mai → 31/mai). Mais antigo: 27 dias (dentro da retenção de 30 dias).
- Retenção: `RETENTION_DAYS=30` (backup_database.sh deleta >30d) + `backup_retention.sh` (7 diários + 4 semanais).
- Espaço: backups usam **21M**; disco com **317G livres (19% usado)** ✅.
- *(Obs: há um gap histórico 21–29/mai — a crise de dockerd-hang já corrigida na Frente 1. De 30/mai em diante volta a rodar diário, comprovado por este ciclo forçado.)*

## 6. Backup externo (offsite)
- ⚠️ **DESABILITADO** — rclone não instalado, S3 não configurado (log do backup: "Backup offsite desabilitado"). Backups são **só locais** (mesmo disco do VPS).
- **Pendência:** para 3-2-1 real, configurar `rclone config` (remote `offsite:`) ou confirmar snapshots no painel Hostinger (não verificável por CLI).

## Resposta direta
| Item | Resultado |
|---|---|
| Cron ativo? | ✅ SIM |
| Dump forçado gerou arquivo válido? | ✅ SIM (1.8M, gzip íntegro, 525 tabelas) |
| Tamanho >0? | ✅ 1.798.857 bytes |
| Rotação OK? | ✅ 30 dias + 7/4 semanal |
| Espaço OK? | ✅ 317G livres |
| PasswordAuthentication | ✅ yes (decisão do Jordan) |
| Offsite | ⚠️ desabilitado (pendência) |
