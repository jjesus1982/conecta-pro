# Diagnóstico de RAM + Triagem de Segurança — Conecta PRO VPS

- **Data:** 2026-05-29 (~16:30 UTC)
- **Host:** 82.25.75.74 — 31 GiB RAM, 4 GiB swap, 387 GB disco
- **Modo:** 100% READ-ONLY. Nada foi morto, apagado, reiniciado ou alterado.
- **Uptime:** 41 dias. **Load average:** 7.34 / 8.67 / 12.87 (alto p/ a carga real).

---

## 1. VEREDITO

### ➜ **(A) Serviços legítimos + bug operacional / má configuração. NÃO há sinal de comprometimento.**

A RAM alta e a lentidão são explicadas integralmente por processos legítimos da
própria stack, com dois problemas operacionais claros:

1. **587 processos `docker logs` PRESOS** (até 9 dias parados) somando **~7.5 GB** de RAM —
   disparados por um script de monitoramento que chama `docker logs` repetidamente
   contra um **daemon Docker travado** que nunca responde, acumulando processos zumbis-vivos.
2. **22 workers Celery vivos consumindo ~16 GB** (um deles sozinho com 2.3 GB após 24 dias),
   sem reciclagem de memória (`--max-tasks-per-child` ausente) → crescimento contínuo.
   Acompanhado de **327 processos Celery `<defunct>` (zumbis)** não reapeados.
3. **`dockerd` girando em ~156% de CPU** (acumulou **65 dias de CPU em 41 dias** de uptime) —
   é a causa direta do load alto e da lentidão, e do travamento dos `docker logs`.

**Nenhum indicador clássico de comprometimento foi encontrado** nas verificações feitas
(ver seção 4): sem minerador, sem binário em /tmp//dev/shm, sem conexão a pool,
sem cron malicioso, sem rootkit (rkhunter 0/0), sem login inesperado.

> **Sobre o pedido de "arquivos duplicados ocupando memória":** disco está em **18% (68 GB de 387 GB,
> 320 GB livres)** — espaço **não** é o problema, e arquivos em disco **não consomem RAM**.
> A lentidão é 100% RAM/swap esgotados + CPU do dockerd. Detalhes na seção 5.

---

## 2. TOP CONSUMIDORES DE RAM

Contabilidade por categoria (RSS — observação: RSS sobre-conta páginas compartilhadas,
por isso a soma excede os 28 GB reais; serve para proporção):

| Categoria | RAM (RSS) | Avaliação |
|---|---|---|
| **Celery — 22 workers vivos** | **16.20 GB** | ⚠️ Legítimo mas mal dimensionado (sem reciclagem) |
| **`docker logs` presos (587 procs)** | **7.48 GB** | ⚠️ **BUG operacional — investigar/conter** |
| Postgres backends (2 clusters) | 1.93 GB | Legítimo (156 conexões idle) |
| Ruby — sidekiq + 2× puma (Chatwoot) | 1.84 GB | Legítimo |
| uvicorn (FastAPI main_production) | 1.75 GB | Legítimo |
| clamav (clamd) | 0.95 GB | Legítimo (antivírus) |
| Stack de monitoramento (promtail/loki/exporter) | 0.32 GB | Legítimo |
| redis | 0.02 GB | Legítimo |

### Top processos individuais por RAM

| PID | %MEM | RSS | Início | Comando | Avaliação |
|---|---|---|---|---|---|
| 22786 | 7.0% | 2.32 GB | 05/Mai (24d) | celery worker `operacional` conc=2 | ⚠️ vazamento/acúmulo |
| 13001 | 5.5% | 1.83 GB | 06/Mai | uvicorn main_production:app :8080 | legítimo |
| 46750 | 4.4% | 1.45 GB | 06/Mai | celery worker `gov.batch` | ⚠️ acúmulo |
| 46729 | 3.4% | 1.12 GB | 06/Mai | celery worker `gov.batch` | ⚠️ acúmulo |
| 3031 | 3.4% | 1.12 GB | 18/Abr (41d) | celery **flower** :5555 | ⚠️ acúmulo (41 dias sem restart) |
| 54352 | 3.0% | 0.95 GB | hoje 06:34 | clamd (clamav) | legítimo |

Todos os 5 maiores têm `exe -> /usr/local/bin/python3.12` (binário em disco, legítimo). PPIDs
são os masters Celery correspondentes — cadeia de parentesco normal.

## 3. TOP CONSUMIDORES DE CPU

| PID | %CPU | TIME acumulado | Comando | Avaliação |
|---|---|---|---|---|
| **1239** | **156%** | **65 dias de CPU** | `/usr/bin/dockerd` | ⚠️ **TRAVADO/girando — causa do load** |
| 47319 / 52203 | 88% / 40% | — | `claude` | legítimo (esta própria sessão de auditoria) |
| 2972 | 4.1% | — | promtail | legítimo |
| 873 | 3.0% | — | containerd | legítimo |
| 1923 | 2.4% | — | sidekiq (Chatwoot) | legítimo |

`docker stats` deu **timeout (exit 143)** → daemon não responde à API, confirmando o estado travado
(consistente com a auditoria anterior registrada na memória).

---

## 4. TRIAGEM DE COMPROMETIMENTO — resultado

**Nenhum indicador clássico de comprometimento encontrado nas verificações feitas:**

| Verificação | Resultado |
|---|---|
| Processos de /tmp, /dev/shm, /var/tmp | ❌ Nenhum. `/dev/shm` vazio; `/tmp` só artefatos de dev (relatórios, .py, .sql); `/var/tmp` só systemd-private |
| Binários deletados/sem disco (top procs) | ❌ Nenhum — todos apontam para binários reais em /usr/local/bin, /usr/bin, /usr/sbin |
| Conexões externas suspeitas (`ss`) | ❌ Nenhuma a pool de mineração. Externas: Telegram (149.154.166.110 = telegram_assistant.py), APIs Google/Anthropic (proc `claude`), SSH de entrada |
| Cron malicioso (download/exec de URL) | ❌ Nenhum. Cron contém scripts próprios em /opt/scripts/ (rkhunter, clamav, security_audit, zombie_cleaner) |
| Rootkit (rkhunter, último log 20/05) | ❌ **Possible rootkits: 0 / Suspect files: 0** / Files checked: 142. Só warnings benignos (config SSH, hidden files comuns) |
| Logins inesperados (`last`/`who`) | ❌ Todos root via SSH de 45.236.8.40 e 191.30.223.194 (IPs BR consistentes com o admin) |
| Processos com nome aleatório/ofuscado | ❌ Nenhum. Os 327 "celery defunct" são zumbis filhos legítimos dos masters Celery |

**Ponto de atenção (não é comprometimento, mas observar):**
- `/tmp/5be0OcK54z` — diretório modo `700 root`, criado 22/05. Nome aparenta aleatório, mas dono root
  e sem processo associado rodando dele. Provável tmpdir de alguma ferramenta. **Apenas documentar** —
  não foi aberto nem tocado.
- **Gap de cobertura:** o cron grava auditoria em `/var/log/security/` que **não existe** →
  `daily_audit.log` não está sendo gerado. O `rkhunter.log` atual está com 0 bytes (rotação 24/05
  sem scan novo escrito desde então). A monitoração de segurança automatizada pode estar
  parcialmente quebrada — recomenda-se validar (sem agir agora).

---

## 5. DISCO / "DUPLICADOS" (pedido adicional)

- **Disco: 18% usado — 68 GB de 387 GB, 320 GB livres.** Espaço **não** é gargalo.
- Arquivos em disco **não consomem RAM**; não há relação com a lentidão atual.
- Backups `.sql` mais antigos/duplicados (em MB, irrelevantes p/ 387 GB):
  - `/opt/conecta-pro/backups/postgresql/pre-punchservice-20260322_150525.sql` (2.7 MB)
  - `/opt/conecta-pro/backups/backup_20260206_031757.sql` (2.0 MB)
  - Várias cópias `onvio_documents.sql` (~0.4 MB cada) em `/tmp/backup_fase_3_5_*`
  - `/tmp/*.sql` diversos de sessões de migração antigas
- `du` de `/opt/conecta-pro` estourou timeout (provável node_modules/.next pesados),
  mas com 320 GB livres **não há urgência de espaço**.

➜ **Conclusão do item disco:** limpeza de backups/clutter em /tmp é higiene saudável,
mas **não resolve** a lentidão — a lentidão é RAM/swap + CPU do dockerd.

---

## 6. RECOMENDAÇÕES PARA DECISÃO HUMANA

> Tudo abaixo é **proposta** — nada foi executado. Decisão e execução ficam com o humano.

### SE FOR CONFIG (cenário confirmado — A):

**Prioridade 1 — Daemon Docker travado (raiz da lentidão e dos 7.5 GB de docker logs):**
- Investigar por que `dockerd` (PID 1239) não responde à API e gira a 156% CPU
  (`journalctl -u docker --since "2 days ago"`, checar containerd, checar fd vazando).
- Após diagnóstico, planejar **restart controlado do docker.service** em janela de manutenção
  (vai derrubar containers — postgres, redis, chatwoot, etc.). Isso também elimina, de uma vez,
  os 587 `docker logs` presos (eles morrem quando o daemon volta).
- **Corrigir a causa dos `docker logs` presos:** localizar o script (provável `/opt/scripts/system_monitor.sh`)
  que chama `docker logs ... --tail 5` e adicionar `timeout 10` + `&` controlado, para nunca acumular
  processos quando o daemon estiver lento.

**Prioridade 2 — Celery (16 GB):**
- Adicionar `--max-tasks-per-child=100` (ou similar) a todos os workers para reciclar memória.
- Avaliar reduzir nº de filas/workers concorrentes (hoje 6 grupos × conc 2-3 = sobredimensionado
  para 0 contratos / carga atual). Flower roda há 41 dias com 1.1 GB — reiniciar periodicamente.
- Investigar por que os masters não reapeiam os 327 zumbis (o `zombie_cleaner.sh` não resolve isso —
  só o master Celery ou seu restart reapa). Restart dos workers Celery limpa os zumbis.

**Prioridade 3 — Postgres:**
- 156 conexões idle / `max_connections=150` (somando 2 clusters). Avaliar **PgBouncer** ou reduzir
  pools das apps. `shared_buffers`/`work_mem` estão em default (não são o problema agora).

**Prioridade 4 — Higiene:**
- Criar `/var/log/security/` e validar os crons de auditoria (estão gravando em dir inexistente).
- Limpar backups `.sql` antigos de /tmp (opcional, baixo impacto).

### SE FOR COMPROMETIMENTO (NÃO indicado pela evidência — passos só se surgir nova suspeita):
- **Não matar/apagar no susto** (destrói evidência). Isolar rede do host antes de mexer.
- Preservar: `cp /proc/<PID>/exe`, dump de `/proc/<PID>/maps`, `ss -tunap`, imagem de memória.
- Rodar rkhunter/chkrootkit num live system; comparar binários com hashes do pacote (`debsums`).
- Revisar `/tmp/5be0OcK54z` (conteúdo) e o gap dos logs de auditoria.

---

## 7. NOTA DE INTEGRIDADE
Auditoria 100% read-only. **Nenhum processo foi morto, nenhum arquivo apagado, nenhum serviço
reiniciado, nenhuma config alterada, nenhum IP bloqueado.** Os 587 docker logs, os 327 zumbis
Celery e o dockerd travado **permanecem exatamente como estavam** para preservar evidência e
permitir decisão humana.
