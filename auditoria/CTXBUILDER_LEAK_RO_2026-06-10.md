# context_builder.py — como é disparado e o que alimenta (READ-ONLY) ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-CTXBUILDER-RO
- **Modo:** 100% READ-ONLY — nada parado/morto/editado. Só descoberta do mecanismo.
- **Veredito:** disparado por **cron a cada 2 min** (one-shot). Matar o PID **NÃO resolve** (renasce ≤2min). A fonte exata do leak é **uma única função** (`collect_error_logs`, linhas 192-200). Parada segura = neutralizar essa função **ou** comentar a linha do cron.

---

## STEP 1 — Como é disparado
- **Cron do root** (crontab -l):
  ```
  # Context Builder para assistente Telegram (a cada 2 min)
  */2 * * * * python3 /opt/conecta-pro/agents/context_builder.py > /dev/null 2>&1
  ```
- **One-shot, sem loop:** `if __name__ == "__main__": build_context()` (linha 341). Sem `while True`/`sleep` interno. O PID 15630 do diag **já saiu** — cada execução dura segundos e o cron relança a cada 2 min.
- **Nenhum outro caller:** grep por `context_builder` em agents/scripts/rotinas = **nada** além do cron. Não é filho de supervisor/tmux/loop python — **só o cron**.
- **Consequência:** `kill 15630` é inútil (já morreu). Para parar de verdade → **desabilitar o cron** ou **neutralizar a função que vaza**.

## STEP 2 — O que ele alimenta
- **Produz:** `agents/system_context.json` (mtime 18:55, ~14KB, atualizado a cada 2 min). 11 coletores:
  `containers, server, interventions, patterns, prometheus_alerts, error_logs, knowledge_base, cron_status, celery_queues, recent_events`.
- **Propósito:** snapshot situacional para o **assistente Telegram** (contexto que o bot lê quando o Jordan pergunta). **Best-effort**, não é caminho de produção/dados.
- **Consumidor:** **nenhum leitor agendado** de `system_context.json` foi encontrado no repo (só `.gitignore` e um doc de sprint o mencionam). É **gerado** a cada 2 min e lido **sob demanda** pelo bot Telegram. → Se o builder parar, o snapshot fica **velho**; **nada em produção quebra**.
- **A função que vaza (linhas 192-200):**
  ```python
  def collect_error_logs():
      critical = ["conecta-pro-backend", "conecta-pro-postgres", "conecta-pro-redis"]
      logs = {}
      for c in critical:
          out = run(f"docker logs {c} --tail 5 2>&1 | grep -iE 'error|...' | tail -3")
          logs[c] = out.splitlines() if out else ["(sem erros recentes)"]
      return logs
  ```
  Saída = lista de linhas de erro recentes por container, com fallback `"(sem erros recentes)"`. **Enriquecimento puro best-effort** — os outros 10 coletores **não dependem** dela. Neutralizar só ela → o `system_context.json` continua completo, exceto a chave `error_logs`.
- **`run()` (linhas 26-28):** `subprocess.run(cmd, shell=True, timeout=15)`. No `TimeoutExpired` mata só o `/bin/sh -c`, **não o neto `docker logs`** → órfão (este é o bug que gera o leak).

## STEP 3 — Outros leakers / contagem
- **Órfãos `docker logs` agora: 498** (era **416** no diag anterior) → **+82, crescendo** (~1/min). Confirma leak ativo.
  - **245 `conecta-pro-postgres` + 245 `conecta-pro-redis`** (= os dois alvos do `collect_error_logs` que travam o `docker logs`).
  - **`conecta-pro-backend` = 0** órfãos → o `docker logs` do backend retorna rápido; só postgres/redis penduram (logs maiores).
  - **~20 antigos estáticos** (8 baileys-api, 5 evolution-api, 4+2+1 chatwoot-*) — resíduo de **sessões claude antigas** (>2d), PPID=1, processo-pai morto → seguros de ceifar; **não crescem**.
- **`zombie_cleaner.sh`** roda no cron (*/15 e */30) mas **NÃO pega** esses órfãos — eles estão `Sl` (vivos, presos no daemon), **não `Z` (defunct)**.

---

## STEP 4 — Respostas

**a) Disparado por quê? Matar o PID resolve?**
Por **cron** (`*/2 * * * * python3 .../context_builder.py`), **one-shot**. **Matar o PID NÃO resolve** — renasce em ≤2 min. Parada real: **(i)** comentar a linha do cron, **ou** **(ii)** neutralizar `collect_error_logs`.

**b) O que quebra se eu parar?**
Só o **frescor** do `system_context.json` (snapshot do assistente Telegram). **Best-effort, não-crítico** — nenhum consumidor agendado, nenhum caminho de produção. Containers/postgres/backend seguem intactos.

**c) A linha 192-200 (docker logs) é essencial?**
**Não.** É enriquecimento best-effort (fallback "(sem erros recentes)"). Pode ser neutralizada **sem quebrar** os outros 10 coletores — só a chave `error_logs` ficaria vazia/estática.

**d) Contagem atual de órfãos:** **498** (vs 416) — crescendo ~+1/min. 245 postgres + 245 redis (ativos) + ~20 antigos (estáticos).

**e) RECOMENDAÇÃO de parada segura (menos→mais invasiva) — NÃO executei:**
1. 🥇 **Cirúrgico (Chesterton, quebra menos):** neutralizar **apenas** `collect_error_logs` — comentar o loop `docker logs` (ou fazer `return {}`). Mantém o context_builder e o `system_context.json` 100% funcionais, menos a chave `error_logs`. **Para o leak na fonte exata.** (Edit de 1 função em `agents/` — fora das forbidden zones do rebuild, mas é mudança → sob aval.)
2. 🥈 **Zero código:** comentar a linha do cron `*/2 ... context_builder.py`. Para o builder inteiro; `system_context.json` fica velho (best-effort); 100% reversível (descomentar). Mais amplo, mas sem tocar código.
3. 🔧 **Fix permanente do bug raiz:** em `run()`, usar `subprocess.run(..., start_new_session=True)` + `os.killpg(os.getpgid(proc.pid), SIGKILL)` no `TimeoutExpired` (mata o grupo todo, incl. o neto `docker logs`). Resolve o leak de forma definitiva sem perder o `error_logs`.
4. ⚠️ **Em qualquer caso:** parar a fonte **previne novos**, mas os **498 órfãos já existentes permanecem** e seguem saturando o dockerd → precisam ser **ceifados** (`pkill -f 'docker logs conecta-pro-(redis|postgres) --tail 5'`) para destravar `docker images`/`ps`. (Inócuo aos containers; é a ação do diag anterior.)

> **Ordem segura proposta (para o Jordan decidir):** (1) parar a fonte [opção 1 ou 2] → (2) `pkill` dos 498 órfãos → (3) validar `docker images` destravado → (4) opcional: aplicar o fix permanente [opção 3] antes do rebuild. **Sem reiniciar o dockerd** (Live Restore=false derrubaria produção).

---

## Resumo
- **Disparo:** cron `*/2` (one-shot) — matar PID não adianta; renasce. **Fonte do leak isolada:** `collect_error_logs` (linhas 192-200), `docker logs postgres/redis --tail 5`.
- **Alimenta:** `agents/system_context.json` (assistente Telegram) — **best-effort, sem consumidor agendado, nada de produção depende**.
- **Menos invasivo:** neutralizar só `collect_error_logs` (mantém o resto) **ou** comentar o cron (zero código). Ambos + `pkill` dos 498 órfãos.
- **Bug raiz:** `run()` não mata o neto no timeout → fix com `start_new_session`+`killpg`.
- **Nada alterado** — só leitura. Correção aguarda decisão do Jordan.

*Read-only: ps/árvore, crontab -l, leitura de context_builder.py (entry/collect_error_logs/run), grep de consumidores, stat. Zero kill/pkill/edit/restart.*
