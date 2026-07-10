# Editor de Grade por Pessoa + Fluxo Falta→Substituto — 2026-07-10

Pedido do Jordan: "Gonzaga e Paiva conseguem definir as escalas de trabalho dos AGPs, ASG,
jardineiro, artífice...? Se faltar alguém no posto, ele consegue informar no sistema e ali
mesmo selecionar ou cadastrar o substituto do dia?" → agora SIM, ponta a ponta.

## O que foi construído (backend)

### A) Editor de grade por pessoa — `/api/v1/operacional/grade/*`
`backend/modules/operacional/controllers/grade_controller.py` (novo)
- `GET /grade/postos` — postos do escopo c/ pessoas na grade.
- `GET /grade/{post_id}?mes&ano` — padrão POR PESSOA derivado dos turnos REAIS
  (12x36 diurno/noturno + paridade pares/ímpares, ou comercial 44h), dias do mês,
  férias aprovadas do DP, alocados sem grade.
- `PUT /grade/{post_id}/colaborador` — redesenha 1 pessoa a partir de uma data:
  cancela o plano futuro (nunca toca presença registrada) e regenera pela MESMA
  matemática da geração automática (12x36 paridade c/ virada em mês de 31 dias;
  comercial seg-sex 8h + sáb 4h). Propaga para meses futuros que já têm escala.
- `POST /grade/{post_id}/colaborador` — encaixa recém-admitido (ex.: Alexandre);
  cria alocação SÓ com criar_alocacao=true explícito (autoria registrada em notes).
- `DELETE /grade/{post_id}/colaborador/{employee_id}?a_partir_de` — encerra na
  grade (cancela futuros); NÃO mexe em alocação/cadastro (isso é DP/Jordan).
- Regras: escrita só GESTOR (líder 403/somente leitura); conflito em outro posto
  → 409 tudo-ou-nada com a lista de dias; férias → dias pulados; a_partir_de no
  passado → 422.

### B) Falta→substituto — `/api/v1/operacional/presenca/*`
`backend/modules/operacional/controllers/falta_substituto_controller.py` (novo)
— une as metades dormentes (shifts/mark-missed + tabela substitutions, 0 uso):
- `POST /presenca/falta/{shift_id}` — shift 'missed' + abre substitutions
  (pending). Idempotente. Bloqueios: presença/batida na janela → 409; turno de
  outro dia (>D-1) ou cancelado/completo → 422; fora do escopo → 403.
- `GET /presenca/substitutos/{substitution_id}` — sugestões REAIS: colegas de
  cargo compatível (líder↔agente) SEM turno no dia e sem férias, mesmo posto
  primeiro; diaristas ativos do Fluxo 2 com diária AUTOMÁTICA (diaria_precos,
  turno derivado do horário: ≥15h = NOTURNO).
- `POST /presenca/substituir/{substitution_id}` — funcionário: turno ESPELHO no
  posto + substituição confirmed (substituto com turno no dia → 409 "nunca dois
  postos"); diarista: lançamento em diaria_lancamentos com valor automático
  (elo do pagamento dia 15) + confirmed. Repetir → 409.
- Quadro de presença agora expõe `falta_registrada` e `substituicao`
  (pending/confirmed); falta registrada aparece como 'ausente' na hora.
- Cadastro rápido de diarista continua o existente (CPF+PIX obrigatórios).

## Provas E2E (curl × SQL) — executadas em produção e REVERTIDAS

| prova | resultado |
|---|---|
| GET grade Mirante = ditado do Jordan (6 AGPs turnos/paridades + 3 ASG 44h + férias Ediwilson) | ✅ fiel |
| líder (awsilva) PUT grade → 403; GET só vê o próprio posto (somente_leitura) | ✅ |
| PUT sem paridade → 422; a_partir_de passado → 422 | ✅ |
| PUT Chagas mesmo padrão (12x36 diurno pares) a partir de 11/07 | ✅ 26 canc/26 criados; dias jul+ago IDÊNTICOS (diff vazio) — agosto reproduziu a virada de paridade |
| POST Eduardo na grade do Prime (conflito c/ Mirante) | ✅ 409 com 26 dias listados; alocação NÃO ficou (rollback provado = 0) |
| falta Eduardo (atestado) | ✅ 201; repetir → ja_existia=true mesmo id (idempotente) |
| líder de outro posto marca falta → 403 | ✅ |
| sugestões | ✅ Ailton/Gama/Euler (Mirante, de folga — dia 10 é par) primeiro; diária AGENTE NOTURNO R$100 |
| substituir por Maiara (tem turno hoje) → 409 | ✅ "nunca dois postos no mesmo dia" |
| substituir por Ailton | ✅ turno espelho 18:00–06:00 12h noturno criado; substituição confirmed; repetir → 409 |
| quadro após falta | ✅ Eduardo 'ausente' + falta_registrada + substituicao=confirmed |
| substituir por DIARISTA (falta Anilson) | ✅ lançamento #8 R$100 AGENTE/NOTURNO no posto, observação com o elo |
| REVERSÃO total | ✅ 0 missed, 0 substitutions, 0 lançamentos de teste, nota original do shift restaurada, quadro 31 esperados de volta |

Gotcha reafirmado: `docker exec psql` com heredoc SEM `-i` ignora o stdin silenciosamente —
a 1ª reversão "rodou" sem efeito; refeita com `-i` + ON_ERROR_STOP.

## Commits
- backend: `3af14848` — controllers grade + falta_substituto + quadro c/ falta_registrada
- frontend: `1ba2e7db` — tela Grade por pessoa (~780 linhas) + fluxo no quadro de presença + menu

## Frontend — validação visual (Playwright headless, TZ Manaus, conta jjesus)
- /modulos/operacional/escalas/grade: seletor de postos reais; Gelain (default) = vazio honesto;
  Mirante = 9 pessoas com chips fiéis (Ailton 12x36·Noturno·Ímpares·18:00–06:00; Gama Diurno·Ímpares
  09:00–21:00; Ediwilson badge Férias 03/07–21/07 c/ 7 turnos; Eduardo Noturno·Pares) e
  mini-calendário marcando exatamente os dias do banco. Zero erros de console/página.
- /modulos/operacional/presenca: botão "Registrar falta" em cada linha elegível ao lado do
  check-in manual; tudo que existia preservado (contadores, aviso de sync, polling).
- Build OK, BUILD_ID container==host, público 200.

---
## Mirante das Flores — acerto pela VERDADE DAS BATIDAS (2026-07-10, tarde)
Jordan ditou as particularidades e mandou: "use as batidas de ponto como fonte da verdade".
Análise de 90d de gp_clock_punches (discriminador: entrada+saída no MESMO dia = diurno;
pontas alternadas = noturno; paridade por junho fechado — jun→jul não vira):

| pessoa | sistema tinha | batidas provaram | aplicado |
|---|---|---|---|
| Ailton | noturno ÍMPARES 18-06 | noturno PARES (02,04,06,08,10,24/06) | 18:00–06:00 pares |
| Eduardo | noturno PARES | noturno ÍMPARES (01,03...29/06+01,05/07) | 18:00–06:00 ímpares |
| Chagas | diurno 07-19 pares | diurno 06-18 (entra ~05:42, sai ~17:50; virou pares ~20/06) | 06:00–18:00 pares |
| Gama | 09-21 ímpares | idem (entra ~08:58) | sem mudança |
| Ediwilson | 07-19 pares (volta 22/07) | entra ~08:56, junho TODO em pares | 09:00–21:00 pares |
| Telma | sáb 07-11 | sáb 07-11 ✓ | sem mudança |
| Vanderlice | sáb 07-11 | sáb 12-16 (fecha o sábado) | sáb 12:00–16:00 |
| Paulo | sáb | DOMINGO 07-11 (batida 05/07) | domingos |
| Euler | 07-19 ímpares | ZERO batidas em 60d | mantido; FLAG p/ Jordan |

Os noturnos estavam com as paridades INVERTIDAS no sistema — hoje (10, par) quem entra
às 18:00 é o AILTON. Capacidade nova no editor+auto-gen: fim_de_semana (sab/dom/nenhum)
e inicio_fds (horário próprio do fds), com herança na geração do dia 25.
Cobertura provada 11-31/07: ímpares Euler+Gama+Eduardo; pares Chagas+Ailton (+Ediwilson 22/07);
vaga diurno-ímpares pós-21/07 = slot do Alexandre; ASG cobre TODOS os dias (sáb 2, dom 1).
Commit: feat grade Mirante pela verdade das batidas.
PENDENTE: bake blue/green p/ workers herdarem tasks.py (antes do dia 25) — fazer após Prime Arena.

---
## Laranjeiras Village — raio-x e adequação pelas batidas (2026-07-10)
Posto de 8 AGPs, 4/dia (2 diurnos + 2 noturnos), sem ASG. Batidas 90d confirmaram Andrea,
Anilson, Bianca e Francisco; corrigidos: **Adailson 17-05 → 18:00-06:00 ímpares**;
**Erika (líder) 07-19 → 06:00-18:00 ímpares**; **Matheus 06-18 → 05:00-17:00 ímpares**;
**Euler (cobre férias do Francisco 24/07+) 07-19 → 06:00-18:00 pares** (slot real do coberto).
Cobertura provada 11-31/07: ímpares Matheus 05h + Erika 06h + Andrea/Adailson 18h;
pares Bianca+Francisco(→Euler 24/07) 06h + Anilson/Jonathan 18h. Férias do Francisco
(23/07-21/08) respeitadas, Euler emenda certinho. FLAG: **Jonathan Mendes ZERO batidas 90d**
(cobre a Elen — mesma situação do Euler: sem badge Sólides).

---
## Raio-x em lote: Ideal, Villa Dei Fiori, V. Pássaros, Michelangelo, Gelain (2026-07-10)
27 pessoas comparadas (sistema × batidas 90d): 19 OK, 8 corrigidas, 2 flags.
- Padrão confirmado: diurnos 12x36 entram ~05:00 (04:52-05:01) também nesses postos:
  Ideal Walcicley+Livia (pares), VDF Gernanes (pares)+Ruan (ímpares), V.Pássaros
  Jeovane (pares)+Meire (ímpares) — todos 07-19 → **05:00-17:00**.
- Adeilson (Ideal) e Rene (VDF): batidas só de ~05:00 manhã = SAÍDA de noturno (P1);
  18-06/19-07 → **17:00-05:00** (padrão noturno do posto), paridades mantidas (ímpares).
- Noturnos confirmados: Jonhata/Jonilson/Maiara (Ideal), Eidy (VDF, 40d), Edward+Fernando
  Simplicio (V.Pássaros) — todos 17-05 ✓. ASGs todos OK (07-16 + sáb 07-11); Michelangelo
  100% OK (3 ASG comercial). Gelain: portaria remota, 0 escalados ✓.
- FLAGS: Daniel Souza dos Santos (Ideal, diurno ímpares) ZERO batidas 90d — 3º caso
  (Euler, Jonathan, Daniel). Domingos esporádicos (1-2 em 90d) de alguns ASG = extras
  pontuais, não padrão de escala.
