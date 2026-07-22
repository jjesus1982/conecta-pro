# ACHADO SISTÊMICO — Timezone das batidas (gp_clock_punches) — 2026-07-22

## Verdade do banco (provada)
- Container backend roda em **TZ=America/Manaus (-04)**.
- Import Tangerino (`modules/integrations/connectors/solides/tasks.py`) grava a batida via
  `datetime.fromtimestamp(ts/1000)` **sem tz** → resultado é naïve no horário LOCAL do container
  = **Manaus**. Logo `gp_clock_punches.punch_timestamp` (tipo `timestamp without time zone`)
  **JÁ ESTÁ EM HORÁRIO DE MANAUS** para esses registros.
- Sessão do Postgres = UTC (por isso `AT TIME ZONE 'America/Manaus'` sobre um valor naïve-Manaus
  retorna +4h errado).

## Prova (EDUARDO OLIVEIRA DE SOUZA)
| Fórmula | Valor | Correto? |
|---|---|---|
| raw `to_char(punch_timestamp,...)` | **22/07 06:07** | ✅ (bate clássico; turno 18:00→06:07 12x36) |
| `punch_timestamp - interval '4 hours'` | 22/07 02:07 | ❌ (-4h a mais) |
| `punch_timestamp AT TIME ZONE 'America/Manaus'` | 22/07 10:07 | ❌ (+4h) |

Clássico `/modulos/campo/checkin` exibe **raw** (06:07) e está **correto**.

## Regra de exibição (para TODA tela que mostra batida)
**Exibir o raw `punch_timestamp` diretamente** (`to_char(p.punch_timestamp,'DD/MM HH24:MI')`).
NÃO subtrair 4h, NÃO usar `AT TIME ZONE 'America/Manaus'` (ambos deslocam 4h).

> Ressalva: o caminho FACIAL (`punch_service.py:130` `datetime.fromisoformat(...)`) pode gravar
> diferente conforme o que o client envia. Se aparecerem batidas faciais com horário deslocado,
> tratar caso a caso — mas o padrão atual (Tangerino, maioria) é Manaus-naïve = exibir raw.

## Correções
- [x] **T1 / campo.py** `checkin` — removido o `- interval '4 hours'`, exibe raw. (este commit)
- [ ] **GP owner** `redesign_data_controller.py:1044` (`_build_gp` → tela `ponto`) usa
  `AT TIME ZONE 'America/Manaus'` (+4h). Trocar por raw `to_char(p.punch_timestamp,'DD/MM HH24:MI')`.
  NÃO editei (território de outro terminal / arquivo base compartilhado).
