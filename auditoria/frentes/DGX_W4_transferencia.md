# DGX W4 — Transferência de colaborador entre as empresas do grupo (24/09/2026)

**Branch:** `dgx/w4-transferencia` (base `98961d795`) · **Módulo:** dp (+ 1 linha em `operacional/services/movimentacao_service.py`)
**Sessão:** agent-w4 · **Container efêmero:** `teste-dgx-w4`, porta 8254, sandbox `conecta_pro_staging` (**parado ao fim**)
**Produção:** não tocada. A DDL do `_ensure` (§3) aplica em produção no 1º acesso à tela, depois do bake.
**Lacuna:** `docs/dgx/lacunas/dp_rh.md` item **#22** — `/Colaboradores/Index`: **Transferir (filial destino)**.

---

## 1. Estado antes (medido no sandbox, 24/09/2026 10:00)

### 1.1 Quem o espelho do eSocial mostra como desligado, e o que o sistema sabe deles hoje

Os 5 S-2299 que o governo devolveu (`esocial_eventos_espelho`, espelho lido até **22/09/2026**),
cruzados com `employees`. Motivos **10 e 11** (tabela 19) são transferência — o vínculo NÃO acaba:

| Nome | CPF | S-2299 | mtv | Status aqui | Admissão | Demissão aqui | Empresa aqui | Aloc. ativas | Períodos de férias |
|---|---|---|---|---|---|---|---|---|---|
| **GEILSON RODRIGUES DE ANDRADE** | 029.969.132-21 | **30/06/2026** | **11** | **ativo** | 22/03/2026 | **—** | **PATRIMONIAL** | 1 | 0 |
| MARCELINO AURISMAR DA SILVA | 657.269.602-20 | 29/06/2026 | 33 | demitido | 08/12/2025 | 29/06/2026 | Eletrônica | 0 | 1 |
| MARTA DA SILVA PINHEIRO | 027.172.782-90 | 08/06/2026 | 07 | demitido | 01/07/2025 | 09/06/2026 | Eletrônica | 0 | 2 |
| LORINALDO OLIVEIRA DA SILVA | 710.718.362-18 | 01/06/2026 | 07 | demitido | 01/08/2025 | 02/06/2026 | Eletrônica | 0 | 1 |
| THAIS FERREIRA MATOS | 047.232.672-47 | 02/05/2026 | 02 | demitido | 22/04/2026 | 11/06/2026 | Eletrônica | 0 | 2 |

**Uma pessoa transferida no governo: o GEILSON.** Os outros quatro são desligamento de verdade
(33 = falecimento, 07 = pedido de demissão, 02 = sem justa causa) e o sistema já os tem demitidos.

O que o sistema sabia do GEILSON antes desta frente: **`empresa_id` já apontava para a
PATRIMONIAL** — alguém corrigiu a empresa no cadastro em algum momento — mas **não havia
registro nenhum de que houve transferência**: nem data, nem motivo, nem quem efetivou, nem
rastro dos dois eventos de eSocial. A única prova da transferência morava no espelho do governo,
e a `conferencia_esocial` (22/09) só a reportava dentro de um bloco de texto do fluxo de
pagamento — **nenhuma tela do DP mostrava isso**.

### 1.2 O que existia e o que não existia

- **Não existia** `dp_transferencias`, nem serviço, nem tela, nem ação. Zero linhas de código
  com "transferência entre empresas" fora do comentário de `conferencia_esocial._MOTIVOS_TRANSFERENCIA`.
- **Existia e foi reusado:** `empresas` (2 linhas: `conecta_eletronica` 35.710.481/0001-03 e
  `conecta_patrimonial` 66.014.833/0001-10) · `employees.empresa_id` (75 na Patrimonial, 29 na
  Eletrônica) · `esocial_transmissao_propostas` (fila de rascunho humana do orquestrador, status
  `proposto`, índice único parcial de idempotência) · `movimentacao_service` (F5) ·
  `conferencia_esocial._MOTIVOS_TRANSFERENCIA` (`{"10","11"}`) · `cct_cargos` (F2/T1) ·
  `hr_vacation_periods`, `employee_dp.dependentes`, `time_bank`, `hr_employee_documents`.
- **Baseline para o oráculo:** `termination_processes` = 3, `admission_processes` = 1,
  `esocial_eventos_espelho` = 416, `eventos_esocial` = 0, máx. de alocações ativas por pessoa = 1.

### 1.3 Oráculo VERMELHO no nascimento

```
  ✗ (a) serviço transferencia não importa: ImportError: cannot import name 'transferencia' from 'modules.people_management.hr.services'
  ✗ (a) dp_transferencias: colunas faltando ['employee_id', 'empresa_origem_cnpj', 'empresa_destino_cnpj', 'data', 'motivo', 'mantem_admissao', 'novo_cargo_id', 'novo_salario', 'observacao', 'status', 'esocial_s2299_id', 'esocial_s2200_id', 'efetivada_por', 'efetivada_em']
TOTAL falhas transferência W4: 2
exit=1
```

---

## 2. O que o DGX tem

`/Colaboradores/Index` traz, ao lado de Exportar/Imprimir/Alocações, o botão **Transferir** com
escolha da **filial destino**. É a operação que reconhece que um grupo empresarial tem mais de um
CNPJ e que a pessoa anda entre eles sem sair do grupo. No DGX a transferência não passa pela tela
de Demissão — e é exatamente essa separação que faltava aqui.

O que a legislação exige por trás (e o DGX assume): **S-2299 com `mtvDeslig` 10 ou 11 na origem**
e **S-2200 com `tpAdmissao` 2 ou 3 e bloco `sucessaoVinc` no destino**, mantendo o vínculo
contínuo — `dtAdm` continua sendo a admissão ORIGINAL; `sucessaoVinc.dtTransf` é a data da
transferência. Não há TRCT, não há verba rescisória, o período aquisitivo de férias não reinicia.

---

## 3. O que foi feito

### 3.1 Arquivos

| Arquivo | O que é |
|---|---|
| `backend/modules/people_management/hr/services/transferencia.py` | **novo** — a regra: `_ensure`, `simular`, `criar`, `efetivar`, `cancelar`, `regua` |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_w4_transferencia.py` | **novo** — 4 telas + 4 ações |
| `backend/scripts/orq/test_oraculo_w4_transferencia.py` | **novo** — o oráculo (§4) |
| `.../redesign_builders/departamento_pessoal.py` | +4 linhas — `include_router` e `telas(db, out)` antes de `montar_grupos` |
| `.../redesign_builders/_dp_grupos.py` | +4 linhas — as 4 abas ao FIM de `g-admissao` |
| `.../redesign_builders/_dgx_t1_dp.py` | ficha do colaborador ganha a seção **`transferencias`** (16ª) |
| `backend/modules/operacional/services/movimentacao_service.py` | **+1 motivo** em `MOTIVOS`: `transferencia_de_empresa` |
| `backend/scripts/orq/test_oraculo_dgx_t1_dp.py` | a lista de seções esperadas da ficha passa de 15 para 16 |

### 3.2 DDL que o `_ensure` aplica em produção no 1º acesso

```sql
CREATE TABLE IF NOT EXISTS dp_transferencias (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL,
  empresa_origem_cnpj varchar(18), empresa_destino_cnpj varchar(18) NOT NULL,
  data date NOT NULL, motivo varchar(2) NOT NULL DEFAULT '10',
  mantem_admissao boolean NOT NULL DEFAULT true,
  novo_cargo_id uuid, novo_salario numeric(12,2), observacao text,
  status varchar(12) NOT NULL DEFAULT 'rascunho',
  esocial_s2299_id uuid, esocial_s2200_id uuid,
  criado_por uuid, criado_em timestamp DEFAULT (now() AT TIME ZONE 'America/Manaus'),
  efetivada_por uuid, efetivada_em timestamp, cancelada_por uuid, cancelada_em timestamp);
CREATE INDEX IF NOT EXISTS ix_dp_transferencias_emp    ON dp_transferencias (employee_id, data DESC);
CREATE INDEX IF NOT EXISTS ix_dp_transferencias_status ON dp_transferencias (status, data DESC);
```

Tabela nova e só dela. **Nenhum `ALTER`, `UPDATE`, `DELETE` ou `DROP` em dado que a frente não criou.**

### 3.3 Telas (grupo **Admissão & Cadastro**, `g-admissao`)

| Id | Deep-link | O que faz |
|---|---|---|
| `transferencias` | `/redesign/departamento-pessoal?t=transferencias` | lista com status e, por rascunho, as ações **Efetivar** (gated + confirm) e **Cancelar** |
| `transferencia-nova` | `…?t=transferencia-nova` | colaborador · empresa destino · data · motivo (10/11) · cargo e salário novos (opcionais) · observação |
| `transferencia-simular` | `…?t=transferencia-simular` | o antes/depois, sem gravar |
| `transferencias-conferencia` | `…?t=transferencias-conferencia` | **a régua**: eSocial × sistema, 3 painéis |

**Por que em Admissão & Cadastro e não em Desligamento:** transferência não é rescisão. Pendurá-la
no grupo do Desligamento seria ensinar, pela navegação, o erro que esta frente existe para
desfazer — e a Ficha do colaborador, que ela alimenta, já mora aqui.

A ficha do colaborador (T1) ganhou a seção **Transferências**: data, origem → destino, motivo por
extenso e status, na mesma tela em que a data de admissão aparece — para ficar visível que uma
coisa não mexe na outra.

### 3.4 As regras que a frente afirma

- **`simular`** devolve dois blocos. `muda`: empresa, CNPJ, cargo, salário, alocação, eSocial.
  `nao_muda`: data de admissão, período aquisitivo de férias (nº de períodos, âncora e saldo),
  banco de horas, dependentes, documentos, e o vínculo (status e data de demissão intocados).
  Não escreve nada — o oráculo confere lendo o colaborador antes e depois.
- **`efetivar`** faz três coisas e só três: (1) `UPDATE employees SET empresa_id`, mais
  `cct_cargo_id`/`cargo`/`salario_base` **só se** informados — `data_admissao`, `status` e
  `data_demissao` nunca entram no `SET`; (2) alocação: `movimentacao_service.remover` em **D−1** e
  `movimentacao_service.alocar` em **D**, mesmo condomínio/posto/função, com `alocacao_origem_id`
  ligando as duas; (3) **dois rascunhos** em `esocial_transmissao_propostas` com `status='proposto'`.
- **Transmissão: nunca.** Este módulo não chama `transmitir_evento_sst`, não monta XML final e não
  fala com o governo. O rascunho carrega os FATOS (mtvDeslig, tpAdmissao, `dtAdm` original,
  `sucessaoVinc`) para o humano conferir e transmitir pelo fluxo do eSocial que já existe.
- **`cancelar`** só aceita rascunho. Transferência efetivada não se desfaz por aqui — se foi
  errada, a correção é uma transferência de volta e, no governo, um S-3000 pelo fluxo humano.
- **Uma trava de entrada:** mais de uma alocação ativa → 409 com a mensagem pedindo para encerrar
  as excedentes. A F5 garante no máximo uma (medido: máx. = 1), então isto é cinto de segurança.

---

## 4. Oráculo

```bash
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_w4_transferencia.py
```

**VERMELHO** (antes do código — só o script montado na imagem): ver §1.3.

**VERDE** (depois):

```
  ✓ (a) dp_transferencias com as colunas do contrato (faltam: nenhuma)
  ✓ (b) simular lista empresa/cargo/salário no que MUDA: ['alocacao', 'cargo', 'cnpj', 'empresa', 'esocial', 'salario']
  ✓ (b) simular lista admissão/período aquisitivo/dependentes no que NÃO muda: ['banco_de_horas', 'data_de_admissao', 'dependentes', 'documentos', 'periodo_aquisitivo_de_ferias', 'vinculo']
  ✓ (b) simular não escreveu nada no colaborador
  ✓ (c) data de admissão intacta: 2024-09-24 → 2024-09-24
  ✓ (c) período aquisitivo intacto (nº, âncora, saldo): (2, '2024-09-24', 60) → (2, '2024-09-24', 60)
  ✓ (c) dependentes intactos: 2 → 2
  ✓ (c) continua ATIVO e sem data de demissão
  ✓ (c) empresa trocou: 35.710.481/0001-03 → 66.014.833/0001-10
  ✓ (c) novo salário aplicado: 2500.00
  ✓ (d) exatamente 2 rascunhos de eSocial: 2
  ✓ (d) os dois eventos certos: ['S-2200', 'S-2299']
  ✓ (d) nenhum transmitido — todos 'proposto': ['proposto']
  ✓ (d) nada foi ao governo: eventos_esocial/espelho (0, 416) → (0, 416)
  ✓ (e) exatamente uma alocação ativa depois: 1
  ✓ (e) a da origem encerrada em D−1: 2026-09-23
  ✓ (e) a nova começa em D: 2026-09-24
  ✓ (e) sem buraco e sem sobreposição entre a de origem e a nova
  ✓ (h) sem rescisão nem admissão nova: termination/admission (3, 1) → (3, 1)
  ✓ (f) cancelar não mexeu no colaborador
  ✓ (f) cancelar não mexeu nas alocações
  ✓ (f) cancelar não criou rascunho de eSocial: 2 → 2
  ✓ (f) o rascunho ficou 'cancelada': cancelada
  ✓ (g) a régua acha quem está transferido só no governo (GEILSON): ['02996913221']
  ✓ (g) quem está casado (governo + sistema) NÃO aparece como 'só no governo'
  ✓ (g) quem está casado NÃO aparece como 'só no sistema'
  ✓ (g) quem está casado aparece na lista de conferidos
  ✓ (i) fixtures apagadas ao fim: 0 sobrando
  ✓ (h) termination/admission no fim: (3, 1)
TOTAL falhas transferência W4: 0
exit=0
```

**Vizinhos, depois da frente:** `test_oraculo_dgx_t1_dp.py` → `TOTAL dgx t1: 0 falha(s)` (exit 0,
depois de a lista de seções da ficha passar de 15 para 16) · `test_oraculo_movimentacao_com_motivo.py`
→ `TOTAL falhas movimentação com motivo: 0` (exit 0) · `test_oraculo_mapa_ferias.py` →
`OK mapa de férias: tela fiada, soma fecha, sem default, âncora respeita o art. 133` (exit 0).

**HTTP** (porta 8254, token real, colaborador-fixture `FIXTURE DGX W4 HTTP` apagado ao fim):
`transferencia-simular` 200 · `transferencia-nova` 200 · `transferencia-efetivar` 200 (devolveu os
dois ids de rascunho de eSocial) · `transferencia-cancelar` 200 · `ficha-colaborador` 200 com a
seção `transferencias` preenchida. As 4 abas aparecem no fim de `g-admissao` e o painel de
conferência listou o GEILSON no quadro vermelho.

---

## 5. O que NÃO foi feito, e por quê

1. **Nenhum XML de S-2299/S-2200 é montado.** O rascunho é uma folha de fatos em `payload` jsonb.
   Montar o XML final exige `esocial_service.gerar_evento_*` com certificado e o caminho de
   transmissão — que é justamente o que esta frente foi proibida de tocar. Quem transmite, monta.
2. **Nenhuma transmissão, nenhum gatilho de transmissão.** Os dois eventos ficam `proposto` na fila
   humana. Não há task, não há beat, não há botão "transmitir" nesta frente.
3. **`mantem_admissao` é sempre `true` na prática.** A coluna existe (contrato) e o serviço a grava,
   mas nenhuma tela oferece `false`: transferência com data de admissão nova não é transferência,
   é admissão. Deixar o campo sem porta é de propósito — se o dono quiser o caso raro (sucessão em
   que o contador pede vínculo novo), é um `select` a mais, não um redesenho.
4. **A transferência não mexe em benefícios, VT/VR, cartão, dependentes ou descontos.** Eles seguem
   o colaborador porque são do colaborador; nenhum deles guarda CNPJ. Se algum benefício for por
   empresa no futuro, é outra frente.
5. **A régua não descobre quem foi transferido PARA dentro do grupo e nunca foi cadastrado aqui.**
   A consulta ao eSocial é por CPF — o governo devolve 500 sem `cpfTrab` (medido em 22/09, está
   documentado em `conferencia_esocial`). Quem o cadastro não conhece é invisível para ela; isso é
   assunto do processo de admissão, e a tela diz isso com todas as letras.
6. **Não mexi em `calculo_service.py`, `alembic/`, `frontend/`, `checar_regressao.py` nem em
   produção.** Nenhum valor de folha muda: a frente não toca em rubrica, holerite ou rescisão.
7. **Não criei PDF de comunicado de transferência.** O DGX também não tem; e o documento que o
   colaborador assina numa transferência é decisão do dono (§7).

---

## 6. Como o Jordan testa amanhã

1. Departamento Pessoal → **Admissão & Cadastro** → aba **Conferência eSocial × sistema**.
   Deve aparecer o **GEILSON** no quadro vermelho ("transferido no eSocial e sem registro aqui"),
   com o S-2299 motivo 11 de 30/06/2026 ao lado, e a data da última leitura do espelho no subtítulo.
2. Aba **Simular transferência**: escolha o GEILSON, empresa destino **CONECTAMAIS PATRIMONIAL**,
   data **30/06/2026**, deixe cargo e salário em branco → **Simular**. Leia os dois blocos: à
   esquerda o que muda, à direita a data de admissão (22/03/2026), o período aquisitivo, o banco de
   horas e os dependentes — que **não** mudam. Nada foi gravado.
3. Aba **Nova transferência**: os mesmos campos, motivo **11 — sucessão/incorporação/cisão/fusão**
   (foi o que o contador usou no governo), observação "regularização do que o eSocial já registrou"
   → **Gravar rascunho**. Volte à aba **Transferências**: a linha aparece em amarelo, `rascunho`.
4. Na linha, **Efetivar** → o aviso explica que isso troca a empresa, remaneja a alocação e cria
   2 rascunhos de eSocial, e que **nada é transmitido**. Confirme.
5. Volte à **Conferência**: o GEILSON deve sair do quadro vermelho e aparecer em **Conferidos**,
   com as duas datas lado a lado.
6. Abra **Ficha do colaborador** → GEILSON: a seção **Transferências** mostra a linha, e logo acima
   a data de admissão continua **22/03/2026**.
7. Para ver que o rascunho não é transmissão: os dois eventos estão em `esocial_transmissao_propostas`
   com `status='proposto'` — a mesma fila que o orquestrador usa e que ninguém dispara sozinho.

> Se o passo 4 devolver 409 dizendo que há mais de uma alocação ativa, é dado antigo: encerre a
> excedente em Operacional → Movimentações e repita.

---

## 7. Decisões que só o dono pode tomar

1. **Qual o motivo certo — 10 ou 11?** O contador transmitiu o GEILSON com **11** (sucessão,
   incorporação, cisão ou fusão). Entre duas empresas do mesmo grupo sem sucessão societária, o
   código da tabela 19 é o **10**. A frente aceita os dois e não escolhe por ninguém, mas a
   resposta muda o `tpAdmissao` do S-2200 (2 vs 3) e, portanto, o que o governo vai entender.
   **Pergunta para o contador, não para o sistema.**
2. **Regularizar o GEILSON.** Ele está transferido no governo desde 30/06/2026 e o sistema nunca
   registrou. Efetivar a transferência aqui (passo 3–4 do §6) fecha o buraco — mas cria dois
   rascunhos de eSocial de eventos que **o governo já recebeu**. Ou o Jordan efetiva e descarta os
   dois rascunhos na fila, ou eu acrescento uma opção "já transmitido — não enfileirar". Não decidi
   sozinho porque a segunda opção é uma porta para marcar como entregue coisa que não foi.
3. **Existe documento de transferência para o colaborador assinar?** Não há PDF nesta frente. Se o
   DP entrega um comunicado/termo de transferência hoje (em papel ou pelo contador), ele vira um
   gerador `pdf_branding` numa frente seguinte — e o timbrado sairia com o CNPJ **de destino**.
4. **Transferência retroativa tem limite?** Hoje aceita qualquer data posterior ao início da
   alocação atual. O eSocial tem prazo para o S-2299 (até o dia 15 do mês seguinte) e uma
   transferência de 3 meses atrás nasce fora do prazo. Se quiser um aviso na tela a partir de N
   dias, diga o N.
5. **Os outros quatro S-2299 do §1.1 (motivos 33/07/07/02) são desligamento de verdade e o sistema
   já os tem demitidos** — nenhuma ação. Registrado aqui só para constar que foram conferidos.
