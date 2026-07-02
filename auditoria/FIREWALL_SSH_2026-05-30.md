# FRENTE 2 — Firewall / SSH (INTERATIVO)

**Data:** 2026-05-30
**Pré-requisito:** ✅ Jordan confirmou console Hostinger aberto e testado antes de qualquer mudança.
**Status:** ✅ deny-by-default estabelecido, portas indevidas fechadas, persistido. SSH mantido (decisão do Jordan).

---

## 1. Diagnóstico (estado real ANTES)

| Item | Antes |
|---|---|
| Política INPUT | **ACCEPT (chain vazia)** — o deny-by-default que se acreditava ativo **NÃO estava** |
| `docker-firewall.service` | **failed** — `ExecStart=/sbin/iptables-restore < rules.v4`: o systemd **não interpreta `<`** → "Unknown arguments". Nunca funcionou (o ipset `blocklist` ausente era problema secundário) |
| Firewall efetivo | **só fail2ban** (reativo) |
| Portas públicas indevidas | 8081 (evolution-api), **3000** (frontend PM2 host), **3001** (frontend docker) |
| SSH | PermitRootLogin yes, PasswordAuthentication yes, root com 5 chaves |

## 2. Decisões do Jordan (interativo)

1. Firewall base: **ruleset mínimo limpo** (não restaurar o rules.v4 UFW antigo).
2. Portas: **fechar 3000 e 3001, manter 8081** (evolution pode receber webhook WhatsApp).
3. SSH: **manter senha + chave** (não desabilitar PasswordAuthentication).

## 3. O que foi aplicado (incremental, SSH-first, com rede de segurança)

Backup das regras: `/tmp/iptables_backup_20260530_185755.rules`. Auto-reversão de 10 min armada durante a aplicação (cancelada após validação).

**Deny-by-default (ordem que protege o SSH):**
```
-A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT   # mantém sessões vivas
-A INPUT -i lo -j ACCEPT                                         # loopback
-A INPUT -p tcp --dport 22 -j ACCEPT                            # SSH (ANTES do DROP)
-A INPUT -p tcp --dport 80 -j ACCEPT
-A INPUT -p tcp --dport 443 -j ACCEPT
-A INPUT -p icmp --icmp-type 8 -j ACCEPT                        # ping
-P INPUT DROP                                                   # deny-by-default
-P FORWARD DROP
```
- **Validação SSH:** Jordan abriu uma **2ª sessão nova** e confirmou que conectou ANTES de persistir (a regra externa do ACCEPT 22 funciona). *(Meu teste do box→IP-próprio passa por loopback e não vale como prova externa — por isso a validação foi do Jordan, de fora.)*

**Fechar portas indevidas:**
- **3000** (frontend PM2 host): bloqueada ao externo automaticamente pelo INPUT DROP (sem ACCEPT). nginx/localhost segue acessando.
- **3001** (frontend docker): `-A DOCKER-USER -i eth0 -p tcp -m conntrack --ctorigdstport 3001 -j DROP` — bloqueia **só o externo** (`-i eth0`); o **nginx faz upstream via `127.0.0.1:3001` (loopback)** e continua funcionando (site https → 200). Regra durável (por porta publicada, não por IP de container).
- **8081** (evolution): mantida, conforme decisão.

**Limpeza:** `docker-firewall.service` **desabilitado** (quebrado pelo bug do `<` no systemd + redundante com netfilter-persistent). Elimina também um dos "serviços flapping" herdados. `ipset blocklist` criado (vazio) por compatibilidade.

## 4. Persistência

- **`netfilter-persistent`** (enabled) salvou o estado em `/etc/iptables/rules.v4` e o **`reload` (simulação de boot) preservou tudo** (INPUT DROP + SSH + bloqueio 3001). Sobrevive a reboot.
- rules.v4 agora **não tem mais** a referência ao `blocklist` quebrada.

## 5. SSH (inalterado — decisão do Jordan)

- PermitRootLogin **yes**, PasswordAuthentication **yes**, PubkeyAuthentication **yes** (root com 5 chaves).
- Proteção de brute-force: **fail2ban** (jails `sshd` + `sshd-aggressive` ativos).
- *Recomendação futura (não aplicada):* desabilitar PasswordAuthentication (chave já funciona) eliminaria brute-force de senha — quando o Jordan quiser.

## 6. Estado final (prova)

```
Políticas: INPUT DROP | FORWARD DROP | OUTPUT ACCEPT
INPUT ACCEPT: ESTABLISHED, lo, 22, 80, 443, icmp
DOCKER-USER: DROP externo 3001
fail2ban: nginx-http-auth, nginx-req-limit, postgresql, sshd, sshd-aggressive
docker-firewall: inactive/disabled | netfilter-persistent: enabled
ssh_estab=4 | site https=200
```

## 7. Rollback (documentado)

```bash
# Reverter o firewall inteiro para o estado anterior:
iptables -P INPUT ACCEPT
iptables-restore < /tmp/iptables_backup_20260530_185755.rules
netfilter-persistent save
# (e, se quiser, reabilitar docker-firewall.service — mas estava quebrado)
```

**Resumo:** deny-by-default real estabelecido (era ACCEPT total), 3000/3001 fechados ao externo sem quebrar o site (nginx via loopback), 8081 mantida, persistido por netfilter-persistent, serviço quebrado removido. SSH mantido com senha+chave por decisão do Jordan (fail2ban protege). Tudo validado (sessão nova do Jordan conectou) e reversível.
