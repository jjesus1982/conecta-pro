# Diagnóstico — Docker image store irresponsivo (READ-ONLY) ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-DOCKER-DIAG
- **Modo:** 100% READ-ONLY — nada reiniciado/prune/rm/build. Só inspeção.
- **Veredito:** **NÃO é disco nem corrupção.** É um **vazamento de processos `docker logs` órfãos** (gerados pelo `agents/context_builder.py`) que **satura o dockerd**.

---

## a) Sintoma confirmado
| Comando | exit | |
|---------|------|--|
| `docker images` | **124** | trava |
| `docker image inspect 5a14e5db` | **124** | trava |
| `docker ps` | **124** | trava (piorou — antes respondia) |
| `docker version` | 0 | OK |
| `docker info` | 0 | OK |
| `ctr -n moby images ls` | **0** | **OK (containerd responde!)** |

→ O que trava é a **enumeração via dockerd** (images/ps/inspect). `version`/`info` (estado leve) e o **containerd direto (`ctr`)** respondem. Logo o gargalo está no **dockerd**, não no containerd nem no disco.

## b) Disco — NÃO é a causa
- `/var/lib/docker` em `/dev/sda1`: **387G, 72G usados, 316G livres (19%)**. Inodes **4%** (50M livres). Sem pressão de espaço nem de inode.

## c) Daemon / containerd
- `containerd`: **saudável** (`Ssl`, ativo; `ctr -n moby images ls` retorna em <12s). Content store: **634 blobs** em `/var/lib/containerd/io.containerd.content.v1.content/blobs/sha256`.
- `dockerd`: responde a `info`/`version` mas **trava** em qualquer enumeração de imagens/containers.
- **Nenhum processo em estado `D`** (não há I/O de kernel travado). 27 `containerd-shim` (= ~26 containers running, normal).
- Docker 29.1.3, **Storage Driver `overlayfs`**, **image store do containerd** (novo padrão v28+). `/var/lib/docker/image/` **não existe** (esperado nessa arquitetura) — por isso o método de ler `repositories.json` do disco não se aplica; usei `ctr`.

## d) Store / overlay — sem corrupção
- 22 imagens (via `docker info`), 634 blobs no content store, `ctr` lista tudo. **Store íntegro**, apenas a **via dockerd→listagem está saturada**.

## e) Âncora de rollback — **EXISTE** ✅ (confirmado via `ctr`)
```
conecta-pro-backend:latest
conecta-pro-backend:pre-rebuild-followup-20260610   <-- ÂNCORA do último rebuild
conecta-pro-backend:pre-rebuild-fvisita-20260609
conecta-pro-backend:pre-rebuild-transfer-20260609
conecta-pro-backend:pre-rerebuild2-20260609
conecta-pro-backend:rebuild-20260609
conecta-pro-backend:rebuild-followup-20260610
conecta-pro-backend:rebuild-fvisita-20260609
conecta-pro-backend:rebuild-transfer-20260609
```
O rollback do último rebuild está preservado no store.

## f) DIAGNÓSTICO — causa-raiz
🔴 **Vazamento de processos `docker logs` órfãos saturando o dockerd.**

- **423 processos `docker logs` travados** (estado `Sl`), dos quais **416 são** `docker logs conecta-pro-redis --tail 5` e `docker logs conecta-pro-postgres --tail 5`, com **PPID=1** (órfãos reparentados ao systemd).
- **Idade (leak ATIVO e crescente):** 5 nos últimos 5min, 56 na última hora, 354 em 1-24h, 8 >2d. O cluster redis/postgres começou ~6-7h atrás e cresce ~1/min. (Os 8 >2d são resíduo separado de sessões `claude` antigas: `docker logs evolution-api/baileys-api/chatwoot-...` de ~5-11 dias.)
- **Origem:** `agents/context_builder.py` (rodando agora, PID 15630):
  - linha 193-196: itera `["conecta-pro-backend","conecta-pro-postgres","conecta-pro-redis"]` e roda `docker logs {c} --tail 5 2>&1 | grep ... | tail -3`.
  - linha 26-28: `run(cmd, timeout=15)` = `subprocess.run(cmd, shell=True, timeout=15)`. Quando o `docker logs` excede 15s, o `TimeoutExpired` mata **apenas o `/bin/sh -c`**, **não o neto `docker logs`** (não há `process group kill`). O `docker logs` continua preso (conexão aberta ao dockerd) e é reparentado ao PID 1.
- **Mecanismo de runaway (feedback loop):** cada `docker logs` preso mantém uma conexão/handler ativo no dockerd → o dockerd fica mais lento → mais chamadas `docker logs` do context_builder estouram o timeout de 15s → mais órfãos → dockerd ainda mais lento. Em ~6-7h chegou a 416, e agora a **enumeração (images/ps/inspect) fica na fila atrás dos handlers presos e estoura o timeout**.

### ⚠️ Alerta crítico para qualquer correção
- **`Live Restore Enabled: false`** → **reiniciar o dockerd DERRUBA os 26 containers running** (inclui produção + postgres). **NÃO reiniciar o Docker** como primeiro recurso.

### Recomendação (NÃO executei — decisão do Jordan)
Ordem segura, do menos ao mais invasivo:
1. **Parar a fonte do leak primeiro:** pausar/parar o `context_builder.py` e o que o agenda (evita re-vazar enquanto se limpa). Idealmente corrigir o `run()` para matar o **grupo de processos** no timeout: `subprocess.run(..., start_new_session=True)` + `os.killpg` no `TimeoutExpired` (e/ou trocar `docker logs ... | grep` por leitura sem pipe). Código em `agents/` (fora das forbidden zones do rebuild, mas é mudança — sob aprovação).
2. **Ceifar os 416 órfãos** (inócuos — são chamadas de API presas, não afetam os containers): `pkill -f 'docker logs conecta-pro-(redis|postgres) --tail 5'` (+ os 8 antigos de evolution/baileys/chatwoot). Isso libera os handlers do dockerd e **deve destravar `docker images`/`ps`** sem tocar em container algum.
3. **Reavaliar** `docker images` após o passo 2. **Só se** ainda travado, considerar reiniciar o dockerd — mas **antes habilitar `live-restore`** no `daemon.json` (senão derruba os 26 containers). Esse passo é último recurso e merece janela.
4. Antes do rebuild futuro: confirmar que o leak não volta (context_builder corrigido), senão o `docker build` também travará.

---

## Resumo
- **Sintoma:** dockerd trava em images/ps/inspect; `version`/`info`/`ctr` OK. Não é disco (316G livres) nem containerd (saudável, 634 blobs) nem corrupção.
- **Causa-raiz:** **416+ processos `docker logs ... --tail 5` órfãos** vazados pelo `agents/context_builder.py` (timeout do `subprocess.run` não mata o neto), saturando o dockerd em feedback loop (~6-7h, +1/min).
- **Âncora de rollback** `pre-rebuild-followup-20260610` **existe** (via `ctr`).
- **⚠️ Não reiniciar o Docker** (Live Restore = false → derrubaria 26 containers/produção). Correção segura: parar o context_builder + `pkill` dos `docker logs` órfãos.
- **Nada foi alterado** — só leitura. Ação corretiva aguarda decisão do Jordan.

*Read-only: timeout docker (images/ps/inspect/version/info), df/du, systemctl status/cat, ps/journal, ctr images ls, leitura de context_builder.py. Zero restart/prune/rm/kill/build.*
