# DGX F6 — DP complementos: dependentes, vales, eventos coletivos, crachás em lote, demissão em lote (24/09/2026)

**Branch:** `dgx/f6-dp-complementos` (base `c7077dbb6`, a mesma das frentes F1–F5)
**Módulo:** dp (telas do redesign do DP + serviço em `hr/services`) · **Sessão:** agent-f6
**Escrita:** só no SANDBOX (`conecta_pro_staging`), fixtures marcadas `FIXTURE DGX F6` e apagadas ao fim.
**Produção:** não tocada. O DDL de `_ensure` aplica em produção no 1º acesso depois do bake (§3).

## 1. Estado antes (medido no sandbox, 24/09/2026 00:30)

- **Dependentes.** O brief apontava `employee_dp.dependentes` + `quantidade_dependentes_sf`. Cavado:
  `employee_dp` tem **0 linhas** e ninguém lê (só o model). A FOLHA lê **`employees.dependentes`**
  (`calculo_service.py` 782: salário-família pela chave `menor_14`; 833: IRRF por `len()`).
  21 pessoas com dependentes, **33 entradas, todas sem nome/data** — backfill Portte de 07/2026
  (`{"tipo":"filho","fonte":"backfill_portte_salfam_2026-07-28","menor_14":true}`). O serviço
  `salario_familia_service.contar_elegiveis` (até 14 anos ou inválido, lê `nascimento`/`invalido`)
  só era chamado pela esteira de candidatos. Sem tela de dependentes, sem form.
- **Vales.** `employee_deductions`: 97 ativos, todos `consignado`; CHECK `tipo IN (consignado,
  pensao_alimenticia, emprestimo, outros)`; sem `motivo/data_ocorrencia/valor_pago/vencimento`.
  `rubricas_folha` sem o código `1040` (que o `calculo_service` já emite para todo desconto da tabela).
- **Apontamento de folha.** `folha-apontamento` = `UPDATE hr_payslips SET contest_reason, contested_at`
  (não conformidade em folha rascunho/publicada). Não existe tabela de lançamentos manuais lida pelo
  cálculo. Nenhum evento coletivo.
- **Crachá.** Só `employees.cracha_numero` (coluna). Nenhum gerador. `foto_url`: **0 de 63 ativos**.
  `nome_de_guerra` (frente 05): 0 preenchidos. `cnv`: 0.
- **Rescisão.** `nova-rescisao` → `POST /hr/terminations` → `TerminationService.create_termination`
  (status `initiated`). Sem lote. `termination_processes` sem status "rascunho": `initiated` é o
  primeiro estado e nada é efetivado nele (colaborador continua `ativo`).
- `hr_payslips`: 09/2026 = 51 draft / 0 published; 07/2026 = 51 published. `gp_asos`: 1 demissional.
  `sst_uniforme_entregas`: 0 linhas; `equipamentos_controlados_alocacoes`: 0 linhas.

Oráculo VERMELHO (antes de qualquer código):
```
$ python3 /app/scripts/orq/test_oraculo_dp_complementos.py
FALHOU: frente F6 não importa: cannot import name '_dgx_f6_dp' from 'modules.operacional.controllers.redesign_builders'
TOTAL dp complementos: 1 falha
exit=1
```

## 2. O que o DGX tem (docs/dgx)

- `01 · Dependentes`: idEmpregado, Nome, DataNascimento, Sexo, Deficiente + TipoDeficiencia, GrauDependente
  (8: Bisneto/a, Cônjuge, Filho/a, Genro/Nora, Irmã(o), Neto/a, Pai/Mae, Sogro/a), RG, CPF, GrauInstrucao (11).
- `06 · /frontend/vales`: grid Colaborador/Prestador · Evento · Data Ocorrência · Vencimento · Valor ·
  Valor Pago · Parcelas · Tipo · Motivo; filtro Aberto/Pago.
- `06 · /frontend/EventosColetivos`: Tipo (Inclusão/Remoção/Substituição), Evento Predecessor/Sucessor,
  Apontamento, Início/Término, Referência, Contratos, Escalas, Colaboradores.
- `04 · ColaboradorCracha` e `06 · /view/demissaolote/`: telas SPA sem formulário legível — só o nome.

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/scripts/orq/test_oraculo_dp_complementos.py` (novo) | Oráculo, 5 blocos + fiação (§4). |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_f6_dp.py` (novo) | DDL `_ensure`, regras, 8 telas, 9 ações + 1 GET de PDF. |
| `backend/modules/people_management/hr/services/cracha_pdf.py` (novo) | `montar_crachas(pessoas)`: A4 timbrado (`pdf_branding.marca_canvas/rodape_canvas`), 8 crachás CR-80 (85,6×54 mm) por folha, empresa por CNPJ do vínculo. `demo()` com asserts. |
| `.../redesign_builders/departamento_pessoal.py` | +5 linhas `# dgx f6`: import de `router`/`telas`, `include_router`, `await _telas_f6(db, out)` ANTES de `montar_grupos`. |
| `.../redesign_builders/_dp_grupos.py` | Tuplas no FIM de `g-admissao` (dependentes, dependente-novo, crachas-lote), `g-folha` (vales, vale-novo, eventos-coletivos, evento-coletivo-novo), `g-desligamento` (demissao-lote). |

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente, roda uma vez por processo)
```sql
ALTER TABLE employee_deductions ADD COLUMN IF NOT EXISTS motivo text;
ALTER TABLE employee_deductions ADD COLUMN IF NOT EXISTS data_ocorrencia date;
ALTER TABLE employee_deductions ADD COLUMN IF NOT EXISTS valor_pago numeric(12,2) DEFAULT 0;
ALTER TABLE employee_deductions ADD COLUMN IF NOT EXISTS vencimento date;
-- CHECK employee_deductions_tipo_check recriado UMA vez, só se ainda não tiver 'vale' (os 4 valores antigos ficam)
INSERT INTO rubricas_folha (codigo, descricao, tipo, natureza, incide_inss, incide_irrf, incide_fgts, ativo)
  VALUES ('1040','Vale / adiantamento avulso (e demais descontos do colaborador: consignado, pensão)','desconto','variavel',false,false,false,true)
  ON CONFLICT (codigo) DO NOTHING;
CREATE TABLE IF NOT EXISTS folha_eventos_coletivos (id serial PK, tipo, rubrica_codigo, rubrica_sucessora_codigo, competencia date,
  data_inicio, data_fim, referencia numeric, filtro jsonb, quantidade_colaboradores int, criado_por, criado_em, aplicado_em,
  desfeito_em, apontamento_ids jsonb, status varchar(12) DEFAULT 'rascunho');
CREATE INDEX IF NOT EXISTS ix_folha_eventos_coletivos_comp ON folha_eventos_coletivos (competencia, status);
```
Sem `alembic/`. Nenhum DROP/DELETE/UPDATE em dado existente (o CHECK é objeto de schema, e a
troca preserva os 4 valores que existiam).

### Telas (deep-link `/redesign/departamento-pessoal?t=<id>`; todas têm aba no grupo)

| id | grupo | tipo | o que faz |
|---|---|---|---|
| `dependentes` | g-admissao | table | Todos os dependentes dos ativos a partir de `employees.dependentes`: colaborador, nome, nascimento, idade, grau, sexo, deficiente/tipo, CPF, instrução, **Sal.-família** (sim/não · "sim (sem data)" para o backfill), **IRRF** (dica legal: filho ≤21/24, cônjuge, pais — a folha deduz todos). Ação por linha **Remover**. |
| `dependente-novo` | g-admissao | form | colaborador, nome, nascimento, grau (8), sexo, deficiente, tipo, CPF (dígito validado), RG, instrução (11) → `dependente-salvar`. |
| `crachas-lote` | g-admissao | form | condomínios/funções/lista + modelo → `crachas-pdf` devolve `doc` (PDF) e diz quantos sem foto. |
| `vales` | g-folha | table | colaborador, motivo, data, vencimento, valor total, parcela/mês, parcelas, pago, situação (filtro Aberto/Pago). Ação **Quitar**. |
| `vale-novo` | g-folha | form (`confirm`) | colaborador, motivo, data, valor total (aceita `1.200,00`), parcelas, vencimento → `vale-salvar`. |
| `eventos-coletivos` | g-folha | table | #, tipo, rubrica, sucessora, competência, período, ref., colab., situação, quem. Ações **Aplicar** (rascunho) / **Desfazer** (aplicado). |
| `evento-coletivo-novo` | g-folha | form (`gated`+`confirm`) | tipo, competência MM/AAAA, rubrica (de `rubricas_folha` ativas), sucessora, referência, início/término, condomínios/funções/escalas/colaboradores (multiselect, somam) → `evento-coletivo-salvar` (rascunho). |
| `demissao-lote` | g-desligamento | form (`gated`+`confirm`+`showResult`) | colaboradores (multi), último dia, tipo (os 6 de `nova-rescisao`), aviso, dias, motivo → `demissao-lote-preparar`. |

### Regras (decisões, não reabertas)
- **Fonte dos dependentes = `employees.dependentes`** (o que a folha lê), não `employee_dp`. A chave
  `menor_14` que o `calculo_service` consome é DERIVADA da mesma régua de `contar_elegiveis` a cada
  gravação (`normalizar_dependentes`); entradas do backfill (sem data) ficam intocadas — não fabrico
  nem apago direito. `employee_dp.quantidade_dependentes_sf` + `salario_familia` vão junto por upsert
  (cria a linha de `employee_dp` se não houver), como o brief pediu.
- **Deficiente ≠ inválido.** O form grava `deficiente`/`tipo_deficiencia` (DGX); a cota de
  salário-família por invalidez exige laudo — não é marcada por formulário (§7).
- **Vale** = `employee_deductions` `tipo='vale'`, `valor` = parcela, `data_inicio` = data da
  ocorrência, `data_fim` = último dia da competência da última parcela → o bloco 1040 do
  `calculo_service` (intocado) desconta exatamente N competências. **Quitar** = `ativo=false`,
  `valor_pago` = total. Descrição no holerite: "Vale — <motivo>".
- **Evento coletivo** aplica pelo MESMO caminho de `folha-apontamento` (`rd_action_folha_apontamento`,
  sessão síncrona, texto `[autor] [evento coletivo #N] Substituição da rubrica 0010 → 0011 ·
  referência 10.00 · competência 09/2026`). Só folha **rascunho**; competência com folha publicada é
  recusada (409); folha que já tem apontamento de outra origem é pulada (a função sobrescreve o texto
  — não apago o de ninguém). **Desfazer** limpa só os `hr_payslips` cujo `contest_reason` tem a marca
  do evento. Não altera valor de holerite: é paralelo cego — quem fecha vê e lança.
- **Demissão em lote** = N × `TerminationService.create_termination` (`initiated` = primeiro estado do
  fluxo, nada efetivado). Verbas estimadas por `clt_calculator.calcular_rescisao` (férias vencidas
  = 30 dias quando o mapa de férias diz "vencida"). Pendências: férias vencidas/`> 22 meses`
  (`mapa_ferias.mapa`), ASO demissional (`gp_asos`), uniforme/EPI não devolvido
  (`sst_uniforme_entregas`), arma/colete em posse (`equipamentos_controlados_alocacoes`).
- Todas as ações de escrita passam por `_require_modulo_dp` (gate `module:dp`, o mesmo dos reembolsos).
  `gated` no form é o aviso visual do redesign; **não há OTP** (nada paga nem efetiva).

## 4. Oráculo

Comando (contrato do agente, container efêmero contra o sandbox):
```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_dp_complementos.py
```
Afirma: (0) `build()` chama `_telas_f6` e as 8 abas estão nos grupos certos de `_dp_grupos.GRUPOS`;
(1) régua pura (`[≤14, adulto, inválido, backfill]` → `[T, F, T, T]`), CPF, e no banco: toda entrada
com data tem `menor_14` == régua; `employee_dp.quantidade_dependentes_sf` == `contar_elegiveis`;
ida e volta com fixture (salvar → flag certa e contagem 1 → remover → 0); (2) vale de R$ 300 em 3×
aparece em `calcular_folha_colaborador` como `1040` de R$ 100,00 e SOME ao quitar; rubrica 1040
existe como desconto; (3) evento em competência só-rascunho para 2 pessoas → 2 `contest_reason` com
a marca por SQL == `quantidade_colaboradores` == `len(apontamento_ids)`; competência publicada
recusada; desfazer → 0; (4) 8 pessoas → PDF de 1 página (PyPDF2) com o primeiro nome e a matrícula
de cada uma e "CNPJ"; 9 → 2 páginas; (5) 2 pessoas → 2 `termination_processes` `initiated`, e
`employees.status` continua `ativo` sem data de demissão.

VERMELHO (antes): §1. VERDE (depois, 24/09 00:55):
```
dependentes: 21 pessoa(s) com dependentes · 33 entrada(s) sem data de nascimento (backfill Portte, fora da régua) · fixture em ADEILSON DINIZ DEODATO
TOTAL dp complementos: 0 falha(s)
OK dp complementos: dependentes na fonte da folha, vale entra e sai da prévia, evento coletivo aplica/desfaz, crachá 8/página, demissão em lote só rascunho
exit=0
```
No caminho ficaram vermelhos legítimos que o oráculo pegou e o código corrigiu: `employee_dp.id` sem
default (upsert precisa de `gen_random_uuid()`), bind `:e` inferido como uuid e reusado como text
(asyncpg), CHECK de `tipo` sem `vale`, filtro do evento gravado com as chaves erradas (alcançava 0),
e a validação de CPF da casa reprovando CPF válido (§5).

Prova por HTTP (container `teste-dgx-f6`, porta 8206, sandbox — parado ao fim):
```
GET /api/v1/redesign/data/departamento-pessoal → 200
g-admissao: [..., 'dependentes', 'dependente-novo', 'crachas-lote']   g-folha: [..., 'vales', 'vale-novo', 'eventos-coletivos', 'evento-coletivo-novo']   g-desligamento: [..., 'demissao-lote']
dependentes: table rows=16 · sub "16 dependente(s) de 10 colaborador(es) ativo(s) · 16 contam para o salário-família · 16 sem data de nascimento (herdados da Portte ...)"
POST dependente-salvar (CPF 111.111.111-11) → 422 "CPF do dependente inválido (dígito verificador)."
POST dependente-salvar (CPF 529.982.247-25) → 200 "Dependente salvo. 1 conta(m) para o salário-família."
  linha: ADAILSON SERRA ALVES · FIXTURE DGX F6 HTTP · 03/03/2018 · 8 · Filho/a · F · Não · 529.982.247-25 · — · sim · sim
POST dependente-remover?eid=…&idx=0 → 200 "Dependente removido. Restam 0."
POST vale-salvar (1.200,00 em 4x) → 200 "Vale lançado (4x) — entra na folha de 09/2026."
  linha: ADAILSON · FIXTURE DGX F6 HTTP · 23/09/2026 · — · R$ 1.200,00 · R$ 300,00 · 4 · R$ 0,00 · Aberto
POST vale-quitar?vid=… → 200 "Vale quitado — sai das próximas folhas."
POST evento-coletivo-salvar (07/2026, publicada) → 200 rascunho #5 · POST evento-coletivo-aplicar?eid=5 → 409 "Competência 07/2026 tem folha PUBLICADA"
POST evento-coletivo-salvar (09/2026, substituição 0010→0011, 2 pessoas) → 200 #6 · aplicar → 200 "aplicado a 2 de 2" · desfazer → 200 "2 de 2 apontamento(s) removido(s)"
POST crachas-pdf (sem filtro) → 200 "50 crachá(s) em 7 folha(s). 50 sem foto (moldura vazia)." + doc → GET /api/v1/redesign/crachas/pdf?ids=… → 200, 59 KB, %PDF-1.4 (7 páginas, 8 por folha, conferido no olho)
POST demissao-lote-preparar (2 pessoas, involuntary, indenizado 30 d) → 200
  "2 rescisão(ões) em rascunho de 2 selecionado(s). Nada efetivado — cada uma segue em Desligamento → Rescisões."
  ADAILSON SERRA ALVES: rescisão 1d77d095 · verbas estimadas R$ 3.533,67 · pendências: sem ASO demissional
  ADEILSON DINIZ DEODATO: rescisão 7913ca1c · verbas estimadas R$ 2.612,86 · pendências: sem ASO demissional
```
Fixtures HTTP apagadas por SQL ao fim (`employee_deductions` motivo `FIXTURE DGX F6 HTTP`,
`folha_eventos_coletivos` #5/#6, `termination_processes` reason `FIXTURE DGX F6 HTTP`, as 2 linhas de
`employee_dp` que o upsert criou — a tabela estava vazia antes). Sandbox conferido: tudo 0.

## 5. O que NÃO foi feito e por quê

- **Cálculo da folha não muda** (`calculo_service.py` só lido). O evento coletivo é apontamento, não
  lançamento de rubrica com valor: não existe tabela de lançamentos manuais que o cálculo leia, e criar
  esse caminho é a frente F1 (rubrica como dado). Quando F1 der o caminho, `aplicar_evento` troca o
  destino e o oráculo (bloco 3) passa a contar lá.
- **`menor_14` do backfill Portte (33 entradas sem data) não foi tocado.** A folha paga a cota sem data
  de nascimento que prove; a tela mostra "sim (sem data)" em amarelo e o subtítulo conta. Corrigir é
  cadastrar a data (Pyetra), não código.
- **IRRF**: a folha deduz `len(dependentes)` — um "Sogro/a" de 60 anos cadastrado hoje passa a deduzir
  IRRF. A coluna IRRF da tela avisa ("não (idade)" / "conferir"); a regra fica para F1/F3.
- **`government_integrations.utils.validar_cpf` está errada** (mistura `(soma*10) % 11` com `11 - resto`;
  reprova 529.982.247-25, válido) e é usada por `receita_federal_service`. Não corrigi: módulo de outra
  frente. Escrevi a validação padrão no `_dgx_f6_dp.cpf_valido` (6 linhas) e registro aqui.
- **Crachá verso, QR, código de barras, `cracha_numero`**: não. Frente simples, como o brief. A foto
  vem de `employees.foto_url` (0 preenchidos hoje; o gerador aceita caminho absoluto, relativo a
  `UPLOADS_DIR` ou `/uploads/...`). Não há endpoint de upload de foto de funcionário no código —
  `foto_url` só existe como coluna.
- **Parcela do vale não "anda"** (`parcela_atual` fica 1): o desconto entra N competências pela janela
  `data_inicio..data_fim`, que é o que o cálculo lê. Contador é cosmético; sobe quando alguém precisar.
- **Rubrica 1040**: o brief pedia "Vale / adiantamento avulso"; nomeei "Vale / adiantamento avulso (e
  demais descontos do colaborador: consignado, pensão)" porque 1040 é o código que o `calculo_service`
  JÁ emite para todo desconto de `employee_deductions` — chamar só de vale mentiria no eSocial (S-1010).
- **Multiselect** do redesign chega como JSON em string (`lerLista` no `ModuleView.tsx`); as ações
  aceitam lista, JSON ou CSV. Nenhum frontend editado.
- **OTP** nas ações `gated`: não. Nada paga nem efetiva; o `gated` é o aviso visual.
- **Sem sub-router em `hr/`**, sem Hermes/MCP, sem `checar_regressao.py` (oráculo em `scripts/orq/`
  é globado pela meia-noite).
- **Commit com `SKIP=ruff-format`** (os outros hooks rodaram: ruff, bandit, secrets, governança). O hook
  `ruff-format` reformata `_dp_grupos.py` INTEIRO (234 linhas, uma tupla por linha) — arquivo
  compartilhado pelas frentes e lido por regex de linha (`feedback_ruff_format_cega_parser`, 09/2026).
  Meus 3 arquivos novos estão formatados pelo ruff; `_dp_grupos.py` ficou no formato compacto original.

## 6. Como o Jordan testa amanhã (depois do bake)

1. **Dependentes**: DP → Admissão & Cadastro → aba *Dependentes*. Conferir o subtítulo (N contam para o
   salário-família · N sem data). Aba *Novo dependente*: escolher alguém, nome, nascimento 2019, grau
   Filho/a, CPF errado → 422; CPF certo → "1 conta(m)". Voltar à lista: a linha aparece com
   Sal.-família "sim". Botão **Remover** na linha.
2. **Vale**: Folha → *Novo vale*: R$ 300, 3 parcelas, data de hoje → confirmar. Aba *Vales*: Aberto,
   R$ 100,00/mês. Folha → *Gerar folha* (prévia) do colaborador: linha `1040 Vale — <motivo>` R$ 100,00.
   **Quitar** → some da prévia.
3. **Evento coletivo**: Folha → *Novo evento coletivo*: Inclusão, 0010, competência do mês em rascunho,
   referência 10, 2 colaboradores → salvar (rascunho). Aba *Eventos coletivos* → **Aplicar** → "aplicado
   a 2 de 2". Folha → *Não conformidades*: 2 apontamentos `[evento coletivo #N] ...`. **Desfazer** → somem.
   Tentar com 07/2026 (publicada) → 409.
4. **Crachás**: Admissão & Cadastro → *Crachás em lote* → sem filtro → Gerar. Abre PDF de 7 folhas,
   8 por folha, "SEM FOTO" em todos (hoje ninguém tem foto). Filtrar por função para um lote menor.
5. **Demissão em lote**: Desligamento → *Demissão em lote*: 2 pessoas, último dia, tipo → confirmar.
   Painel de resultado: uma linha por pessoa com verbas estimadas e pendências. Aba *Rescisões*: 2 novas
   em "Iniciado". Os colaboradores continuam ativos. Cancelar as duas pela tela de rescisão (fluxo normal).
6. Oráculo em produção: `docker exec -e PYTHONPATH=/app conecta-pro-backend python3
   /app/scripts/orq/test_oraculo_dp_complementos.py` → `TOTAL dp complementos: 0 falha(s)`. Ele cria e
   apaga as próprias fixtures (`FIXTURE DGX F6`).

## 7. Decisões que só o dono pode tomar

1. **Invalidez para salário-família**: hoje só idade ≤ 14 conta. Se houver filho inválido com laudo
   INSS, quem marca `invalido` no cadastro e com que documento?
2. **33 dependentes do backfill Portte sem nome/data**: pagam cota de salário-família "sem prova".
   Cadastrar nome/nascimento de cada um (Pyetra, pela aba Dependentes → Remover + Novo) ou aceitar.
3. **IRRF por `len(dependentes)`**: aceitar até F1/F3 trazerem a regra legal (filho ≤ 21/24, etc.)?
4. **`validar_cpf` de `government_integrations`** está errada e reprova CPF válido na consulta à
   Receita — corrigir lá (outra frente) é 3 linhas.
5. **Foto do funcionário**: não há upload no sistema. Sem isso, crachá sai sempre com moldura vazia.
6. **Evento coletivo como apontamento** (não lançamento): é o que dá para fazer sem mexer no cálculo.
   Vale como sinal para quem fecha a folha, ou espera F1 e vira lançamento de verdade?
