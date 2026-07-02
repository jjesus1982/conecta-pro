# FRENTE 1 — Backup Automático: Diagnóstico + Correção (AUTÔNOMA)

**Data:** 2026-05-30
**Status:** ✅ **RESTAURADO E ENDURECIDO** — backup automático funcionando + resiliente a hang silencioso.

---

## 1. Diagnóstico (Chesterton) — por que parou ~20/mai

- O cron **existe e está ativo**: `0 3 * * * /opt/conecta-pro/scripts/backup_database.sh` (cron daemon `active`).
- Timeline real (`backups/postgresql/`): …05-17, 18, 19, **20**, **[gap 21–29]**, **30** ✅.
- **Causa-raiz:** o script faz `docker exec conecta-pro-postgres pg_dump | gzip` **sem timeout** (linha 70). Durante a crise de RAM/load (28/31 GB, load ~79, **dockerd travado** — resolvida em sessões anteriores), o `docker exec` **travou indefinidamente**. Como hang ≠ erro de saída, o **trap ERR não disparou** → falhou **silenciosamente** por 9 dias, **sem log e sem alerta**.
- **Agravante:** `BACKUP_ALERT_WEBHOOK` não configurado e `.env` é zona proibida → nenhuma notificação de falha. Por isso o gap passou despercebido.
- Com o VPS saudável (dockerd responsivo), o backup das 03:00 de **30/mai voltou a rodar sozinho** ("BACKUP CONCLUÍDO COM SUCESSO", 1.8M).
- Disco: **317 G livres** (19% usado) — não foi causa.

**Conclusão:** a causa primária (dockerd travado) já estava resolvida; restava endurecer o script contra **hang silencioso** e tornar falhas **visíveis**.

## 2. Correção aplicada (autônoma, reversível)

Backup do script: `scripts/backup_database.sh.bak-20260530_185019` · backup do crontab: `/tmp/crontab.bak-*.txt`.

1. **Timeout no pg_dump** (linha 70): `timeout 600 docker exec ... pg_dump ...`. Se o dockerd/postgres travar, estoura em 10 min → `exit≠0` → **trap dispara** (log + alerta). Acaba o hang silencioso.
2. **Alerta Telegram no trap de falha**: adicionado envio via o **mesmo bot do monitoramento** (`MONITOR_BOT_TOKEN`/`MONITOR_CHAT_ID`), passado pela linha do cron (consistente com os outros crons do projeto). Falha de backup agora **notifica no Telegram** — sem depender de `.env` (zona proibida).
3. Crontab da linha de backup atualizado para passar o token (`crontab -l` confirma).

## 3. Teste (prova)

- Execução manual do script endurecido → **`backup_20260530_185019.sql.gz` (1.8M)**, `gunzip -t` OK, conteúdo `-- PostgreSQL database dump` válido, "**BACKUP CONCLUÍDO COM SUCESSO**".
- `bash -n` no script: OK. Cron daemon: `active`. Linha do cron com alerta: confirmada.

## 4. Estado do backup (3-2-1)

| Item | Estado |
|---|---|
| Dump diário do Postgres (03:00 UTC) | ✅ funcionando (`backup_database.sh`) |
| Rotação/retenção | ✅ 30 dias no script + `backup_retention.sh` (7 diários + 4 semanais, 03:30) |
| Destino com espaço | ✅ 317 G livres |
| Integridade verificada | ✅ `gunzip -t` no script |
| Alerta de falha | ✅ **agora ativo** (Telegram via trap) |
| **Cópia offsite (3-2-1)** | ⚠️ **DESABILITADA** — rclone/S3 não configurados |

## 5. Pendência / recomendação (não-bloqueante)

- 🔸 **Offsite ausente**: hoje os backups são **só locais** (mesmo disco do VPS). Para 3-2-1 real, configurar `rclone config` (remote `offsite:` — Backblaze B2/S3/SFTP) ou ativar snapshots externos. O script já tem o passo `[3/5]` pronto para rclone — basta criar o remote.
- 🔸 **Snapshot Hostinger**: não consigo confirmar pelo CLI se há snapshots no painel da Hostinger (são externos ao VPS). **Verificar no painel** — se existirem, cobrem o requisito offsite; se não, configurar rclone.
- 🔸 `BACKUP_ALERT_WEBHOOK` no `.env` (zona proibida — não toquei): opcional, o alerta Telegram já cobre.

## 6. Rollback

```bash
cp /opt/conecta-pro/scripts/backup_database.sh.bak-20260530_185019 /opt/conecta-pro/scripts/backup_database.sh
crontab /tmp/crontab.bak-<TS>.txt
```

**Resumo:** causa-raiz = `docker exec` sem timeout travando no dockerd-hang (crise resolvida) + falha silenciosa (sem alerta). Corrigido com timeout + alerta Telegram. Backup testado e gerando dump válido; cron ativo. Offsite continua como recomendação.
