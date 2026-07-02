# ETAPA 1 — LIMPEZA `docker logs` PRESOS + ZUMBIS CELERY
**Data:** 2026-05-29 (~19:07 UTC)
**Host:** srv1134814.hstgr.cloud (31 GiB RAM, 4 GiB swap)
**Executor:** sessão de auditoria (Claude) — **com autorização explícita do Jordan** para ação destrutiva
**Escopo autorizado:** capturar `free -h`, matar `docker logs` presos, tentar reapear zumbis Celery

> ⚠️ **LEITURA HONESTA: a limpeza segura teve efeito praticamente nulo.** O problema NÃO eram os
> `docker logs` remanescentes nem os zumbis — é o **`dockerd` emperrado a ~156% de CPU** + um
> **bot de monitoramento que respawna `docker logs` continuamente**. Os 7,5 GB dos 587 `docker logs`
> originais (diagnóstico das 16:30) **já tinham sido liberados antes** desta sessão (provável cron
> `zombie_cleaner`/find-killer). Detalhes e correção real abaixo.

---

## 1. ANTES → DEPOIS (medições reais desta sessão)

| Métrica | ANTES (18:58 UTC) | DEPOIS (19:07 UTC) | Δ |
|---|---|---|---|
| RAM usada | 24 Gi | 24 Gi | **≈ 0** |
| RAM disponível | 7,1 Gi | 6,9 Gi | ≈ 0 |
| Swap livre | 50 Mi | 50 Mi | 0 |
| `docker logs` presos | 9 | 2 | -7 (mas oscila: respawnam) |
| Zumbis Celery `<defunct>` | 396 | **397** | **+1 (NÃO reapeados)** |
| Load average (1/5/15m) | 103 / 108 / 102 | **127 / 129 / 115** | **piorando** |
| `dockerd` %CPU (PID 1239) | — | **156%** | causa-raiz |

> **Referência histórica (diagnóstico read-only das 16:30, outra sessão):** 587 `docker logs`
> presos = ~7,5 GB; RAM usada 28 Gi / disponível 2,5 Gi. Esses 587 **já não existiam** quando
> esta sessão começou (sobravam 4) — a liberação de ~5 GB ocorreu **antes** e **não** por mim.

---

## 2. AÇÕES EXECUTADAS NESTA SESSÃO

### Ação 1 — matar `docker logs` presos
- Comando (mira só o binário `docker`, preserva o shell):
  `ps -eo pid,comm,args | awk '$2=="docker" && /logs/{print $1}' | xargs kill -9`
- Mortos: PIDs **22371** (`docker logs conecta-pro-postgres --tail 5`) e **22595** (`docker logs conecta-pro-redis --tail 5`), ambos em estado `Sl`.
- **Resultado:** sem efeito sustentado — o monitor respawna novos `docker logs` em minutos (oscila 2↔9). RAM não mudou (cada `docker logs` ocioso pesa pouco; o peso grande era o acúmulo dos 587, já resolvido).

### Ação 2 — reapear zumbis Celery (`SIGCHLD`, não-destrutivo)
- `kill -CHLD` enviado aos 6 masters Celery: PIDs **3950** (sefaz), **41312** (batch), **65453** (operacional), **3520** (priority), **1154** (integrations), **3805** (nfse).
- **Resultado: FALHOU em reapear** — contagem foi de 396 → 397. Os masters não estão coletando os filhos `<defunct>` mesmo recebendo SIGCHLD.
- **Por quê:** zumbis Celery persistentes assim só somem **reiniciando o processo-pai** (o container/worker). Não há `kill` que limpe zumbi (ele já está morto; é só entrada na tabela de processos).
- **Importante:** zumbis ocupam **~0 RAM**. Reapeá-los **não** resolveria a pressão de memória — limparia só a tabela de processos.

---

## 3. CAUSA-RAIZ REAL (o que de fato precisa ser corrigido)

| # | Causa | Evidência | Impacto |
|---|-------|-----------|---------|
| 1 | **`dockerd` emperrado** (PID 1239) | **156–157% CPU**, 65 dias de CPU em 41 de uptime; `docker ps`/`docker logs` penduram | Load 89→127 e subindo; lentidão geral; trava todo `docker logs` |
| 2 | **Bot de monitoramento respawna `docker logs`** | `conecta-pro-monitor.service` (timer a cada ~30min) e `conecta-monitor.service` chamam `docker logs <c> --tail 5/--since 5m`; ao pendurar no dockerd, viram órfãos (PPID 1) | Acúmulo perpétuo de `docker logs` presos (era o que gerava os 587) |
| 3 | **Workers Celery sem reciclagem** | 6 masters há 24 dias, `--max-tasks-per-child` ausente; ~16 GB vivos + 397 filhos `<defunct>` | Crescimento contínuo de RAM; zumbis acumulam |
| 4 | **Serviços systemd em loop de restart** | `conecta-backend.service` e `conecta-healer.service` = `activating auto-restart`; `conecta-pro-monitor.service` preso em `start-pre`; `docker-firewall.service` = **FAILED** | Churn de processos, contribui p/ load |

---

## 4. PLANO DE CORREÇÃO REAL — requer decisão/janela (NADA disso foi executado)

> Tudo abaixo está **comentado** e exige aprovação explícita. Os itens 1–2 são os que de fato
> resolvem; envolvem risco de outage e por isso **não foram executados** mesmo com a autorização
> de "limpeza fresca" — a autorização foi dada antes de sabermos que o `dockerd` está emperrado.

```bash
# === (A) PARAR O SANGRAMENTO DE 'docker logs' — baixo risco, reversível ===
#   Pausa o bot que respawna docker logs contra o daemon emperrado:
# systemctl stop conecta-pro-monitor.timer conecta-pro-monitor.service
# systemctl stop conecta-monitor.service
#   (monitoramento fica pausado até reativar — confirmar que não cega alertas críticos)

# === (B) RECICLAR CELERY (reapeia os 397 zumbis + recupera ~16 GB) — MÉDIO/ALTO risco ===
#   PROBLEMA: depende do docker, que está emperrado → restart pode pendurar.
#   Fazer em janela de manutenção, um worker por vez:
# docker restart conecta-pro-celery-operacional   # (repetir p/ sefaz, batch, priority, integrations, nfse)
#   Correção definitiva: adicionar --max-tasks-per-child=100 ao comando dos workers (evita reacúmulo).

# === (C) DESTRAVAR O dockerd (causa-raiz do load) — ALTO risco: OUTAGE TOTAL ===
#   Reinicia TODOS os containers. SÓ em janela de manutenção combinada:
# systemctl restart docker
#   Depois validar: docker ps  (esperar todos voltarem) + revisar healthchecks (vide DIAGNOSTICO_FASE1).

# === (D) corrigir serviços flapping ===
# systemctl status conecta-backend.service conecta-healer.service docker-firewall.service
#   (investigar logs antes de mexer: journalctl -u <serviço> --no-pager | tail -50)
```

---

## 5. RECOMENDAÇÃO

1. **Não adianta matar `docker logs` nem zumbis** — voltam / não liberam RAM. Foi feito (Ação 1/2) e confirmado ineficaz.
2. **Primeiro passo seguro:** pausar o bot de monitoramento (item A) para estancar o load.
3. **Correção de verdade exige janela de manutenção** para reiniciar Celery (B) e, idealmente, o `dockerd` (C) — ambos com risco de indisponibilidade, **portanto aguardam seu OK explícito e horário combinado**.
4. Ver `auditoria/DIAGNOSTICO_RAM_SEGURANCA_2026-05-29.md` (diagnóstico read-only completo) e `auditoria/DIAGNOSTICO_FASE1_2026-05-29.md` (containers unhealthy).

**Estado ao fim desta sessão:** RAM 24 Gi usada / 6,9 Gi livre · 2 `docker logs` presos · 397 zumbis · load 127 · dockerd 156%. **Nada crítico foi reiniciado.**
