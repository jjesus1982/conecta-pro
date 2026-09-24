# DGX U2 — Férias completas como no DGX (aviso em lote, recibo timbrado, conta a pagar, cobertura)

**Data:** 24/09/2026 · **Branch:** `dgx/u2-ferias-completas` · **Módulo:** dp (`people_management/hr` + builder do DP)
**Oráculo:** `backend/scripts/orq/test_oraculo_u2_ferias_completas.py` — `TOTAL u2: 0 falha(s)` (41 checagens)

## 1. Estado antes (medido no sandbox, 24/09/2026 06:00)

- `hr_vacation_requests`: 20 solicitações (12 SUBMITTED · 5 APPROVED · 2 REJECTED · 1 CANCELLED). Colunas `gross_value`,
  `net_value`, `calculation_details`, `sell_days`, `advance_13th`, `period_id` existiam e **ninguém escrevia** nelas.
- Aviso de férias: **individual**, por dois caminhos diferentes — `POST /hr/vacations/{id}/aviso-previo` (PDF reportlab,
  layout inline no endpoint, sempre com o timbrado da Eletrônica) e a aba `aviso-ferias` (HTML via
  `ContractGeneratorService`). Nenhum lote; nenhum aviso entrava na fila de assinatura.
- Recibo de férias: **não existia** (só como tipo de documento do GED). Cálculo: só a calculadora `calcular-ferias`
  (`rd_action_ferias_calc`), que devolve uma frase e não grava nada.
- Conta a pagar da férias: **não existia**. A folha paga férias no PIX em lote sem título.
- Cobertura: F8 (`cobertura_service.registrar(motivo="ferias")`) e F5 (`cobertura_de_ferias`) existiam e funcionavam —
  mas só pela aba Operacional → Coberturas, desligadas da aprovação. `substitutions.cobertura_id` no sandbox: **0**.
- Ficha de férias por pessoa: só o MCP `ferias_funcionario`/`saldo_ferias` e a seção "férias" da ficha da T1 (6 linhas).
- `employee_alocacoes` ativas: 51, **0 com `posto_id`** — o posto do coberto tem de vir dos turnos (`shifts`).

## 2. O que o DGX tem (lacuna 6 de `docs/dgx/lacunas/dp_rh.md`)

Linha de férias com **Editar · Excluir · `GerarConta/{id}`** (forma de pagamento, vencimento, valor, centro de custo →
conta a pagar) · **Cobertura** (`/Coberturas/CoberturaColaborador?Motivo=FERIAS`); tela com **Aviso de Férias em lote**
(`POST /Ferias/LoteAvisoFerias` → PDF/Excel/Word), **Mapa de férias**, **Incluir em lote**; campos abono, 13º adiantado,
dias, aquisitivo (`01_DPRH_MODELO_DE_DADOS.md` § Férias); recusa férias com afastamento aberto (feito na T1).

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/hr/services/ferias_dgx.py` (novo) | A regra: `ensure` (DDL), `carregar`/`calcular` (a MESMA sequência da calculadora), `story_aviso` (página do aviso, compartilhada), `pdf_aviso`/`pdf_aviso_lote` (emenda com PyMuPDF — cada página com o empregador da pessoa), `enfileirar_aviso` (helper do holerite), `pdf_recibo`, `gerar_conta` (`PayableService`), `registrar_cobertura` (F8 → F5), `postos_do_periodo`, `descobertos`, `ficha`. |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_u2_ferias.py` (novo) | Telas e rotas (abaixo). |
| `backend/modules/people_management/hr/controllers/vacation_controller.py` | `gerar_aviso_previo_ferias` passa a montar a página por `ferias_dgx.story_aviso` (−74 linhas de layout inline) e a usar o empregador por CPF × competência (antes: sempre Eletrônica). Mesma rota, mesmo PDF. |
| `backend/modules/operacional/controllers/redesign_builders/departamento_pessoal.py` | 3 imports + `include_router` + `_telas_u2` (antes de `montar_grupos`) + `_mapa_descobertos_u2` (depois da frente 08). 7 linhas. |
| `backend/modules/operacional/controllers/redesign_builders/_dp_grupos.py` | Abas no FIM do g-ferias: `aviso-ferias-lote`, `ferias-pessoa`. |
| `backend/modules/signatures/helpers/solicitar_assinatura_documento.py` | 1 linha de política: `"aviso_ferias": [EMPLOYEE]` (sem ela o helper devolve None e nada entra na fila). Toque fora do módulo, declarado. |
| `backend/scripts/orq/test_oraculo_u2_ferias_completas.py` (novo) | Oráculo (§4). |

**DDL** (`ferias_dgx.ensure`, idempotente, roda no 1º acesso à tela ou à ação):
```sql
ALTER TABLE hr_vacation_requests ADD COLUMN IF NOT EXISTS payable_id uuid;
ALTER TABLE hr_vacation_requests ADD COLUMN IF NOT EXISTS cobertura_id uuid;
ALTER TABLE hr_vacation_requests ADD COLUMN IF NOT EXISTS aviso_gerado_em timestamptz;
```

**Telas** (grupo `g-ferias`, `/redesign/departamento-pessoal?t=<id>`):

- `ferias` — **sobrescreve** a tabela do builder (mesma fonte/ordem; colunas novas Conta · Cobertura). Por linha:
  - SUBMITTED: **Aprovar** (campos opcionais *Substituto* e *Posto coberto* → `POST /action/ferias-aprovar-u2?vid=`, que
    reusa `ferias-aprovar` — parede de escopo + `approve_vacation` + evento GEDEON — e, com substituto, registra a
    cobertura F8/F5; sem substituto, a resposta diz «Posto X ficará DESCOBERTO de A a B»), Rejeitar, Cancelar.
  - APPROVED: docs **Recibo (PDF)** (`GET /api/v1/redesign/ferias/{id}/recibo/pdf`) e **Aviso (PDF)**
    (`GET …/ferias/{id}/aviso/pdf`); ações **Gerar conta** (`gated` + `confirm`, some quando já gerada), **Cobertura**
    (some quando já registrada), Cancelar.
  - Campos das ações iguais em todas as linhas → o dedup do redesign manda o select de substituto uma vez (tela em 44 KB).
- `aviso-ferias-lote` — mês de gozo (só meses com férias aprovadas) · cliente · função · «enfileirar para assinatura»
  → `POST /action/aviso-ferias-lote` → abre `GET /api/v1/redesign/ferias/aviso-lote/pdf?mes=AAAA-MM[&cliente&cargo]`
  (UM PDF, uma página por pessoa, cada página com o CNPJ da pessoa). Com «sim», grava `/uploads/ferias/aviso_<id>.pdf`
  e abre 1 `sig_signature_requests` (`aviso_ferias`, só o funcionário) por aviso — idempotente.
- `ferias-pessoa` — form + painel: saldo (`VacationService.calculate_vacation_balance`, o mesmo do MCP `saldo_ferias`),
  posição no mapa do art. 133 (frente 08), períodos de `hr_vacation_periods`, cada gozo com aviso/conta/cobertura/link
  do recibo, avisos na fila de assinatura.
- `mapa-ferias` (frente 08, intocada) ganha o painel **«Postos descobertos — férias aprovadas sem cobertura»**.

**Recibo**: dados do empregado, período aquisitivo (de `hr_vacation_periods` quando a férias tem `period_id`; senão a
mesma derivação do aviso de hoje), gozo/retorno/abono/13º adiantado/pagar até (art. 145), demonstrativo (férias, 1/3,
abono e 1/3 do abono se houver, INSS, IRRF, líquido) — **os números são os da calculadora `calcular-ferias`** (mesmas
funções, mesma ordem); assinatura só do funcionário; timbrado do empregador por CPF × competência (Patrimonial para
EIDY, conferido no PDF).

**Conta a pagar**: `PayableService.create_account` (o da tela «Registrar conta»/T4), condomínio da empresa, `gross_value`
= líquido, `due_date` = início − 2 dias **corridos** (art. 145 diz "até 2 dias antes"; a lei não fala em úteis — se o
prazo já passou, vence hoje e as notas guardam o prazo legal), `document_number` = `request_code`, favorecido = nome do
colaborador, PIX nas notas. Uma conta por férias (`payable_id`; 2ª chamada → 409). **Não paga**.

## 4. Oráculo

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" --tmpfs /app/logs:rw,uid=999,gid=999 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_u2_ferias_completas.py
```
(`uid=999` no tmpfs: a imagem roda como `erp`; sem isso `enfileirar_aviso` não consegue gravar o PDF.)

**Vermelho (antes do código, 06:21):**
```
FALHOU: frente U2 não importa: cannot import name '_dgx_u2_ferias' from 'modules.operacional.controllers.redesign_builders'
TOTAL u2: 1 falha(s)
```

**Verde (depois, 06:40):**
```
  ✓ build() chama _telas_u2 antes de montar_grupos
  ✓ build() chama _mapa_descobertos_u2 depois da frente 08
  ✓ abas no FIM do g-ferias: ['aviso-ferias-lote', 'ferias-pessoa']
  ✓ política: aviso_ferias assinado só pelo funcionário
  ✓ aviso individual (vacation_controller) reusa o mesmo layout do lote (ferias_dgx.story_aviso)
fixture: CARLOS EDUARDO DA SILVA FAÇANHA de férias 01/10 a 05/10 no posto 93a99142 · substituto ADAILSON SERRA ALVES
  ✓ aprovar sem substituto avisa posto descoberto: … Posto Condomínio Prime Arena ficará DESCOBERTO …
  ✓ férias aprovada (APPROVED) e ainda sem cobertura
  ✓ a férias aparece na lista de postos descobertos
  ✓ cobertura_id gravado na férias
  ✓ 5 linhas de substitutions (motivo vacation) com o cobertura_id: 5/5 — o que a aba Coberturas (F8) lista
  ✓ 1 movimentação da F5 (cobertura_de_ferias) do substituto cobrindo o coberto: 1
  ✓ com cobertura, sai da lista de descobertos
  ✓ 2ª cobertura recusada com 409
  ✓ líquido do recibo 343.28 == líquido da calculadora ferias-calc 343.28 (Δ 0.00)
  ✓ recibo usa os dias da férias (5) e o salário do cadastro (1670.00)
  ✓ recibo começa com %PDF · em 1 folha · traz o nome · traz o líquido 343,28
  ✓ payable_id da férias aponta para uma conta a pagar
  ✓ gross_value 343.28 == líquido 343.28
  ✓ vencimento 2026-09-29 == início − 2 dias corridos (art. 145) 2026-09-29
  ✓ conta nasce NÃO paga (status pendente)
  ✓ document_number == request_code (FER-DP-20BFD746)
  ✓ 2ª chamada recusada com 409 · contas com o request_code da férias: 1
  ✓ férias aprovadas no mês 2026-10: serviço 1 == SQL 1
  ✓ lote começa com %PDF · lote tem 1 página(s) para 1 pessoa(s) · lote de 2 ids emenda 2 páginas: 2
  ✓ ação devolve o PDF do lote: /api/v1/redesign/ferias/aviso-lote/pdf?mes=2026-10
  ✓ 1 pedido de assinatura do FUNCIONÁRIO para o aviso: ['employee']
  ✓ o pedido aponta para um PDF que existe em disco (é o que a assinatura estampa)
  ✓ gerar o lote de novo não duplica o pedido de assinatura: 1
  ✓ ficha de férias lista o gozo da fixture · ficha mostra a conta a pagar do gozo
  ✓ férias com afastamento aberto recusada com 409
  ✓ telas montadas (faltam: []) · linha da férias aprovada tem o botão Recibo (PDF)
  ✓ fixtures apagadas (sobra 0)
TOTAL u2: 0 falha(s)
```

Regressão: `test_oraculo_mapa_ferias.py` → `OK mapa de férias` · `test_oraculo_dgx_t1_dp.py` → `TOTAL dgx t1: 0 falha(s)`
(rodado depois da refatoração do `vacation_controller`).

HTTP (container `teste-dgx-u2`, porta 8232, parado ao fim): `GET /redesign/data/departamento-pessoal` → g-ferias com as
10 abas (as 2 novas no fim), `ferias` com 5 aprovadas × [Recibo, Aviso] e 12 pendentes com Aprovar (`fieldsRef`
deduplicado), `mapa-ferias` com o 4º painel; `GET …/ferias/7569b3a2…/recibo/pdf` → 200 %PDF (1 página, Patrimonial,
líquido R$ 2.050,58 = 30 dias de R$ 1.670,00); `…/recibo/pdf` de uma SUBMITTED → 409; `GET …/aviso-lote/pdf?mes=2026-08`
→ 200, retorno 06/09/2026; `POST /hr/vacations/{id}/aviso-previo` (rota antiga) → 200 %PDF; `POST /action/ferias-pessoa`
→ saldo 35/30/5, mapa, período, gozo com link do recibo.

## 5. O que NÃO foi feito e por quê

- **Nada muda no cálculo**: `calculo_service` (rubricas 0060/0061) e `clt_calculator` intocados; o recibo REPETE a
  calculadora. `gross_value`/`net_value`/`calculation_details` da tabela continuam vazios — gravar ali seria uma segunda
  fonte para o mesmo número; se um dia a folha passar a ler dali, é decisão do dono (§7).
- **13º adiantado** sai como SIM/NÃO no aviso e no recibo, sem valor: a calculadora não o apura e eu não invento.
- **Vencimento em dias corridos**: art. 145 diz "até 2 dias antes do início" sem falar em úteis. Documentado no serviço
  (`DIAS_ANTES_PAGAMENTO`) e no oráculo. Se o prazo já passou ao gerar, vence hoje.
- **Conta sem `empresa_id`/categoria/centro de custo** (o DGX pede forma de pagamento, centro de custo, plano de contas):
  o `PayableAccountCreate` da tela «Registrar conta» também não os exige; quem classifica é o Financeiro.
- **Cobertura fora da janela da F8** (±60 dias de hoje, ≤ 62 dias): férias aprovada com mais de 60 dias de antecedência
  não registra cobertura na hora — a resposta diz isso e a linha mantém a ação **Cobertura** para depois. Não afrouxei a
  régua da F8.
- **Período aquisitivo sem `period_id`**: só 0 das 20 férias têm `period_id`; sem ele uso a mesma derivação do aviso de
  hoje (início − 1 ano). A régua certa (âncora do art. 133 com afastamento > 6 meses) está no mapa da frente 08, mas
  ligar a aprovação a `hr_vacation_periods` (`days_used`, `period_id`) é o que a FRENTE_08 §5 já deixou para o dono.
- **`return_date` do banco ignorado no papel**: nas férias vindas do Sólides vem igual ao fim (EIDY: fim 05/09, retorno
  05/09). O aviso individual sempre imprimiu fim + 1; mantive. Corrigir o dado é outra frente.
- **Excel/Word do aviso** (o DGX oferece): só PDF — é o que o padrão-ouro da casa gera.
- **Recibo na fila de assinatura**: não enfileirei (o brief pedia só o aviso). Decisão do dono (§7).
- **`aviso-ferias` (HTML, ContractGeneratorService)** continua existindo ao lado do PDF; não apaguei nada.
- Sem `frontend/`, `alembic/`, `checar_regressao.py`, `_frente_*`, `calculo_service.py`, Telegram, pagamento.

## 6. Como o Jordan testa amanhã (depois do bake)

1. DP → **Férias & Afastamentos → Férias**: numa linha *Aprovada*, clique **Recibo (PDF)** → abre o recibo timbrado;
   compare o líquido com **Calcular (CLT)** para a mesma pessoa, 30 dias, 0 abono — tem de bater ao centavo.
2. Na mesma linha, **Gerar conta** → confirme → «Conta a pagar de R$ … vencendo DD/MM (art. 145)». Financeiro → Pagar
   mostra a conta (não paga). Clique **Gerar conta** de novo: a ação sumiu da linha; pela API dá 409.
3. Numa linha *Pendente*, **Aprovar** escolhendo um substituto → «Cobertura registrada: N dia(s) … Movimentação (F5)
   criada». Operacional → Coberturas lista o período; Movimentações mostra `cobertura de férias`. Sem substituto → a
   mensagem diz de quando a quando o posto fica descoberto, e o **Mapa de férias** ganha a pessoa no painel «Postos
   descobertos».
4. **Aviso em lote**: mês de gozo, «enfileirar: sim» → abre o PDF com uma página por pessoa; o colaborador vê o aviso na
   fila de assinatura do Meu Espaço (só ele assina).
5. **Ficha de férias**: escolha a pessoa → saldo, mapa, períodos, gozos (com conta/cobertura/recibo) e avisos a assinar.
6. Oráculo em produção: `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_u2_ferias_completas.py`
   → `TOTAL u2: 0 falha(s)` (cria e apaga as próprias fixtures `FIXTURE DGX U2`; escolhe coberto/substituto do dia
   +5 com turno em posto ligado a condomínio — se não houver par livre, avisa e sai vermelho sem gravar nada).

## 7. Decisões que só o dono pode tomar

1. **Persistir o cálculo na férias** (`gross_value`/`net_value`/`calculation_details`) na aprovação, para a folha e o
   recibo lerem a mesma foto? Hoje o recibo recalcula pela calculadora a cada abertura (mesmo salário → mesmo número).
2. **13º adiantado com valor**: a calculadora não apura; a folha da competência apura. Quer que o recibo mostre o valor
   do 13º junto (e a conta a pagar o inclua)?
3. **Recibo de férias na fila de assinatura** (como o holerite)? Um `document_type` a mais na política.
4. **Conta a pagar por empresa (Eletrônica × Patrimonial)** e categoria/centro de custo padrão para férias.
5. **`return_date` das férias do Sólides** igual ao fim: corrigir o dado (fim + 1) na fonte?
6. **Ligar aprovação ↔ `hr_vacation_periods`** (`period_id`, `days_used`): é o que faz o período aquisitivo do recibo sair
   da régua do art. 133 em vez da derivação "início − 1 ano".
