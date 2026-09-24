# DGX T1 — DP/RH: passagem de teste e implementação (24/09/2026)

**Branch:** `dgx/t1-dp-rh` (base `b9005ef2f`) · **Módulo:** dp (+ 1 linha em `rh.py`, 1 trava em `hr/controllers`)
**Sessão:** agent-t1 · **Container efêmero:** `teste-dgx-t1`, porta 8221, sandbox `conecta_pro_staging` (parado ao fim)
**Produção:** não tocada. DDL de `_ensure` (§3) aplica em produção no 1º acesso depois do bake.
**Lista de lacunas (Fase C, commitada antes de implementar):** `docs/dgx/lacunas/dp_rh.md` (24 recursos).

## 1. Estado antes (medido no sandbox, 24/09 05:00)

- `employees.foto_url`: **0 de 63 ativos**; único escritor = sync Sólides (URL externa). Nenhum endpoint de upload,
  nenhuma rota que sirva a imagem; crachás da F6 = "50 sem foto (moldura vazia)".
- Ficha: `funcionarios` = 5 colunas + edição de 7 campos; `GET /hr/employees/{id}/profile` devolve `documents: []`
  fixo. As 26 seções que o DGX mostra numa tela estavam em 9 grupos do DP + RH + Gestão de Pessoas.
- `disciplinary_actions.document_text` = texto puro (5 medidas, 1 com texto); zero PDF, zero `pdf_branding`.
- `PUT /people-management/sst/afastamentos/{id}/retorno` existia e nenhuma tela chamava; `criar_vacation` não olhava
  `sst_afastamentos` (2 afastamentos ativos no sandbox; férias aceitas para eles).
- `training_certificates.expires_at` / `training_courses.validity_months` nunca lidos por tela (0 certificados);
  reciclagem automática só na trilha do vigilante (frente 05).
- `turnover_service`: taxa trimestral global; tela `turnover` = lista de desligamentos. 15 desligados sem motivo,
  **15 inativos/demitidos sem data de demissão**.
- `cct_cargos` (51 ativos): sem CBO, tipo de serviço ou flags CNH/CNV/porte.

Oráculo VERMELHO (imagem `conecta-pro-backend:latest` sem a T1, só o script montado):
```
FALHOU: frente T1 não importa: cannot import name '_dgx_t1_dp' from 'modules.operacional.controllers.redesign_builders'
TOTAL dgx t1: 1 falha(s)
exit=1
```

## 2. O que o DGX tem — Fase A, botão a botão (trial, empresa PATRIMONIAL, cliente `scripts/dgx/dgx_client.py`)

**Colaborador compartilhado criado por esta frente:** `TESTE CP COLABORADOR 01` — id **1**, RE `TCP01`, CPF
529.982.247-25, admissão 01/09/2026, salário 2.000,00, cargo `TESTE CP CARGO 01` (id 1), função `TESTE CP FUNCAO 01`
(id 1). Ficam no DGX (o orquestrador apaga); tudo o mais que criei foi apagado (§6).

- **`/Colaboradores/Incluir`** → `POST /Colaboradores/Salvar`. Mínimo que o servidor exigiu (mensagens literais):
  *RE não informado · Nome Abreviado não informado (`NomeGuerra`) · Admissão não informada · Cargo não informado ·
  Salário não informado · CPF não informado* — 7 campos; `CodigoCargo` obriga a criar o cargo antes
  (`/Cargos/Salvar` exige `SalarioBase` (formato `2000,00`), `Prefixo` (`SufixoInicial`) e `TipoServico` numérico:
  0 Patrimonial · 1 Escolta · 2 Limpeza · 3 Outros · 4 Administrativo). Resposta traz `URLRetorno: /Colaboradores/Editar/1`.
- **Ficha `/Colaboradores/Editar/{id}`** (form `fEmpregados`, 104 campos + sub-listas por ajax `X/SubLista?idEmpregado=`):
  Dados Gerais · Endereço · Documentos · Sindicato · Demissão · Ponto Online e Cronos · ASOS · Advertências · Afastamentos ·
  Alocações · Anexos · Banco de Horas · Benefícios · CIPA · Cartões (VT: SPTRANS/BOM/Guarupas/BEM/NUBUS) · Contatos · Cursos ·
  Dependentes · Formas de Pagamento · Locais · Pagamentos · Pensionistas · Restrições de Clientes · Suspensões ·
  Últimos Lançamentos · Uniformes/EPIs. Botões: `DetalhesReport?Tipo=PDF|Excel|Word` (PDF de 600 KB), `ImportarFoto`
  (modal → `POST /Colaboradores/IncluirFoto` multipart `Foto`+`idEmpregado` → JSON `CaminhoArquivo=/api/storage/files/…`,
  `FotoPerfil: true`), `Demitir`, `IncluirReadmissao`, `QRCodePontoOnline` (500 no trial). Cargo/função NÃO estão na
  ficha — vivem em Alocações (Movimentações).
- **`/Colaboradores/Index`**: Incluir · Filtro · Importar (Sistema + Arquivo → falhas em `/view/falhasImportacaoEmpregados`) ·
  Exportar · Imprimir · Ret Afast (`RelatorioRetornoAfastamentos`) · Folhamatic · Planilha · Alocações · Transferir (filial
  destino); contadores Ativo/Inativo/Afastado/Demitido/Falecido/Férias/Suspenso/Ausente.
- **Cursos**: `/CursosCertificados` (Reciclável, DiasValidade 180/365/730/1095/1460/1825/0=não expira, Atuação);
  `/AgenteCursos` recusou sem validade: *"Este curso é Reciclável, preencha a Data de Validade para continuar!"* — não
  calcula sozinho; filtro Status Ativo/Vencido/Não Expira/Renovado; `ListagemReport` PDF/Excel/Word.
- **Advertência** (`TipoFatoRelevante` 1 Advertência · 9 Outros, motivo 500, descrição 5000, data) e **Suspensão**
  (data, retorno, `EventoRelacionado` → `SalvarEventoRelacionado` liga a um evento/rubrica): gravam; Editar/Excluir;
  `IncluirAnexo` (500 no trial); só `ListagemReport` (PDF da LISTA, 550 KB) — **não há termo individual em PDF**.
- **Afastamento**: 18 tipos eSocial (4 = Doença…); editar traz campos extra (`TipoAcidenteTransito`, `NomeMedico`,
  `InscricaoMedico`, `CID`, `UFMedico`, `DiasAfastamento`, `CNPJCessionario`, `TipoOnusCessao`, `CNPJSindicato`,
  `TipoOnusRemuneracao`); fechar = preencher `Retorno`. `/TiposAfastamento`: tabela Descrição·Código·**Status do
  colaborador** por tipo (todos AFASTADO por padrão; editável). `GerarArquivo` (layout por período). Status do colaborador
  na API continuou 0 (Ativo) — muda por rotina, não na hora.
- **Férias**: com afastamento aberto recusa *"Já existe um afastamento para este colaborador"*; após o retorno grava
  (id 1, 01/10→30/10/2027, aquisitivo 01/09/2026→31/08/2027). Linha: Editar · Excluir · **`GerarConta/{id}`** (forma de
  pagamento, vencimento, valor, centro de custo, plano de contas, conta bancária → conta a pagar) · **Cobertura**
  (`/Coberturas/CoberturaColaborador?Motivo=FERIAS`). Tela: Incluir · Filtro · **Mapa de férias** (RE, Cliente, Cargo,
  Avos, aquisitivo, Data Limite, Turno; Recalcular) · Imprimir (`/Relatorios/FeriasListagem`) · **Aviso de Férias**
  (`POST /Ferias/LoteAvisoFerias` com os ids marcados → `/Relatorios/PreviewAsync` → `RelatorioAvisoFerias` PDF/EXCEL/WORD) ·
  Incluir Em Lote (`/frontend/Ferias/Editar`: filtros → Calcular → Salvar Todos).
- **Benefícios**: `/TiposBeneficios` gravou VT (Percentual Sobre Salário 6,00, Diária, remover férias/afastados);
  `/OperadoraItinerarios` exige **Código numérico**; `/EmpregadoBeneficios` exige **Linha**; `/EntregasBeneficios`
  (benefício, referência `10/2026`, período, entregas anteriores 1/2, apuração Manual ou apontamento + início/fim) gravou
  a entrega 1 com "Funcionários 0" (colaborador sem contrato/alocação); `GerarArquivoExportacao` (leiaute SPTrans);
  `RelatorioFaltasPorPeriodo`. `/BeneficiosReajuste`: Novo Reajuste (Contrato × Benefício → "Vagas Reajustadas",
  histórico Benefício·Data·Valor·Usuário). Alelo: Associação/Desbloqueio → `GerarArquivoAlelo`.
- **SPA**: Turnover (`POST /Colaboradores/ListaColaboradoresDashboard` {PesquisarPor, DataInicio/Termino, idsCliente,
  idsFuncionario, idsContratos, UltimaAlocacaoDemitido} → ATIVOS 1 · DESLIGADOS 0 · TOTAL 1 · **TURNOVER 0,50** =
  ((1+0)/2)/1; série mensal; gênero) · Fotos em lote (grid RE·Colaborador·Fotos, `filtro {trazerFoto:true}`, form por linha) ·
  Demissão em lote (Referência → marcar → Selecionados(n) → Último Dia + Demissão → Aplicar) · Falhas de importação
  (Data · Identificador origem · Nome · RE · Motivo; Não resolvido / Resolvido) · Crachás (Colaborador · Validade Crachá ·
  Admissão; `AtualizarTodasValidades`; legenda ATIVO/VENCIDO) · Vales (Colaborador/Prestador, Evento `vale=true`,
  `/Vales/parcelar`, Aberto/Pago) · Eventos coletivos (Inclusão/Remoção/Substituição, predecessor/sucessor, apontamento,
  contratos/escalas/colaboradores) · `/View/Sindicatos` (Nome · Contato · Telefone · Mês Dissídio · Tipo).

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/operacional/controllers/redesign_builders/_dgx_t1_dp.py` (novo) | DDL `_ensure`, 8 telas, 5 ações + 2 GET (foto, termo PDF), `ficha()`, `certificados()`, `serie_turnover()`, réguas `situacao_validade`/`turnover`. |
| `backend/modules/people_management/hr/services/foto_colaborador.py` (novo) | `salvar_foto` (JPEG/PNG/WebP ≤ 5 MB, assinatura do arquivo conferida, grava `UPLOADS_DIR/employees/<id>.<ext>` e `foto_url` RELATIVA que `cracha_pdf.foto_path` resolve), `importar_zip` (matrícula · CPF · UUID), `demo()`. |
| `backend/modules/people_management/hr/services/termo_disciplinar_pdf.py` (novo) | `montar_termo(acao, assinaturas)`: PDF padrão-ouro (`pdf_branding`), identificação, corpo do `document_text` já hasheado/assinado, bloco de autenticidade, campos de assinatura, testemunhas na recusa. `demo()`. |
| `.../redesign_builders/departamento_pessoal.py` | +3 linhas `# dgx t1` (import, include_router, `_telas_t1` antes de `montar_grupos`); ação **Registrar retorno** na linha de `licencas` (status ativo). |
| `.../redesign_builders/_dp_grupos.py` | Abas: g-admissao (5), g-visao (1), g-cct (2). |
| `.../redesign_builders/rh.py` | `disc-medidas`: `docsfn` **Termo (PDF)** (desligado, honesto, quando ainda não há texto). |
| `backend/modules/people_management/hr/controllers/vacation_controller.py` | `criar_vacation`: **409** com afastamento aberto (status ativo, sem retorno) — no controller, porque MCP `solicitar_ferias` e portal passam por ele. |
| `backend/scripts/orq/test_oraculo_dgx_t1_dp.py` (novo) | Oráculo, 9 blocos (§4). |

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente)
```sql
ALTER TABLE cct_cargos ADD COLUMN IF NOT EXISTS cbo varchar(10);
ALTER TABLE cct_cargos ADD COLUMN IF NOT EXISTS tipo_servico varchar(20);
ALTER TABLE cct_cargos ADD COLUMN IF NOT EXISTS exige_cnh boolean NOT NULL DEFAULT false;
ALTER TABLE cct_cargos ADD COLUMN IF NOT EXISTS exige_cnv boolean NOT NULL DEFAULT false;
ALTER TABLE cct_cargos ADD COLUMN IF NOT EXISTS exige_porte_arma boolean NOT NULL DEFAULT false;
```
Sem tabela nova, sem `alembic/`, sem DROP/DELETE/UPDATE em dado existente. Pasta `UPLOADS_DIR/employees/` nasce no
1º upload (`mkdir -p`).

### Telas (deep-link `/redesign/departamento-pessoal?t=<id>`)

| id | grupo | tipo | o que faz |
|---|---|---|---|
| `colaboradores-fotos` | g-admissao | table | ativos CLT com/sem foto (filtro), doc **Foto** por linha (`GET /api/v1/redesign/colaboradores/{id}/foto`). |
| `colaborador-foto` | g-admissao | form multipart | colaborador + arquivo → `colaborador-foto`. Substitui a anterior. |
| `colaboradores-fotos-lote` | g-admissao | form multipart | ZIP (`<matrícula|CPF|id>.jpg/png/webp`) → `colaboradores-fotos-lote`; resultado lista gravadas / sem colaborador / ignorados. |
| `ficha-colaborador` | g-admissao | form `showResult` | escolhe a pessoa → 15 seções (dados, contrato+CCT, documentos, endereço/contato, banco/PIX, alocação F5, dependentes F6, benefícios F3, descontos/vales, ASO, cursos, disciplina, afastamentos, férias, uniforme/EPI+armamento). Só leitura. |
| `certificados-vencimento` | g-admissao | table | RH (`training_certificates`) ∪ vigilante (`vigilante_cursos`) ∪ ficha (CNV/curso/CNH/porte) com régua Vencido/≤30/≤60/≤90/Ativo/Não expira; filtro. |
| `turnover-dashboard` | g-visao | dash | KPIs (quadro CLT, admitidos 12 m, desligados 12 m, turnover DGX), série 6 meses, gênero; subtítulo conta desligados sem motivo e **sem data**. |
| `cargos-atributos` / `cargo-atributos-form` | g-cct | table / form | CBO (6 dígitos), tipo de serviço (5 do DGX), exige CNH/CNV/porte → `cargo-atributos-salvar` (campo vazio não apaga). |
| linha de `licencas` | g-ferias | ação | **Registrar retorno** (data) → `PUT /people-management/sst/afastamentos/{id}/retorno` (encerra, recalcula estabilidade, retransmite S-2230 pelo caminho já existente). |
| linha de `disc-medidas` (RH) | Medidas disciplinares | doc | **Termo (PDF)** → `GET /api/v1/redesign/disciplina/{id}/pdf`. |

Ações de escrita passam por `_require_modulo_dp` (gate `module:dp`, o mesmo da F6).

## 4. Oráculo

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,mode=1777 -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_dgx_t1_dp.py
```
VERMELHO (antes): §1. VERDE (depois, 24/09 05:35):
```
ok foto_colaborador
ok termo_disciplinar_pdf 38307 bytes
ativos CLT: 50 · certificados: 0 (0 vencidos) · turnover 09/2026: +0 −1 quadro 52 → 0.01
TOTAL dgx t1: 0 falha(s)
OK dgx t1: foto resolve no crachá, ficha bate com o SQL, régua de validade, turnover DGX, termo em PDF, férias travadas por afastamento aberto
exit=0
```
Afirma: fiação (`_telas_t1` antes de `montar_grupos`, 8 abas nos grupos, PDF ligado no rh, trava no controller); réguas
puras; foto de fixture gravada e RESOLVIDA por `cracha_pdf.foto_path`, GIF recusado, ZIP 2/1/1; ficha: dependentes ==
`jsonb_array_length`, benefícios ativos == SQL, férias == min(6, SQL); vencidos da tela == recontagem SQL das 3 fontes;
admitidos/desligados do mês == SQL só-CLT; termo `%PDF` com o nome do empregado (PyPDF2); férias 409 com afastamento
aberto e aceitas após retorno (fixture `FIXTURE DGX T1`, apagada); 5 colunas de `cct_cargos`.

Prova por HTTP (container `teste-dgx-t1`, 8221, sandbox — fixtures desfeitas, parado ao fim):
```
POST colaborador-foto (JPEG) → 200 "Foto de ADAILSON SERRA ALVES gravada (employees/2430761d-….jpg). O crachá já sai com ela."
POST colaborador-foto (GIF) → 422 "Envie JPEG, PNG ou WebP."   GET /redesign/colaboradores/{id}/foto → 200 image/jpeg
POST crachas-pdf {employee_ids:[id]} → "1 crachá(s) em 1 folha(s). 0 sem foto"   (antes: 50 sem foto)
POST colaboradores-fotos-lote (85.jpg, fotos/81429045272.png, 999999.jpg, leia-me.txt) → "2 gravada(s) · 1 sem colaborador · 1 ignorado(s)"
POST ficha-colaborador → 15 seções; contrato: AGENTE DE PORTARIA · PORTEIROS AGENTE DE PORTARIA GUARDETE · piso R$ 1.670,00 · 12x36
GET /redesign/disciplina/2d6fa25c…/pdf → 200 application/pdf 37 KB (ADVERTÊNCIA DISCIPLINAR · THAIS FERREIRA MATOS · ADV-TFM-20250710)
POST cargo-atributos-salvar {cbo 5174-20, exige_cnv sim, Patrimonial} → 200; banco 517420|Patrimonial|true; cbo "12" → 422
POST vacation-request (ADEILSON, afastamento fixture aberto) → 409 "Colaborador com afastamento aberto (doenca desde 14/09/2026). Registre o retorno…"
PUT /sst/afastamentos/{id}/retorno {data_retorno} → 200 status encerrado   → vacation-request → 200 "Férias solicitadas … 30 dias"
checar_tela_sem_porta (QA_API=8221): TOTAL 16 sem porta — os mesmos de antes, nenhuma tela da T1
```

## 5. O que NÃO foi feito e por quê

- **Recibo de férias PDF, `GerarConta` (título a pagar) e férias em lote** (lacuna 6): esforço M cada; a folha já paga
  férias no PIX em lote, e o recibo exige o cálculo de férias assinado — fica para uma frente de férias.
- **Entrega de benefício com período de apuração configurável** (14) e **reajuste em massa** (15): a F3 declarou o
  motor em paralelo cego "até fechar dois meses" e a decisão de 13/09 diz que preço muda por aditivo, não por botão.
- **Suspensão descontando dias na folha**: dinheiro → paralelo cego + decisão do dono (§7). O DGX faz por
  `EventoRelacionado` (rubrica); aqui seria `employee_deductions` ou apontamento — não sem o Jordan escolher.
- **Status do colaborador por tipo de afastamento** (`/TiposAfastamento` → AFASTADO/FÉRIAS): `employees.status` é lido
  pela folha e pela escala; mudar automaticamente é regra de negócio grande. A ficha e `licencas` mostram o afastamento.
- **Falhas de importação persistidas** (8), **export/imprimir colaboradores** (22): baixo valor; erros já voltam na hora.
- **Foto no mesmo form da admissão** e **miniatura na tabela**: o form declarativo não mostra imagem em célula; a foto
  abre pelo botão da linha (`fmt: jpg` = só "baixar/abrir", por desenho do `docsource`).
- **`training_certificates` continua com 0 linhas**: a tela de validade está pronta; quem emite certificado é o fluxo de
  treinamento do RH (`gestao_de_pessoas` → emitir). Não fabriquei dado.
- **Colateral**: em `vacation_controller.py` o hook do ruff reordenou um import e quebrou em linhas o `pdf_branding as B`
  (pré-existente, agora com `noqa: N812`) — sem isso o commit não passava por um erro que não era meu.
- Sem Telegram, sem `alembic/`, sem `frontend/`, sem `checar_regressao.py`, sem MCP/Hermes.

## 6. Como o Jordan testa amanhã (depois do bake)

1. DP → Admissão & Cadastro → **Enviar foto**: escolha alguém, mande um JPEG → "Foto gravada". Aba **Fotos**: a pessoa
   vira "com foto", botão Foto abre a imagem. **Crachás em lote** com essa pessoa → o crachá sai com a foto.
2. **Fotos em lote (ZIP)**: ZIP com `85.jpg` (matrícula) e `03527554238.jpg` (CPF) → resultado lista as duas; um nome
   inventado aparece em "não encontrados".
3. **Ficha do colaborador**: escolha alguém → painel com as 15 seções. Confira dependentes e benefícios com as abas
   Dependentes e Benefícios (mesmos números).
4. Férias & Afastamentos → **Licenças**: numa linha "Ativo", **Registrar retorno** → data → linha vira Encerrado. Antes
   disso, tente **Solicitar** férias para essa pessoa → 409 com a mensagem do afastamento; depois do retorno → aceita.
5. RH → Medidas disciplinares: linha de THAIS FERREIRA MATOS → **Termo (PDF)** abre o termo timbrado; numa medida sem texto
   o botão vem desligado com o motivo.
6. Visão geral → **Turnover**: KPIs + 6 meses + gênero; o subtítulo diz quantos desligados estão sem data.
7. Sindicato & CCT → **Editar cargo**: PORTEIROS … → CBO 517420, exige CNV sim → aba **Cargos: CBO e exigências** mostra.
8. Oráculo em produção: `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_dgx_t1_dp.py`
   → `TOTAL dgx t1: 0 falha(s)` (cria e apaga as próprias fixtures `FIXTURE DGX T1`).

## 7. Decisões que só o dono pode tomar

1. **Suspensão desconta na folha?** O DGX liga a suspensão a um evento (rubrica). Aqui: dias de suspensão viram desconto
   automático (`employee_deductions`) ou apontamento para quem fecha a folha? Dinheiro — não decidi.
2. **15 inativos/demitidos sem data de demissão** (e 15 sem motivo): o turnover não consegue colocá-los no tempo.
   Cadastrar a data (Desligamento → Rescisões) ou aceitar a série como está.
3. **Foto obrigatória na admissão?** Hoje é opcional (aba própria). Se for regra, entra em `cadastro-incompleto`.
4. **Reciclagem por cargo**: com `exige_cnv` no cargo, a régua do vigilante (frente 05, `system_configs`) pode passar a
   ler o cargo em vez da lista de funções. Quer que a régua mude de fonte?
5. **Recibo de férias e conta a pagar da férias** (DGX `GerarConta`): vale uma frente própria ou a folha/PIX em lote basta?
6. No DGX ficaram `TESTE CP COLABORADOR 01` (id 1) + `TESTE CP CARGO 01` + `TESTE CP FUNCAO 01` (o colaborador exige o
   cargo). O orquestrador apaga os três no fim.
