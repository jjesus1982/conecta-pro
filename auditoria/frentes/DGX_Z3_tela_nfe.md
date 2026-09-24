# DGX Z3 — A tela de emitir NF-e e o DANFE

**Onda 8 · 24/09/2026 · branch `dgx/z3-tela-nfe` · módulo `fiscal` · porta de teste 8283**

> Pedido do dono: **«preciso urgente emitir notas fiscais».**

---

## §1 — Estado ANTES (medido no sandbox, cópia de produção de 24/09)

| O que | Medida |
|---|---|
| Rotas HTTP de NF-e de produto | **0**. `fiscal_contabil/notas_fiscais/nfe/controller.py` tem 476 linhas, um `router = APIRouter(prefix="/nfe")` e um bloco final «Endpoints» **vazio** — a docstring promete `POST /fiscal/nfe/emitir`, `GET /fiscal/nfe/listar` e `GET /fiscal/nfe/{id}/status`; nenhuma existe. |
| Telas de NF-e de produto no redesign | **0**. O menu do fiscal tem `nfse-emitir-dps`, `nfse-emitidas`, `nfe-entrada-xml` (NF-e de **compra**) — nada de NF-e modelo 55 de **saída**. |
| `router` no builder `fiscal.py` | **não existia** (o loader só inclui `router` se o módulo tiver um). |
| Tabela `nfes` | 90 colunas, **2 linhas**, ambas `status='rejeitada'`, série 1, números 1 e 2. Sem coluna `ambiente`, sem colunas de cancelamento. |
| Tabela `nfe_itens` | 35 colunas, 2 linhas. |
| Gerador de DANFE | **nenhum**. `nfe_provider._emitir_sync` devolve literalmente `"pdf_danfe": None`. |
| `fin_produtos` (frente Z1) | ainda não existe nesta base → fonte provisória `nfe_compras_estoque` (147 itens com NCM real). |
| `empresas` | 2 ativas: `conecta_eletronica` (CNPJ 35.710.481/0001-03, IE 05.426.574-6, lucro real → CRT 3, cert. `certificado.pfx`) e `conecta_patrimonial` (66.014.833/0001-10, **sem IE**, simples → CRT 1, cert. `patrimonial.pfx`). |
| `clients` | 29, com `document_number`, `state_registration` e endereço completo. |

**Em uma frase:** havia motor (assinatura, chave de acesso, transmissão SEFAZ-AM, cancelamento
com `xJust`) e **nenhuma porta**. Ninguém no ERP conseguia emitir uma nota de mercadoria.

---

## §2 — O que o DGX tem

Emissão de NF-e com escolha de ambiente, pré-visualização do documento antes de transmitir,
listagem com chave/status/motivo da SEFAZ, DANFE em PDF e cancelamento com justificativa.
O detalhe que o DGX acerta e que a maioria dos ERPs erra: **o ambiente é uma decisão explícita
da tela**, não uma configuração escondida — e o documento de homologação sai carimbado.

---

## §3 — O que foi feito

### Arquivos

| Arquivo | O quê |
|---|---|
| `backend/modules/operacional/controllers/redesign_builders/_dgx_z3_tela_nfe.py` | **novo** — regras puras, DANFE, XML de conferência, 3 endpoints GET/POST de documento, 4 ações, 4 telas. |
| `backend/modules/operacional/controllers/redesign_builders/fiscal.py` | +2 blocos: `await _z3.telas(db, out)` no fim do `build()`; `EXTRA_MENU.extend(...)` e `router = _z3m.router` no fim do arquivo. |
| `backend/scripts/orq/test_oraculo_z3_tela_nfe.py` | **novo** — oráculo. |

### Telas (deep-link `/redesign/fiscal?t=<id>`, grupo **Notas fiscais**, no FIM do menu)

| id | Tipo | O que faz |
|---|---|---|
| `nfe-nova` | form | Empresa emitente, destinatário (select dos 29 clientes **ou** avulso com CNPJ/CPF, IE, indicador de contribuinte e endereço completo), natureza, CFOP, finalidade, produto + quantidade/unitário/desconto (+ itens adicionais em JSON), frete e **ambiente com HOMOLOGAÇÃO pré-selecionado**. |
| `nfe-preview` | table (**leitura pura**) | Um rascunho por linha com nº/série, destinatário, nº de itens, produtos, **ICMS / PIS / COFINS**, total, ambiente e a coluna «Situação»: verde «Pronta para transmitir» ou **vermelho** com todas as pendências. Botão «Ver XML montado» por linha. Nenhuma ação de escrita. |
| `nfes-emitidas` | table | Nº/série, **chave de acesso formatada em blocos de 4**, destinatário, valor, status, ambiente e o **`xMotivo` INTEIRO da SEFAZ**. Documentos por linha: **Ver XML** e **DANFE (PDF)**. Ações: **Cancelar** (só em autorizada, justificativa 15+), **Transmitir (homologação)** (em rascunho/rejeitada), **Lançar a receber** (só em autorizada). |
| `nfe-producao` | form **`gated: True` + `confirm` + OTP** | Só lista rascunhos marcados PRODUÇÃO. Passa por `redesign_write_gate.money_gov` — sem OTP consumido nesta request, nada vai à SEFAZ. |

### Endpoints

```
GET  /api/v1/redesign/nfe/{nfe_id}/danfe/pdf      ← o DANFE
GET  /api/v1/redesign/nfe/{nfe_id}/xml            ← XML autorizado, ou o montado para conferência
POST /api/v1/redesign/action/nfe-nova
POST /api/v1/redesign/action/nfe-transmitir-homologacao
POST /api/v1/redesign/action/nfe-producao         ← gated + OTP
POST /api/v1/redesign/action/nfe-cancelar         ← gated + OTP quando ambiente = produção
```
Todos sob `Depends(require_permission("module:fiscal"))`.

### A regra que não se quebra — como está implementada

1. `ambiente` nasce `value="homologacao"`, e a **primeira opção** do select é a de homologação.
2. `nfe-nova` **nunca transmite em produção**: escolher «produção» grava o rascunho e devolve
   *«Rascunho N/S de R$ X gravado PARA PRODUÇÃO — e NADA foi transmitido»*, apontando a tela gated.
3. `nfe-producao` é `gated: True` + `confirm` + `money_gov` (OTP no e-mail do Jordan).
4. Cancelamento em produção passa pelo mesmo gate.
5. O DANFE carrega a faixa **SEM VALOR FISCAL** sempre que `ambiente != producao` **ou**
   `status != autorizada` — um rascunho impresso não é documento fiscal nem em produção.
6. **Esta frente não transmitiu em produção nenhuma vez, nem para testar.**

### DDL que o `_ensure` vai aplicar em produção no 1º acesso

Tudo `ADD COLUMN IF NOT EXISTS` sobre `nfes` — **nenhum UPDATE, nenhum DELETE**:
`ambiente varchar(16)` · `c_stat varchar(8)` · `cliente_id uuid` · `empresa_slug varchar(40)` ·
`destinatario_ind_ie varchar(2)` · `destinatario_cod_municipio varchar(10)` ·
`justificativa_cancelamento text` · `data_cancelamento timestamptz` ·
`protocolo_cancelamento varchar(40)` · `criado_por varchar(120)` ·
`CREATE INDEX IF NOT EXISTS ix_nfes_status_criacao ON nfes (status, created_at DESC)`.

> As 2 notas que já existiam nasceram **antes** de haver coluna `ambiente` e aparecem como
> **«(não registrado)»**. Não dá para adivinhar em que ambiente elas foram — e chutar
> «produção» ali seria inventar fato fiscal.

### A recusa que ensina (HTTP 422, medida de fora)

```
Item 1 «CAMERA IP DOME 2MP»: NCM ausente ou com 0 dígito(s). A SEFAZ exige o NCM de 8 dígitos
de cada produto (é ele que define a tributação) — cadastre o NCM do produto antes de emitir.

Item 1 «CAMERA IP DOME 2MP»: CFOP 6102 incompatível com o destino. O destinatário está no
mesmo estado (AM → AM), então o CFOP tem de começar com 5 (ex.: 5102 para venda de mercadoria).

Destinatário marcado como CONTRIBUINTE do ICMS (indicador 1) e sem Inscrição Estadual.
Preencha a IE; se ele não for contribuinte, marque o indicador 9; se for isento, marque o 2.

CONECTAMAIS PATRIMONIAL LTDA não tem Inscrição Estadual cadastrada. A SEFAZ não autoriza NF-e
de mercadoria sem IE — cadastre a IE da empresa (Configurações → Empresas) ou emita por um
CNPJ que tenha.
```
As pendências saem **todas de uma vez**, numeradas — não uma por tentativa.

---

## §4 — Oráculo

`backend/scripts/orq/test_oraculo_z3_tela_nfe.py` — trava cinco coisas: (1) o padrão do ambiente
é homologação e a tela de produção é gated; (2) a recusa ensina (NCM/destinatário/CFOP → 422);
(3) o DANFE de homologação traz a faixa e o de produção autorizada não; (4) cancelar exige 15+
caracteres; (5) a lista mostra o `xMotivo` inteiro. Fixture `'FIXTURE DGX Z3'` apagada no `finally`.

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_z3_tela_nfe.py
```

**VERMELHO (antes do código, 13:41):**
```
FALHOU: não consegui importar _dgx_z3_tela_nfe: cannot import name '_dgx_z3_tela_nfe' from
        'modules.operacional.controllers.redesign_builders'
TOTAL falhas Z3: 1
```

**VERDE (depois, 13:58):**
```
TOTAL falhas Z3: 0
OK NF-e: padrão homologação travado, recusa que ensina (NCM/destinatário/CFOP), DANFE de
homologação com SEM VALOR FISCAL, cancelamento com 15+ caracteres, xMotivo inteiro na lista.
```

### Prova de FORA (HTTP real, container `teste-dgx-z3` na porta 8283)

O verde do oráculo é o de dentro. O de fora, pelo mesmo caminho do navegador:

```
telas: ['nfe-nova', 'nfe-preview', 'nfes-emitidas', 'nfe-producao']
portas no menu: ['nfe-nova', 'nfe-preview', 'nfes-emitidas', 'nfe-producao']
ambiente padrão no payload HTTP: homologacao
nfe-producao gated: True
  sem NCM: HTTP 422 → ... A SEFAZ exige o NCM de 8 dígitos ...
  sem CFOP: HTTP 422 → ... São 4 dígitos — venda dentro do estado começa com 5 ...
  destinatário sem CEP: HTTP 422 → Destinatário sem CEP de 8 dígitos. Ex.: 69050-001 → 69050001.
  CFOP 6xxx no mesmo estado: HTTP 422 → ... o CFOP tem de começar com 5 ...
produção: {"ok": true, "nfe_id": "...", "numero": 1, "serie": 9, "valor_total": 900.0,
           "message": "Rascunho 1/9 ... gravado PARA PRODUÇÃO — e NADA foi transmitido..."}
DANFE: HTTP 200 · 43806 bytes · %PDF=True · SEM VALOR FISCAL=True
XML: <?xml version="1.0" ...  (2435 bytes)
preview linhas: 3 · ações de ESCRITA: nenhuma
cancelar com justificativa curta: 422   ·   cancelar um RASCUNHO: 400
TOTAL falhas E2E Z3: 0
```

### Prova VISUAL do DANFE (e os dois defeitos que só ela pegou)

A primeira versão passava no oráculo (a faixa estava lá) e estava **errada na folha**:
o «Município / UF» do destinatário atravessava a borda da caixa de baixo, a legenda da chave
caía fora da caixa, e o **V. COFINS ficava por cima do TOTAL DA NOTA**. Corrigido: a altura de
cada caixa agora sai de `_alt(linhas)` (título 9 mm + 8 mm por linha + respiro), a caixa de
itens **estica** até encostar na de totais (ancorada em baixo) e o TOTAL desceu uma linha.
A data em texto ISO também saía ao contrário — `_br_dt` passou a aceitar ISO.

---

## §5 — O que NÃO foi feito, e por quê

1. **Não toquei no emissor** (`financial/integrations/nfe_provider.py`,
   `fiscal_contabil/notas_fiscais/nfe/controller.py`) — é a frente **Z2**. Mas medi um defeito
   que impede QUALQUER emissão hoje, e que é de uma linha (para a Z2 aplicar):

   > `nfe_provider.py:197` faz `nf.identificador_unico = f"NFe{chave}"`, e
   > `identificador_unico` é uma **`@property` sem setter** na PyNFe instalada
   > (`pynfe/entidades/notafiscal.py:545`). Transmitir em homologação devolve, de fora:
   > `502 — A SEFAZ/emissor não concluiu a transmissão (homologacao): Falha na emissão da NF-e:
   > property 'identificador_unico' of 'NotaFiscal' object has no setter. A nota segue como
   > rascunho.` A linha é redundante: a PyNFe já calcula o `Id` a partir dos campos da nota.

   A tela trata isso do jeito honesto: HTTP 502, a nota **fica rascunho**, e o motivo real vai
   para `motivo_rejeicao`. Nunca vira «autorizada».

2. **Não criei `fin_produtos`** — é a frente **Z1**. `_produtos()` tenta `fin_produtos` primeiro
   e cai em `nfe_compras_estoque` se ela não existir; a tela **declara a fonte** no subtítulo
   («cadastro fiscal próprio ainda não existe, então o NCM é o da última compra; confira antes
   de emitir»). Quando a Z1 entrar, a fonte troca sozinha, sem tocar neste arquivo.

3. **Não parametrizei o emitente por CNPJ.** `nfe_provider._EMITENTE` é fixo na Eletrônica.
   Transmitir por outro CNPJ mandaria ao fisco um XML com o emitente errado — a tela **recusa**
   com a explicação, em vez de fazer isso. Quem parametriza é a Z2.

4. **Um CFOP por nota** (os itens adicionais em JSON podem trazer o seu). Nota com CFOPs
   diferentes por item é caso raro aqui e a régua de validação já é por item.

5. **Carta de correção (CC-e) e inutilização de numeração** ficaram fora: são eventos distintos
   do cancelamento e ninguém pediu. O cancelamento, que é o urgente, está.

6. **Não lanço o título a receber sozinho.** A linha da nota autorizada oferece «Lançar a
   receber» apontando para `receivable-condicao` — o endpoint e os campos que o financeiro já
   usa. Emitir nota e lançar título são duas decisões: quem emite escolhe o vencimento.

7. **Não vinculei à fatura da frente W2**: a W2 é desta mesma onda e ainda não está mesclada.
   O `cliente_id` já fica gravado em `nfes` — é o gancho de que o vínculo vai precisar.

8. **Não mexi em `frontend/`**: `form` e `table` renderizam genericamente; a única coisa que
   precisei descobrir foi que o dispatcher injeta um «Ver» read-only em toda tabela — por isso
   a régua de «tela que não transmite» é *ação com `endpoint`*, não *ação*.

---

## §6 — Como o Jordan testa amanhã (passos de clique)

1. Fiscal → menu **Notas fiscais** → **Emitir NF-e (produto)**.
2. Empresa: **Conecta Mais Eletrônica** (a Patrimonial vai recusar — está sem IE, e o aviso diz isso).
3. Ambiente: deixe **HOMOLOGAÇÃO** (já vem marcado).
4. Destinatário: escolha um cliente da lista **ou** deixe «AVULSO» e digite CNPJ, razão, CEP,
   logradouro, nº, bairro, município, UF e o **código IBGE** (Manaus = 1302603).
5. CFOP **5102** (venda dentro do AM), produto da lista, quantidade e valor unitário. Enviar.
6. **Para ver a recusa que ensina:** apague o NCM, ou troque o CFOP para 6102 com destinatário
   em Manaus, e envie — a tela lista tudo que falta, numerado.
7. **Conferir antes de transmitir**: o rascunho aparece com os tributos e, se faltar algo, a
   pendência em vermelho. Clique em **Ver XML montado**.
8. **NF-e emitidas**: clique em **DANFE (PDF)** — o documento sai com a faixa **SEM VALOR FISCAL**
   atravessando a página (é homologação). Em nota rejeitada, leia a coluna do fim: é o texto
   exato da SEFAZ.
9. **Só quando a Z2 consertar o emissor** e você quiser valer de verdade: em «Emitir NF-e»
   marque **PRODUÇÃO** (grava só o rascunho), vá em **NF-e — transmitir em PRODUÇÃO**, escolha o
   rascunho, confirme e digite o **OTP que chega no seu e-mail**.

---

## §7 — Decisões que só o dono pode tomar

1. **A Patrimonial vai emitir NF-e de mercadoria?** Ela está sem Inscrição Estadual cadastrada.
   Se for emitir, precisa da IE na Receita/SEFAZ-AM e no cadastro; se não for, a Eletrônica
   segue sendo a única emitente de modelo 55 e a tela já está certa como está.
2. **Parametrizar o emitente por CNPJ no `nfe_provider`** (hoje fixo na Eletrônica) — é trabalho
   da Z2, mas a decisão de fazer ou não é sua.
3. **A tributação padrão** hoje é ICMS CST 40 (isento, Zona Franca) + PIS/COFINS CST 07 (isentos),
   que é o que a casa pratica em Manaus. Venda para **fora do AM** provavelmente não é isenta —
   confirme com a Portte antes da primeira nota interestadual.
4. **Série**: o padrão é 1. Se quiser separar venda de material (série 2) de outra coisa,
   diga qual numeração.
5. **Quem pode emitir em produção**: hoje é quem tem `module:fiscal` **e** acesso ao e-mail do
   OTP (você). Se quiser que outra pessoa emita, é uma decisão de permissão.
6. **As 2 notas antigas** (`rejeitada`, série 1, nºs 1 e 2) ficam com ambiente «(não registrado)».
   Se você souber em qual ambiente elas foram, dá para registrar — eu não inventei.
