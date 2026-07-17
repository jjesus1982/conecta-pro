# Módulo Ponto — Lapidação + preparação para o ponto próprio (01/08)
**Conecta PRO · 17/07/2026 · commit `043ed40d` · missão: "todo mundo batendo ponto pelo
Conecta PRO a partir de 01/08, informações em tempo real, sem delay"**

---

## 1. Diagnóstico da FONTE atual (por que existe delay hoje)
O endpoint do Tangerino/Sólides (`payssego/punches`) **só expõe a apuração (D-1)** —
consultado ao vivo às 23:4x de 16/07, devolvia 404 até para 15/07 em vários funcionários;
o sync (a cada 15 min) rodava "com sucesso" atualizando os MESMOS 182 pares há 22h.
**Tempo real via pull do Tangerino é impossível** — não é bug nosso, é limite da fonte.
O ponto próprio (01/08) resolve na raiz. ✔ Diagnóstico confirmado por consulta direta à API.

## 2. BUG-RAIZ: dois fusos na mesma coluna (o que quebrava as telas)
`gp_clock_punches.punch_timestamp` tinha DOIS escritores com convenções diferentes
(sync=UTC-like; portal=hora local) e leitores divididos: o Operacional convertia
UTC→Manaus (certo p/ o acervo), o módulo Ponto lia CRU como local. Efeitos visíveis:
- **Espelho +4h**: entrada 07:00 real aparecia 11:00; padrão 44h (07-16h) parecia 11-20h.
- **Batidas noturnas caíam no dia seguinte** → `presentes_hoje: 0` à noite.
- **Banco de horas com débito fantasma** (janelas noturnas 22-05h calculadas no fuso errado).

**Convenção canônica adotada: UTC na coluna** (bate com ~5.300 linhas do acervo, com a
presença ao vivo do Operacional e com o eSocial). Correções:
- **17 sites de leitura** convertidos (`AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus'`):
  dashboard (presentes/em-aberto/intrajornada), espelho (ORM+SQL), banco de horas,
  folha-PDF, time_tracking/time_record, próximo-tipo-de-batida, operacional/ai.
- **`to_dict` do punch = choke point de apresentação** → toda tela/API exibe hora local.
- **Writer canônico**: batida própria grava `utcnow()`; timestamp vindo do device
  (offline/app) é convertido local→UTC (+4h fixo — Manaus não tem horário de verão).
- 1 batida legada do app (13/07, gravada local) reparada (+4h).

**Prova (oráculo)**: espelho de julho passou de `11:00/15:00/16:00/20:05` para
`07:00/11:00/12:00/16:05` — o padrão real do contrato 44h.

## 3. Batida própria — TEMPO REAL PROVADO ponta a ponta
```
POST /ponto/batida  →  banco grava 04:13 UTC  →  API exibe 00:13 local
                    →  dashboard presentes_hoje incrementa NO MESMO SEGUNDO
```
(batida de teste removida após a prova). Infra já existente na tabela: facial_match/
liveness, foto, geofence Haversine por posto, offline-sync, status pending→approved (DP).

## 4. Bugs de tela corrigidos
| Tela | Bug | Fix |
|---|---|---|
| /batida | **Geolocalização BLOQUEADA** por `Permissions-Policy: geolocation=()` (ninguém conseguiria bater ponto com localização) | `geolocation=(self)` no next.config (mesmo gotcha da câmera) |
| /justificativas | 422 em toda carga (`hr/employees?page_size=200`; máx=100) → tela vazia | page_size=100 |
| /atrasos | Coluna Colaborador toda `--` (payload traz `employee_nome`; tela lia outro campo) | lê `employee_nome` |

## 5. Pré-requisito organizacional de 01/08 — JÁ ESTÁ OK
**50/50 funcionários ativos têm e-mail no cadastro E login correspondente** no sistema
(o vínculo batida→funcionário é pelo e-mail do login). Nada a providenciar.

## 6. Provas e artefatos
- `backend/tests/ponto_release/` — **4/4 PASS**: espelho em hora local; E2E da batida
  (UTC no banco + local na API + dashboard na hora, com cleanup); inconsistências com
  nome; page_size. 
- `scripts/qa_ponto_browser.py` — QA de browser permanente (sweep 7 telas + espelho
  local + atrasos com nome + batida sem bloqueio de geo).
- Deploy durável: blue/green backend + build/imagem frontend.

## 7. Pendências conhecidas / decisões para o Jordan
- **Banco de horas com débito alto (~-40h/func)**: parte é real (faltas/fonte), parte é a
  defasagem D-1 do Tangerino (dias 14-16 incompletos subestimam o trabalhado). Com o
  ponto próprio em tempo real isso se corrige sozinho a partir de 01/08.
- `presentes_hoje` continuará 0/latente ENQUANTO a fonte for o Tangerino (D-1) — honesto,
  não é bug. Vira tempo real em 01/08.
- Fluxo do funcionário em 01/08: cada colaborador loga com o próprio e-mail e usa
  /ponto/batida — a tela detecta o tipo (entrada/almoço/retorno/saída) sozinha, valida
  geofence do posto e registra como 'pending' para conferência do DP.
