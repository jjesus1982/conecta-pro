# RESOLUÇÃO VPS — Conclusão da Intervenção de Destravamento

**Host:** srv1134814.hstgr.cloud (31 GiB RAM, 4 GiB swap)
**Data:** 2026-05-30 (continuação — sessão anterior caiu por queda de internet)
**Escopo desta sessão:** concluir APENAS as pendências; o trabalho pesado já estava consolidado e estável.

> Princípios respeitados: nada simulado; zonas proibidas (`financial/`, `government_integrations/`,
> `alembic/versions/`, `main_production.py`, `credentials/`, `.env*`) **não foram tocadas**;
> nenhum container de aplicação, Postgres, Redis, Celery ou o frontend de produção foi reiniciado/morto.

---

## 1. Resumo executivo

Três pendências fechadas e uma reportada para decisão:

| Item | Estado anterior | Ação | Estado final |
|------|-----------------|------|--------------|
| **conecta-backend.service** | Flapping (699.666 restarts) | `stop` + `disable` | inactive / disabled ✅ |
| **conecta-healer.service** | Flapping (356.330 restarts) | `stop` + `disable` | inactive / disabled ✅ |
| **erp-grafana** | Restarting em loop (16-17h) | fix config + remap porta | Up, healthy, RestartCount=0 ✅ |
| **docker-firewall.service** | failed (há ~1 mês) | diagnosticado, **não tocado** | ⚠️ reportado p/ decisão |

---

## 2. Métricas antes → depois

| Métrica | Pico da crise (29/05) | Início desta sessão | **Depois (30/05 13:37)** |
|---------|----------------------:|--------------------:|-------------------------:|
| Load (1m) | 79,2 | 1,49 | **1,20** |
| Load (5/15m) | 78,2 / 81,6 | — | **1,56 / 1,35** |
| RAM disponível | 7,3 Gi | ~13 Gi | **17 Gi** |
| Swap usado | — | — | 32 Mi (de 4 Gi) |
| Containers running | — | — | **25** (20 healthy) |
| Containers restarting/unhealthy | vários | 1 (grafana) | **0** |
| conecta-pro containers | — | 14 UP | **14 UP/healthy** |

O load de 1m caiu de 2,36 (medido no início do diagnóstico) para 1,20 após eliminar o loop de
flapping dos dois serviços órfãos — que reiniciavam continuamente (Restart=always) consumindo CPU.

---

## 3. Detalhamento das ações

### 3.1 Serviços órfãos do Conecta PLUS (estabilizados)

`conecta-backend.service` e `conecta-healer.service` apontavam para `WorkingDirectory=/opt/conecta-plus`,
diretório que **não existe mais** (Conecta PLUS foi removido em sessões anteriores). Com `Restart=always`,
entravam em loop infinito:
- `conecta-backend`: status `209/STDOUT`, **699.666** reinícios acumulados.
- `conecta-healer`: status `200/CHDIR` (chdir falha, dir inexistente), **356.330** reinícios.

O backend do **Conecta PRO roda em Docker** (`conecta-pro-backend`, healthy) — esses units systemd eram
puro resíduo. Ação aplicada (reversível):
```
systemctl stop conecta-backend.service conecta-healer.service
systemctl disable conecta-backend.service conecta-healer.service
```
Resultado: ambos `inactive` + `disabled`. Loop de flapping eliminado.
> Reversão, se necessário: `systemctl enable --now <svc>` (mas exigiria recriar `/opt/conecta-plus`).

### 3.2 erp-grafana (religado com segurança)

**Causa raiz dupla** — o container nunca subia, por dois motivos encadeados:
1. **Plugins via rede ausente:** `GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-simple-json-datasource`
   força o `grafana-cli` a consultar `grafana.com` a cada boot. O VPS **não tem rota de saída**
   (`dial udp 1.1.1.1:53: network is unreachable`) → o install falha e derruba o container.
   - Os **dois plugins já estavam instalados** no volume `monitoring_grafana_data`
     (`/var/lib/grafana/plugins`), tornando o download desnecessário.
2. **Conflito de porta:** o compose publicava `3000:3000`, mas a porta 3000 do host pertence ao
   **frontend de produção** (`conecta-pro-frontend` via PM2, online há 23 dias). O mapeamento sempre colidia.

**Correção (arquivo `monitoring/docker-compose.yml`, fora das zonas proibidas):**
- Comentada a linha `GF_INSTALL_PLUGINS` (com nota explicativa) → Grafana carrega os plugins do volume.
- Remapeada a porta do Grafana: `3000:3000` → **`3002:3000`** (3002 estava livre), sem tocar no frontend.
- Ajustado `GF_SERVER_ROOT_URL` para `http://localhost:3002`.
- `docker compose up -d grafana` (recriação isolada do serviço grafana).

**Verificação:**
- `GET http://localhost:3002/api/health` → **200** `{"database":"ok","version":"10.2.2"}`
- Logs: `Plugin registered pluginId=grafana-clock-panel` e `grafana-simple-json-datasource` (do volume, sem erro de rede).
- `RestartCount=0`, `Up` estável. Sem novo loop.

> ⚠️ **Mudança de acesso:** o Grafana agora responde em **:3002** (antes pretendia :3000, que nunca funcionou
> por causa do conflito). Atualize bookmarks/reverse-proxy se houver.

### 3.3 docker-firewall.service (⚠️ NÃO tocado — requer decisão)

- Unit `oneshot`: `ExecStart=/sbin/iptables-restore < /etc/iptables/rules.v4`.
- **Não está "flapping"** (oneshot): falhou **uma vez** em 2026-04-18 e permanece `failed` desde então.
- Causa: o arquivo `/etc/iptables/rules.v4` **falha no teste de sintaxe**:
  `iptables-restore --test` → *"Set blocklist doesn't exist"* na **linha 86** (referencia um ipset
  `blocklist` que não é criado antes do restore).
- Estado atual do firewall: a chain `DOCKER-USER` está **vazia** (sem regras restauradas).

**Por que não agi:** firewall é matéria de **segurança de rede**. Corrigir exigiria editar regras
(`rules.v4`) ou criar/popular o ipset `blocklist` — risco de bloquear acesso ao próprio VPS e decisão
que não cabe a uma ação automática. **Reportado para sua decisão.**

Opções (a confirmar antes de executar):
- (a) Criar o ipset ausente: `ipset create blocklist hash:ip` e então `systemctl start docker-firewall`.
- (b) Editar `rules.v4` para criar o set no próprio arquivo ou remover a regra da linha 86.
- (c) Manter como está (sem regras DOCKER-USER customizadas) se a política de firewall for outra hoje.
> Nenhuma destas foi aplicada. Não consome recursos enquanto `failed`.

---

## 4. Estado final dos serviços (saúde honesta)

🟢 **Saudável e estável:**
- 25 containers running, 20 healthy, **0 restarting/unhealthy**.
- 14 containers `conecta-pro-*` UP/healthy.
- `erp-grafana` UP em :3002, plugins OK, RestartCount=0.
- Load 1,20 / RAM 17 Gi livre / swap praticamente zerado.
- Backup válido preservado: `/opt/conecta-pro/backups/conecta_pro_20260529_211303.dump` (3,7 MB, 29/05 21:15).
- Serviços órfãos do Conecta PLUS desativados — não voltam no boot.

🟡 **Pendências / atenção:**
- **docker-firewall.service** `failed` — decisão de segurança pendente (seção 3.3).
- **Sem rota de saída no VPS** (DNS/internet externa indisponível): é a causa-raiz do problema do Grafana
  e impede qualquer download de plugin/imagem futuro. Confirmar se é intencional (rede fechada) ou falha.
- **Backup automático:** o relatório de 29/05 registrou que o cron diário das 03:00 parou ~20/mai
  (saturação de conexões Postgres). O backup manual de 29/05 está OK, mas **o agendamento automático
  deve ser revalidado** — fora do escopo desta sessão de estabilização.
- Acesso ao Grafana mudou para :3002 (atualizar referências).

🔴 **Nada crítico aberto.** Nenhum serviço de aplicação do Conecta PRO foi impactado.

---

## 5. Arquivos alterados nesta sessão

- `/opt/conecta-pro/monitoring/docker-compose.yml` — serviço `grafana`: porta `3002:3000`,
  `GF_INSTALL_PLUGINS` comentado, `GF_SERVER_ROOT_URL` → :3002. (Fora das zonas proibidas.)
- systemd: `conecta-backend.service` e `conecta-healer.service` desabilitados (links em
  `multi-user.target.wants` removidos).
- Este relatório: `/opt/conecta-pro/auditoria/RESOLUCAO_VPS_2026-05-30.md`.

*Nenhuma alteração em banco de dados, código de aplicação, credenciais ou `.env`.*
