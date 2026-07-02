# ESTABILIZAÇÃO — BACKUP POSTGRES + PAUSA DO MONITOR
**Data:** 2026-05-29 (19:39 → 19:56 UTC)
**Host:** srv1134814.hstgr.cloud (31 GiB RAM, 4 GiB swap, disco 387G / 18% usado)
**Sessão:** ações seguras de estabilização — backup (prioridade 1) + pausar bot de monitoramento

> ✅ **NENHUM container foi reiniciado. O `dockerd` NÃO foi tocado. Nenhum worker/postgres/redis/uvicorn foi morto.**
> A única mutação de estado foi `systemctl stop` em 3 serviços de monitoramento (reversível).

---

## RESULTADO EM 1 LINHA
🔴 **Backup fresco FALHOU** (Postgres com conexões esgotadas + dockerd emperrado) — não forcei, aguarda decisão.
🟢 **Monitor PAUSADO** com sucesso (3 serviços parados, reversível). Load parou de escalar.

---

## PASSO 0 — ESTADO INICIAL (19:39 UTC)
| Métrica | Valor |
|---|---|
| RAM | 24 Gi usada / **7,3 Gi disponível** / 31 Gi total |
| Swap | 4 Gi usado / 50 Mi livre |
| Load (1/5/15m) | **79,2 / 78,2 / 81,6** |
| Disco /opt | 387 G total, 320 G livre (18% uso) — folga total p/ dump |

---

## PASSO 1 — BACKUP DO POSTGRES → ❌ **FALHOU (não forçado)**

### Tentativa A — via `docker exec` (caminho padrão)
- `timeout 20 docker ps` → **TIMEOUT (exit 124)**. O `dockerd` está emperrado (~156% CPU); a API não responde.
- **Conforme a regra, NÃO insisti no Docker.** Fui ao Plano B.

### Tentativa B — conexão direta (sem o daemon)
- Porta no host: só `127.0.0.1:5433` existe, e é do **`chatwoot-fazerai-postgres`** — o `conecta-pro-postgres` **não** mapeia porta no host.
- Li os configs em `/var/lib/docker/containers/*/config.v2.json` (disco, sem daemon) e identifiquei a produção:
  - **Container:** `conecta-pro-postgres` · **USER:** `postgres` · **DB:** `conecta_pro` · **IP bridge:** `172.18.0.13:5432` (rede `conecta-pro_conecta-pro-network`). *(senha lida mas **nunca exibida**)*
- `pg_dump` 16.14 disponível no host. TCP para `172.18.0.13:5432` → **PORTA ABERTA** (host alcança o container pela bridge).
- **Bloqueio:** toda conexão retorna `FATAL: sorry, too many clients already`.
  - Testado: 1 conexão de teste + **8 tentativas de `pg_dump`** em loop → todas rejeitadas pelo limite.
  - Evidência: `max_connections = 100` (volume `conecta-postgres-data`) — **100% consumido pelos próprios containers da aplicação** (pool do backend + 706 procs Celery; conexões container-a-container). Até o superusuário `postgres` é barrado → slots reservados também esgotados.

### Decisão (conforme regra do Plano B)
- **PAREI. Não forcei.** **Não** fiz cópia bruta do data dir (seria inconsistente com o banco em execução — não é backup confiável). **Não** reiniciei o Docker.
- Nenhum dump parcial ficou no disco (limpeza confirmada — `ls` em `backups/` sem `conecta_pro_20260529_*.dump`).

### ⚠️ Achado crítico — backup automático quebrado há 9 dias
- Backup existente mais recente: **`backups/postgresql/backup_20260520_030002.sql.gz`** (20/mai, 03:00, 1,7 MB).
- O cron diário das 03:00 **parou de gerar backups por volta de 20/mai** — quase certamente pela **mesma causa** (saturação de conexões + dockerd emperrado). **Há 9 dias sem backup novo.**

---

## PASSO 2 — PAUSAR O BOT DE MONITORAMENTO → 🟢 **OK (reversível)**

Serviços confirmados e parados (apenas `stop`, sem `disable`):
| Serviço | Antes | Depois |
|---|---|---|
| `conecta-pro-monitor.timer` | active (waiting) | **inactive** ✓ |
| `conecta-monitor.service` ("Conecta Plus System Monitor") | activating (auto-restart) | **inactive** ✓ |
| `conecta-pro-monitor.service` ("Conecta PRO Monitor Bot") | activating (start-pre) | **failed** (parado, fora do loop) ✓ |

- ⚠️ **Monitoramento (bot Telegram / system monitor) está PAUSADO** — alertas automáticos não serão enviados até reativar.
- Não desabilitei nenhum (não usei `disable`) → reversão simples.

### COMANDO DE REVERSÃO (reativar o monitoramento)
```bash
systemctl start conecta-pro-monitor.timer conecta-pro-monitor.service conecta-monitor.service
```

---

## PASSO 3 — VERIFICAÇÃO FINAL (19:56 UTC, read-only)

| Métrica | Início (19:39) | Fim (19:56) | Observação |
|---|---|---|---|
| RAM usada | 24 Gi | 24 Gi | inalterada (nada foi morto) |
| RAM disponível | 7,3 Gi | 7,3 Gi | — |
| Load (1/5/15m) | 79 / 78 / 82 | **85 / 84 / 83** | **parou de escalar** (pico foi 127 antes); não cai já pois o dockerd segue emperrado |
| `docker logs` presos | (oscilava 2–9) | 5 | **não crescerão mais** — spawner pausado; os 5 são órfãos (PPID 1) que vão drenar |

**Serviços críticos VIVOS (só presença, nada tocado):**
`dockerd: 1 · postgres: 189 procs · uvicorn: 2 · celery: 706 · redis: 3`

---

## CONFIRMAÇÃO DE SEGURANÇA
- ✅ `dockerd`/`docker.service` **NÃO** reiniciado.
- ✅ **Nenhum** container reiniciado/parado/recriado.
- ✅ **Nenhum** worker Celery / uvicorn / postgres / redis morto.
- ✅ Zonas de arquivo proibidas **não** tocadas.
- ✅ Senha do Postgres **nunca** ecoada (terminal ou relatório).

---

## RECOMENDAÇÕES (para a próxima decisão humana)
1. **Backup é urgente** (9 dias sem) e **só será possível** após liberar conexões do Postgres ou destravar o Docker — ambos exigem ação fora do escopo desta sessão (janela de manutenção):
   - Investigar/derrubar conexões idle (precisa de 1 slot livre → `pg_terminate_backend` de conexões idle), **ou**
   - Reiniciar o pool do backend/Celery (libera conexões), **ou**
   - Destravar o `dockerd` (resolve a causa-raiz, mas é outage total).
2. Após o backup, atacar a causa-raiz (vide `ETAPA1_DOCKER_LOGS_2026-05-29.md` e `DIAGNOSTICO_RAM_SEGURANCA_2026-05-29.md`): dockerd emperrado, Celery sem `--max-tasks-per-child`, vazamento de conexões Postgres.
3. Lembrar de **reativar o monitor** (comando acima) quando o sistema estabilizar.
