# Segurança — Fechar Flower (5555) e Grafana (3002) ao Público

- **Data:** 2026-05-30 ~14:30–14:41 UTC
- **Servidor:** `srv1134814` (IP público `82.25.75.74`)
- **Objetivo:** Restringir Flower e Grafana de `0.0.0.0` (internet) para `127.0.0.1` (loopback), via docker-compose, recriando **apenas** esses dois serviços.
- **Resultado:** ✅ **Concluído.** Ambos restritos a loopback e saudáveis. Nenhum outro serviço/SSH/firewall foi tocado.

---

## 1. Portas: antes → depois

| Serviço | Container | Antes | Depois | Status |
|---------|-----------|-------|--------|--------|
| Flower (monitor Celery) | `conecta-pro-flower` | `0.0.0.0:5555` + `[::]:5555` | **`127.0.0.1:5555`** | Up (healthy) |
| Grafana | `erp-grafana` | `0.0.0.0:3002` + `[::]:3002` | **`127.0.0.1:3002`** | Up |

Confirmação read-only pós-mudança (`ss -tlnp`):
```
LISTEN 127.0.0.1:5555  docker-proxy   (flower)
LISTEN 127.0.0.1:3002  docker-proxy   (grafana)
```
Não há mais bind em `0.0.0.0` nem `[::]` para 5555/3002. Teste externo: `http://82.25.75.74:5555/` → **sem resposta (000)**, confirmando que não está mais exposto na internet. Acesso local mantido: `127.0.0.1:3002/api/health` → **200**; `127.0.0.1:5555/healthcheck` → **200**.

---

## 2. Diffs aplicados (somente a linha de `ports`)

**`/opt/conecta-pro/docker-compose.celery.yml`** (serviço `flower`, linha 271):
```diff
     ports:
-      - "5555:5555"
+      - "127.0.0.1:5555:5555"
```

**`/opt/conecta-pro/monitoring/docker-compose.yml`** (serviço `grafana`, linha 37):
```diff
       # Grafana remapeado para 3002 para evitar conflito (2026-05-30).
-      - "3002:3000"
+      - "127.0.0.1:3002:3000"
```

YAML validado com `docker compose ... config` (parse OK em ambos); `host_ip: 127.0.0.1` confirmado no config renderizado antes de aplicar.

### Backups criados
- `/opt/conecta-pro/docker-compose.celery.yml.bak-sec-20260530`
- `/opt/conecta-pro/monitoring/docker-compose.yml.bak-sec-20260530`

---

## 3. Aplicação (recriou SÓ flower e grafana)

Comandos usados (com `--no-deps` e nome explícito de serviço, sem `up` global):
```
docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps flower
docker compose -f monitoring/docker-compose.yml up -d --no-deps grafana
```

### Prova de que nenhum outro container foi recriado
Snapshot de `StartedAt` antes/depois — todos os demais permanecem com início de **2026-05-29** (intactos); apenas flower e grafana têm início em **2026-05-30 14:3x**:

| Container | StartedAt | Tocado? |
|-----------|-----------|---------|
| conecta-pro-backend | 2026-05-29T21:25 | NÃO |
| conecta-pro-postgres | 2026-05-29T20:36 | NÃO |
| conecta-pro-redis | 2026-05-29T20:36 | NÃO |
| conecta-pro-frontend | 2026-05-29T20:36 | NÃO |
| conecta-pro-celery-batch / beat / operacional / nfse / sefaz / priority / integrations | 2026-05-29T21:3x | NÃO |
| evolution-api, chatwoot-*, baileys, prometheus, alertmanager, exporters | 2026-05-29 | NÃO |
| **erp-grafana** | **2026-05-30T14:31** | SIM (alvo) |
| **conecta-pro-flower** | **2026-05-30T14:40** | SIM (alvo) |

**SSH (porta 22):** intacto — `sshd` segue ouvindo em `0.0.0.0:22` / `[::]:22` (pid 38300).
**iptables / chain INPUT:** **não tocada** — segue `policy ACCEPT` (mesmo estado do diagnóstico anterior; nenhuma regra de firewall/ipset foi alterada).

---

## 4. Incidente durante a execução: Flower entrou em crash-loop (resolvido)

> **Importante para o histórico operacional deste projeto.**

### O que aconteceu
Ao recriar o flower via compose, o container subiu da **imagem** `conecta-pro-backend:latest` (`facf345e4741`, ~7 semanas) e entrou em crash-loop com:
```
ModuleNotFoundError: No module named 'modules.operacional.ai'
  File "/app/modules/operacional/__init__.py", line 24, in <module>
    from .ai import (  ...
```

### Causa raiz
Neste projeto, o código do backend é **embutido na imagem, mas atualizado em produção via `docker cp` + restart** (padrão documentado). Os containers que rodavam há ~17h (backend, celery workers) tiveram o código vivo copiado para dentro da camada gravável. **A imagem em si está incompleta** — não contém o pacote `modules/operacional/ai/`. Ao recriar o flower pelo compose, ele **descartou o código live-patched** e voltou ao código da imagem, que quebra na importação.

- **A mudança de porta NÃO causou o crash** — o problema é de código/imagem, independente do mapeamento de porta. Reverter a porta não resolveria.
- **Produção não foi afetada:** os workers Celery continuaram rodando normalmente; o Flower é apenas o dashboard de monitoramento.

### Correção aplicada (autorizada pelo administrador)
Sincronização do código vivo de um container saudável para o flower, mantendo a porta em loopback:
1. Tentativa inicial copiando de `conecta-pro-backend` **falhou** — o backend tem um estado divergente de `modules.operacional` (também não importa `.ai`; funciona porque seu entrypoint de API não dispara esse import).
2. **Fonte correta identificada:** os **celery workers** rodam o mesmo `celery -A celery_app` que o flower e possuem o pacote `/app/modules/operacional/ai/` completo (diretório com `__init__.py`).
3. Sync final executado:
   ```
   docker stop conecta-pro-flower
   docker exec conecta-pro-celery-batch tar -C /app -cf - modules | docker cp - conecta-pro-flower:/app
   docker start conecta-pro-flower
   ```
4. Resultado: flower **Up (healthy)**, `RestartCount=0`, conectado ao broker Redis, sem erro de import, `healthcheck → 200`.

### Lição / atenção para o futuro
Qualquer recriação (compose `up`/`recreate`) de containers baseados em `conecta-pro-backend:latest` (backend, flower, celery workers) **vai reverter o código para a imagem incompleta** e quebrar serviços que importam `modules.operacional.ai`. **Recomendação (proposta, fora do escopo desta missão):** reconstruir a imagem `conecta-pro-backend:latest` com o código atual já embutido, para eliminar a dependência do `docker cp` pós-start.

---

## 5. Como reverter

### Reverter o mapeamento de porta (voltar a expor publicamente — NÃO recomendado)
```
cd /opt/conecta-pro
cp docker-compose.celery.yml.bak-sec-20260530 docker-compose.celery.yml
cp monitoring/docker-compose.yml.bak-sec-20260530 monitoring/docker-compose.yml
docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps flower
docker compose -f monitoring/docker-compose.yml up -d --no-deps grafana
```
> ⚠️ Ao recriar o flower, será necessário **re-sincronizar o código** do worker (passo 4.3 acima), senão ele voltará a entrar em crash-loop pelo mesmo `ModuleNotFoundError`. O grafana reverte sem efeitos colaterais.

---

## 6. Checklist de escopo (tudo respeitado)
- [x] Editado **apenas** o mapeamento de portas de flower e grafana (com backup + diff).
- [x] Recriados **apenas** flower e grafana (`--no-deps`); demais containers intactos.
- [x] SSH (porta 22) e `sshd_config` **não tocados**.
- [x] iptables / chain INPUT / ipset / rules.v4 **não tocados**.
- [x] Postgres, Redis, backend, frontend, celery workers/beat **não tocados**.
- [x] Parado e consultado o administrador quando o flower ameaçou ficar fora (ação de correção autorizada antes de prosseguir).

---
*Mudanças aplicadas: 2 linhas de `ports` em compose + sync de código do flower (autorizado). Nenhuma regra de rede/firewall/SSH alterada.*
