# Remoção total do Evolution + Baileys como canal oficial de WhatsApp

- **Data:** 2026-06-05 ~17:46 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Decisão (autorizada por Jordan):** Oficializar **Baileys/Chatwoot** e **excluir totalmente o Evolution**.
- **Resultado:** ✅ **Concluído.** Evolution removido (container, imagem, volume, banco, compose, env). Nenhum outro serviço afetado.

---

## 1. O que foi removido

| Recurso | Antes | Depois |
|---------|-------|--------|
| Container `evolution-api` | Up (instância `connecting`, sem número) | **removido** (0) |
| Imagem `atendai/evolution-api:latest` | presente (`1a69aaeea408`) | **removida** (0) |
| Volume `conecta-pro_evolution_data` | presente | **removido** (0) |
| Banco PostgreSQL `evolution_api` (13 MB) | em `conecta-pro-postgres` | **dropado** (0) |
| Serviço no `docker-compose.yml` | bloco `evolution-api` (linhas 332-366) + volume | **removido** |
| Porta pública `8081` | escutando | **não escuta mais** |
| Vars no backend (compose + `.env`) | `WHATSAPP_API_ENABLED=true` + `EVOLUTION_*` | **`false` + EVOLUTION comentadas** |

---

## 2. Backups criados (rollback possível)
- `/opt/conecta-pro/docker-compose.yml.bak-rmevolution-20260605_174638`
- `/opt/conecta-pro/.env.bak-rmevolution-20260605_174638`
- `/opt/conecta-pro/backend/.env.bak-rmevolution-20260605_174638`
- **Dump do banco:** `/opt/conecta-pro/backups/evolution_removal/evolution_api_20260605_174638.dump` (294 KB, formato custom `pg_restore`)

---

## 3. Passos executados (na ordem)
1. **Backups** do compose, dos dois `.env` e **`pg_dump`** do banco `evolution_api` antes de qualquer remoção.
2. `docker stop evolution-api && docker rm evolution-api`.
3. **Editado `docker-compose.yml`:** removido o serviço `evolution-api` e a declaração do volume `evolution_data`. YAML validado (`docker compose config` OK).
4. **Editado o bloco do backend no compose:** removidas as passagens `EVOLUTION_API_URL/KEY` e `WHATSAPP_INSTANCE_ID`; `WHATSAPP_API_ENABLED: "false"`.
5. **Editados `/opt/conecta-pro/.env` e `backend/.env`:** `WHATSAPP_API_ENABLED=false`; todas as linhas `EVOLUTION_*` comentadas (`# [removido-evolution 2026-06-05]`).
6. `docker volume rm conecta-pro_evolution_data`.
7. `dropdb evolution_api` (após o dump).
8. `docker rmi atendai/evolution-api:latest`.

---

## 4. Verificação final
```
container evolution = 0 | imagem = 0 | volume = 0 | DB = 0 | porta 8081 = não escuta
compose: refs ao serviço evolution-api = 0
.env: WHATSAPP_API_ENABLED=false; EVOLUTION_* ativas = 0
```
Todos os demais containers **intactos e healthy** (backend, frontend, 8 celery, flower, postgres, redis, baileys, chatwoot-fazerai, etc.).

---

## 5. Decisão consciente sobre o backend (importante)
- O `conecta-pro-backend` **NÃO foi recriado** de propósito. Recriar containers baseados na imagem `conecta-pro-backend` tem risco de **reverter código live-patched** (lição do incidente do flower). Como o backend **não estava chamando o Evolution** (log limpo) e a instância já estava não-funcional, manter o container atual é seguro.
- **Implicação:** o backend ainda carrega na memória `WHATSAPP_API_ENABLED=true` + `EVOLUTION_API_URL` antigos até o **próximo restart planejado**. Isso é **inofensivo** (não há chamadas ativas; o host `evolution-api` apenas deixaria de resolver). Os arquivos de config já estão corretos (`false` + comentado) e passarão a valer automaticamente no próximo deploy/restart do backend.

---

## 6. Estado final do WhatsApp
- **Canal oficial:** 🟢 **Baileys via Chatwoot** — conectado (`+558008804414`), mensagens fluindo, Sidekiq processando.
- **Evolution:** 🔴 **removido por completo** — sem container, imagem, volume, banco ou referência ativa.
- **Um número, um provedor:** sem mais risco de conflito de sessão entre dois provedores.

---

## 7. Como reverter (se algum dia necessário)
```bash
cd /opt/conecta-pro
cp docker-compose.yml.bak-rmevolution-20260605_174638 docker-compose.yml
cp .env.bak-rmevolution-20260605_174638 .env
cp backend/.env.bak-rmevolution-20260605_174638 backend/.env
# recriar o banco e restaurar o dump:
docker exec conecta-pro-postgres createdb -U postgres evolution_api
docker cp backups/evolution_removal/evolution_api_20260605_174638.dump conecta-pro-postgres:/tmp/evo.dump
docker exec conecta-pro-postgres pg_restore -U postgres -d evolution_api /tmp/evo.dump
docker compose up -d --no-deps evolution-api
```

---

## 8. Pendência leve (opcional)
- No próximo restart planejado do `conecta-pro-backend`, a config de WhatsApp/Evolution passa a refletir `false`/removido automaticamente — nenhuma ação extra necessária.
- Limpeza histórica: a stack antiga `chatwoot`/`chatwoot-postgres` (separada) segue candidata a remoção, se desejar.

---
*Mudanças aplicadas: remoção de 1 container + 1 imagem + 1 volume + 1 banco (com dump) + edição de compose e 2 `.env`. Backend e demais serviços não recriados/afetados. Segredos não expostos.*
