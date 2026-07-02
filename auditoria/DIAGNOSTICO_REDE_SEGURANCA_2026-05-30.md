# Diagnóstico de Rede e Segurança — READ-ONLY

- **Servidor:** `srv1134814` — IP público `82.25.75.74` (IPv6 `2a02:4780:14:14c1::1`)
- **Data:** 2026-05-30 14:14 UTC
- **Uptime:** 42 dias (boot ~2026-04-18)
- **Executado por:** root (diagnóstico read-only)
- **Escopo:** Mapeamento de estado. **NADA foi alterado.** Nenhuma regra de firewall, serviço, porta ou config foi modificada.

> ⚠️ **ACHADO PRINCIPAL (alta confiança):** a política "deny-by-default" do administrador **NÃO está em vigor**. A chain `INPUT` está com policy `ACCEPT` e **vazia** (0 regras). O arquivo `/etc/iptables/rules.v4` *pretende* aplicar `INPUT DROP` + ipset `blocklist` + chains UFW, mas a restauração **falha atomicamente** porque o ipset `blocklist` referenciado na **linha 86** não existe. Resultado: o host hoje depende apenas do fail2ban + (provável) firewall do provedor, não das regras iptables que o admin acredita estarem ativas.

---

## 1. Mapa de Portas Abertas

### 1.1 Expostas publicamente (bind `0.0.0.0` / `[::]`)

| Porta | Processo / Dono | Serviço | Container | Avaliação |
|------:|-----------------|---------|-----------|-----------|
| 22 | `sshd` | SSH | host | Esperado. Protegido por fail2ban. |
| 80 | `nginx` | HTTP (redirect) | host | Esperado. |
| 443 | `nginx` | HTTPS | host | Esperado. |
| 3000 | `next-server v16.1.6` (pid 55779, root) | Frontend produção (standalone/PM2) | host (não-docker) | cwd `/opt/conecta-pro/frontend/.next/standalone`. Bind público direto; normalmente deveria ser acessado só via nginx. **Revisar.** |
| 3001 | `docker-proxy` → `conecta-pro-frontend` | Frontend (container) | 172.18.0.5:3000 | Duplica o 3000. **Revisar necessidade de exposição.** |
| 3002 | `docker-proxy` → `erp-grafana` | Grafana 10.2.2 | 172.19.0.7:3000 | **Painel admin exposto à internet.** Tem login próprio, mas expõe superfície. **Revisar.** |
| 5555 | `docker-proxy` → `conecta-pro-flower` | Flower (monitor Celery) | 172.18.0.16:5555 | **⚠️ Sensível e exposto.** `rules.v4` *pretendia* bloquear 5555 no `eth0` (DOCKER-USER), mas a regra não está aplicada. Expõe filas/tarefas. **Prioridade de revisão.** |
| 8080 | `docker-proxy` → `conecta-pro-backend` | API FastAPI | 172.18.0.11:8080 | Esperado (API). connlimit 20/IP *pretendido* não está ativo. |
| 8081 | `docker-proxy` → `evolution-api` | Evolution API (WhatsApp) | 172.18.0.4:8080 | Exposto. Depende de API-key própria. **Revisar.** |

### 1.2 Apenas localhost (`127.0.0.1` / `[::1]`) — não acessíveis externamente

| Porta | Serviço | Container |
|------:|---------|-----------|
| 25 | Postfix (master) | host (loopback) |
| 3003 | Chatwoot | 172.20.0.2:3000 |
| 3025 | Baileys API | 172.20.0.4:3025 |
| 5433 | Postgres Chatwoot (pgvector) | 172.20.0.5:5432 |
| 9090 | Prometheus | 172.19.0.3 |
| 9093 | Alertmanager | 172.19.0.5 |
| 9100 | node-exporter | 172.19.0.4 |
| 9187 | postgres-exporter | 172.18.0.3 |
| 53 | systemd-resolved | host |

### 1.3 Internos ao Docker (sem publish no host)
`conecta-pro-postgres` (5432), `conecta-pro-redis` (6379), `conecta-pro-redis-staging`, `conecta-pro-postgres-staging`, `chatwoot-postgres`, `chatwoot-fazerai-redis`, e 8 workers Celery (8080 interno). **Bancos de dados NÃO expostos** — bom.

### 1.4 UDP
`avahi-daemon` (5353 mDNS + portas efêmeras 33551/45860) em `0.0.0.0`/`[::]`. mDNS exposto — baixo risco, mas avahi raramente é necessário em servidor. **Revisar se é preciso.**

### Portas sem dono claro: **nenhuma.** Todas as portas em escuta têm processo identificado.

---

## 2. Estado Real do Firewall vs. o que `rules.v4` Pretende

### 2.1 Estado APLICADO (fato — `iptables -S`)
- `INPUT` policy = **ACCEPT**, chain **vazia** (0 pkts, 0 regras).
- `FORWARD` policy = DROP, delegando a `DOCKER-USER` → `DOCKER-FORWARD`.
- `DOCKER-USER` = **vazia** (0 regras, 1 reference).
- Chains presentes: apenas as geradas pelo Docker (`DOCKER`, `DOCKER-BRIDGE`, `DOCKER-CT`, `DOCKER-FORWARD`, `DOCKER-INTERNAL`, `DOCKER-USER`). **Nenhuma chain UFW, PORT_SCAN ou connlimit ativa.**
- `ipset list -n` = **vazio** (nenhum ipset existe, incluindo `blocklist`).
- NAT: DNAT padrão do Docker para os containers publicados (coerente com os binds).

### 2.2 O que `rules.v4` PRETENDE aplicar (219 linhas, gerado 2026-04-06)
- `*filter` com **`:INPUT DROP`** (deny-by-default).
- Linhas 83–85: connlimit anti-flood em 443 (>50), 80 (>50), 8080 (>20) → REJECT.
- **Linha 86:** `-A INPUT -m set --match-set blocklist src -j DROP` → **referencia ipset `blocklist` inexistente.**
- Linhas 87–92: cadeia completa UFW (`ufw-before-input`, etc.).
- `ufw-user-input` libera só **22, 80, 443** (postura deny-by-default real).
- `DOCKER-USER` (linhas 137–142): DROP em `eth0` para **3000, 9187, 9121, 9100, 9093, 5555**.
- `*raw` PREROUTING: DROP de acesso externo aos IPs de container (snapshot antigo).

### 2.3 O GAP (causa raiz — confiança alta)
- `docker-firewall.service`: **`failed (exit 1)` desde 2026-04-18, há 1 mês e 11 dias.** Unit executa `iptables-restore < /etc/iptables/rules.v4`.
- `iptables-restore` é **atômico**: ao chegar na linha 86 (`--match-set blocklist`) com o ipset ausente, **aborta o arquivo inteiro**. Consequência: **nenhuma** das regras de `INPUT DROP`, connlimit, UFW e DOCKER-USER é aplicada → `INPUT` permanece `ACCEPT` e `DOCKER-USER` vazia (estado de fato observado).
- `netfilter-persistent.service` aparece `active (exited) SUCCESS`, mas o estado vivo (INPUT vazio/ACCEPT, sem blocklist) prova que as regras restritivas **não foram instaladas**. (Journal rotacionado — motivo exato não recuperável; mecanismo inferido com alta confiança a partir do estado atual.)
- **Observação adicional:** os IPs de container em `rules.v4` (ex.: backend em 172.18.0.9) **divergem** dos atuais (backend em 172.18.0.11). O `rules.v4` é um **snapshot defasado** (2026-04-06); mesmo se aplicasse, os DROPs do `*raw` apontariam para IPs errados.
- **Gap residual no próprio plano:** a porta 3000 que o `rules.v4` tenta bloquear via `DOCKER-USER` é, na verdade, servida por um **processo host** (`next-server`), não por container — `DOCKER-USER` (chain FORWARD) não o afeta. Bloqueá-la exigiria regra em `INPUT`.

### 2.4 Coerência da política deny-by-default
**Não está em vigor.** Há brechas que o admin provavelmente desconhece: Flower (5555), Grafana (3002), Evolution (8081) e frontend (3000/3001) estão acessíveis sem qualquer filtro iptables de host. A proteção efetiva hoje vem de: (a) bind em loopback dos serviços sensíveis de observabilidade/DB, (b) fail2ban, (c) provável firewall de borda do provedor (não verificável a partir do host).

---

## 3. Conexões de Entrada e Saída

Total de conexões `ESTABLISHED`: **31**. Nenhuma para destino não-reconhecido.

### 3.1 Entrada (legítimas)
- `443` ← `179.162.203.51` (nginx) — IP brasileiro, consistente com o administrador (Jordan).
- `22` ← `179.162.203.51` (sshd) — sessões SSH do admin.

### 3.2 Saída (legítimas, identificadas)
- `claude` (pids 42287/31404) → `160.79.104.10:443`, `34.149.66.137:443`, `35.190.46.17:443`, `2607:6bc0::10:443`, `2606:50c0:8002::154`, `2600:1901:...` — **tráfego do próprio agente Claude / API Anthropic + Google (GCP/Vertex)**. Esperado nesta sessão.
- `npm exec @tests...` → `2606:4700::6810:422:443` (Cloudflare) — processo de testes em execução.

### 3.3 Conexões suspeitas / não reconhecidas
**Nenhuma.** Não há conexão de saída para C2, mineração ou destino anômalo. Não foram observadas saídas para BrasilAPI/Banco Inter/Onvio/Telegram **neste instante** (provavelmente ociosas — *não-verificado* que estejam funcionais, apenas ausentes agora; sem indício de problema).

---

## 4. Postura de Segurança

### 4.1 SSH (`sshd -T` — efetivo)
| Parâmetro | Valor | Avaliação |
|-----------|-------|-----------|
| `port` | 22 | Padrão. |
| `permitrootlogin` | **yes** | ⚠️ Login root direto permitido. |
| `passwordauthentication` | **yes** | ⚠️ Autenticação por senha habilitada (superfície de brute-force). |
| `pubkeyauthentication` | yes | Bom. |
| `maxauthtries` | 3 | Bom. |
| `permitemptypasswords` | no | Bom. |
| `allowusers` | root | Restrito a root apenas. |
| `kbdinteractiveauthentication` | no | Bom. |
| `x11forwarding` | yes | Desnecessário em servidor (menor). |

### 4.2 fail2ban — **ativo e funcionando**
- 5 jails: `sshd`, `sshd-aggressive`, `nginx-http-auth`, `nginx-req-limit`, `postgresql`.
- `sshd`: 1 IP banido agora (`89.251.8.180`), 4 banidos no total.
- `sshd-aggressive`: **15 IPs banidos** atualmente (114.202.253.12, 154.51.62.34, 165.154.x, 172.96.172.162, 195.x, 31.97.119.204, 47.242.212.103, etc.).
- crowdsec: **inativo** (não instalado/parado).

### 4.3 Sinais residuais de ataque
- `auth.log` atual: **77 "Failed password"**, pulverizados (4–6 por IP) entre dezenas de origens — **ruído de brute-force de internet**, típico e **bem contido pelo fail2ban**. Sem concentração indicando ataque direcionado ativo.
- `last`: **todos** os logins recentes são root a partir de `179.162.203.51` (admin). **Nenhum login bem-sucedido de origem desconhecida.**
- **rkhunter** (último scan 2026-05-30 04:06): **0 rootkits**, 0 possible rootkits. Warnings benignos (config SSH vs rkhunter; arquivos ocultos `/etc/.safety` [dir vazio], `/etc/.updated` [timestamp do systemd], `.resolv.conf...bak`).
- **clamav** (scans diários): **0 arquivos infectados** consistentemente.

### 4.4 `/tmp/5be0OcK54z` (marcado para revisão)
- `drwx------ 2 root root` (700, root), criado **2026-05-22 06:29**.
- **Conteúdo: VAZIO** (0 arquivos). Sem payload, sem binários, sem scripts.
- Nome de 10 caracteres alfanuméricos = padrão típico de `mktemp -d`. Provável diretório temporário órfão de algum script/cron executado como root (apt, rkhunter, build ou similar). **Origem não-verificada**, mas **sem evidência de malícia** — diretório vazio e com permissão restrita. **Confiança média** de ser benigno; baixo risco no estado atual.

---

## 5. RECOMENDAÇÕES — PROPOSTAS para decisão humana (nada executado)

### 5.A — Corrigir o firewall (restaurar deny-by-default) — **PRIORIDADE ALTA**
> A política que o admin acredita ativa **não está**. Decisão e execução são do humano.
1. **Criar o ipset `blocklist` ausente** antes da restauração — ex.: `ipset create blocklist hash:ip` — para que `iptables-restore` não aborte na linha 86. **(PROPOSTA — não executar agora.)**
2. Alternativamente, tornar `docker-firewall.service` resiliente: criar o ipset no `ExecStartPre`, ou usar `iptables-restore -n` (noflush) / `--wait`, de modo que a falta do ipset não derrube toda a política.
3. **Regerar `rules.v4`** a partir do estado atual do Docker — o arquivo de 2026-04-06 tem IPs de container defasados; aplicá-lo como está reintroduziria DROPs apontando para IPs errados.
4. Após corrigir, **validar** que `INPUT` volta a `DROP` com liberação só de 22/80/443, e revalidar conectividade dos serviços antes de tornar persistente.

### 5.B — Abrir / Fechar portas (revisar exposição) — **MÉDIA/ALTA**
- **Fechar ao público (deixar só loopback ou trás de nginx/auth):**
  - `5555` (Flower) — **prioritário**, expõe filas Celery; o próprio `rules.v4` já pretendia bloqueá-lo.
  - `3002` (Grafana) — restringir a VPN/IP do admin ou só via nginx autenticado.
  - `8081` (Evolution API) — confirmar se precisa ser público; se não, restringir.
  - `3000` (next-server host) e `3001` (frontend container) — definir **um** ponto de entrada (idealmente só via nginx 443) e não expor a porta de app diretamente.
- **Manter público:** 22, 80, 443 (e 8080 se a API for consumida externamente).
- **Avaliar desligar `avahi-daemon`** (mDNS 5353) se não houver uso.
- *Nenhuma porta deve ser alterada sem decisão do admin.*

### 5.C — Endurecer SSH — **MÉDIA**
1. `PasswordAuthentication no` (migrar 100% para chave) — elimina a superfície de brute-force que hoje gera os bans.
2. `PermitRootLogin prohibit-password` (ou `no` + usuário sudo dedicado).
3. Opcional: `X11Forwarding no`.
4. Manter fail2ban; **avaliar instalar/ativar crowdsec** como camada adicional (hoje inativo).
*Aplicar só após garantir acesso por chave para não se trancar fora.*

### 5.D — Higiene / monitoramento — **BAIXA**
- Remover `/tmp/5be0OcK54z` (vazio) após confirmar origem — opcional, sem urgência.
- Adicionar healthcheck/alerta para `docker-firewall.service` (falhou silenciosamente por 41 dias).

---

## 6. Revisão do Próprio Trabalho (confiança × tipo)

| Achado | Tipo | Confiança |
|--------|------|-----------|
| Lista de portas em escuta e donos (PIDs) | Estado de fato (`ss`/`docker ps`) | **Alta** |
| `INPUT` ACCEPT + vazia; `DOCKER-USER` vazia; sem ipset | Estado de fato (`iptables -S`, `ipset list -n`) | **Alta** |
| `rules.v4` pretende INPUT DROP + blocklist (linha 86) | Estado de fato (leitura do arquivo) | **Alta** |
| `docker-firewall.service` failed há 1m11d | Estado de fato (`systemctl status`) | **Alta** |
| Mecanismo: ipset ausente aborta restore atômico → política não aplicada | **Inferência** | **Alta** |
| `rules.v4` defasado (IPs de container divergentes) | Estado de fato (comparação) | **Alta** |
| Conexões estabelecidas = agente Claude + admin; nenhuma suspeita | Estado de fato (`ss ... ESTAB`) | **Alta** (instantâneo) |
| Saídas legítimas BrasilAPI/Inter/Telegram funcionais | **Não-verificado** (ausentes neste instante; sem indício de falha) | — |
| Postura SSH (root+senha habilitados) | Estado de fato (`sshd -T`) | **Alta** |
| fail2ban ativo, 16 IPs banidos | Estado de fato (`fail2ban-client`) | **Alta** |
| Brute-force = ruído contido | Estado de fato + interpretação | **Alta** |
| rkhunter/clamav limpos | Estado de fato (logs do último scan, não rodei scan novo) | **Alta** |
| `/tmp/5be0OcK54z` vazio, provável `mktemp` órfão benigno | Fato (vazio) + **inferência** (origem) | Fato: Alta / Origem: **Média** |
| Firewall de borda do provedor | **Não-verificável** a partir do host | — |

**Limitações declaradas:** journal do `docker-firewall.service` foi rotacionado (motivo exato da falha não recuperável diretamente — inferido). Não foi testada reachability externa real das portas (exigiria scan de fora; não feito por ser intrusivo e fora do escopo read-only). Não foi executado scan AV/rootkit novo (usei o último resultado em log, conforme instruído).

---
*Relatório gerado em modo READ-ONLY. Nenhuma regra de rede, serviço, porta ou configuração foi alterada.*
