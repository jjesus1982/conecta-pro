# DGX Z5 — Do orçamento à nota: o emissor CONSOME, nunca cria

**Data:** 24/09/2026 · **Onda:** 8 (NF-e de material para os dois CNPJs) · **Módulo:** `fiscal`
**Branch:** `dgx/z5-orcamento-para-nota` · **Container de teste:** `teste-dgx-z5` (porta 8285, já parado)

> *«os orçamentos são criados pelo Claude Cowork via conector Conecta PRO MCP, até termos o sistema
> todo pronto. Não vai criar orçamento dentro do emissor de nota: ou subo o arquivo, ou crio dentro
> do CRM etc. Obedecer o fluxo natural.»* — Jordan

Esta frase é a frente inteira. **Não existe «novo orçamento» na tela de nota fiscal.** O emissor
tem duas portas e nenhuma outra: buscar um orçamento que já existe, ou subir o arquivo dele.

---

## §1 Estado antes (medido no sandbox = cópia de produção de 23/09)

| O quê | Medida |
|---|---|
| Propostas (`proposals`) | **37** — 26 `draft`, 5 `rejected`, 3 `sent`, **3 `accepted`** |
| Itens de proposta (`proposal_items`) | **177** (`code, name, description, unit, quantity, unit_price, discount_percent, total`) |
| Cotações de compra (`purchase_quotations`) | 4 — **direção contrária**, é COMPRA (fornecedor → nós). Não serve e não foi usada |
| Rascunhos de nota | **0** — não existia o conceito |
| NF-e autorizadas | **0**. As duas únicas tentativas são de 11/04/2026, ambas rejeitadas — a última por «Informado NCM inexistente» |
| Caminho orçamento → nota | **nenhum**. Nada ligava `proposal_items` a `nfe_itens`, em código ou em tela |
| Extrator de documento por LLM | **já existia**: `POST /action/extrair-documento` no `departamento_pessoal.py`, com `_CAMPOS_EXTRAIVEIS`, `_PROMPT_EXTRACAO` e `_imagens_do_arquivo()` |

## §2 O que o DGX tem

O DGX faz a nota nascer de um orçamento aprovado: o operador escolhe o orçamento, o sistema traz
os itens já cadastrados, e o que não tem cadastro fiscal fica pendente até alguém resolver. O que
o DGX **não** tem e aqui foi exigido pelo dono: a segunda porta (subir o arquivo do orçamento) e
o **rastro obrigatório** — de que proposta, ou de que arquivo com hash, cada nota veio.

## §3 O que foi feito

### Arquivos

| Arquivo | Papel |
|---|---|
| `backend/modules/fiscal/services/orcamento_para_nota.py` | **novo** — toda a regra |
| `backend/modules/operacional/controllers/redesign_builders/dgx_z5_orcamento_nota.py` | **novo** — 4 telas + 4 ações + 1 rota de leitura para a Z3 |
| `backend/scripts/orq/test_oraculo_z5_orcamento_nota.py` | **novo** — oráculo (6 afirmações) |
| `backend/modules/operacional/controllers/redesign_builders/fiscal.py` | **+4 linhas**: import, `*_z5.ABAS` no fim do `EXTRA_MENU`, `await _z5.telas(db, out)` antes do `return out` |

### O serviço

- `listar_orcamentos(db, filtro)` — propostas faturáveis com cliente, valor, data, nº de itens e se já têm rascunho.
- `itens_do_orcamento(db, proposal_id)` — itens normalizados para virar item de nota.
- `itens_do_arquivo(db, nome, dados)` — o extrator, com alvo `orcamento`.
- `normalizar_itens_extraidos(bruto)` — **função pura**: a resposta crua do LLM vira itens, com confiança grampeada em [0,1] e trecho de origem. É nela que o oráculo bate, sem rede e sem custo.
- `casar_produtos(db, itens)` — casa com `fin_produtos` por código, depois por descrição; o resto volta `produto_id = None` + sugestão de NCM.
- `preparar_rascunho(db, origem, …)` — grava o rascunho **com a origem** e devolve o id.
- `itens_para_nota(db, rascunho_id)` — a porta que a Z3 consome; **recusa** rascunho com item sem produto.
- `casar_item_manual(db, item_id, produto_id, usuario)` — a escolha do humano.
- `rascunho_existente(db, …)` — evita pagar uma segunda leitura por LLM do mesmo arquivo.

### Decisões declaradas

1. **Faturável = `accepted` só** (`STATUS_FATURAVEIS`). `draft` e `sent` estão em negociação, `rejected` morreu. Emitir documento fiscal de um negócio não fechado é pior que não emitir.
2. **O valor vem de `proposal_items.total`**, não de `quantidade × unitário`: o desconto por item já está aplicado nele, e é ele que o cliente aceitou. Item `is_optional` ou `is_active = false` **não entra** — opcional é o que o cliente pode não ter comprado.
3. **O rascunho mora em tabela própria, não em `nfes`.** `nfes` exige endereço completo do destinatário, CRT do emitente, forma e meio de pagamento — tudo `NOT NULL`. Um orçamento não traz nada disso, e preencher com placeholder seria inventar dado fiscal. Além disso `nfes` é território da Z2, que ainda escolhe entre os dois emissores. **A ponte é a coluna `nfe_id`** no rascunho: a Z3 emite e grava o id ali, e o rastro fecha.
4. **O extrator reusa o mecanismo do DP, não o endpoint.** `_imagens_do_arquivo()` (magic bytes em vez de extensão, recusa explicada do HEIC do iPhone, PDF escaneado rasterizado com fitz) é importado e reusado tal e qual. O que é novo é só o prompt e a normalização, porque o alvo `orcamento` devolve uma **lista** de itens e o endpoint do DP devolve um dict plano de campos — enfiar lista naquele contrato quebraria os alvos `admissao`/`prestador_pj`. **`departamento_pessoal.py` não foi tocado.**
5. **Nunca cria produto.** Item sem produto volta pendente com sugestão de NCM pela descrição (`difflib`, stdlib, corte 0.88 para casar e 0.55 para só sugerir). NCM inventado é exatamente a rejeição de 11/04/2026.
6. **Idempotente por origem**, garantido por índice único parcial no banco (não por `if` em Python): um rascunho ativo por proposta, um por `sha256` do arquivo. Pedir de novo devolve o mesmo id com `ja_existia = True`.
7. **Este módulo não tem o prefixo `_`.** O `fiscal.py` não expõe `router`, e criar um lá só para esta frente colidiria com Z1–Z4, que estão no mesmo arquivo nesta onda. Sem `build`, sem `SLUG` e sem `EXTRA_MENU`, o discovery só monta o `router` daqui — as abas e a chamada de `telas()` ficam no `fiscal.py`.

### DDL que o `_ensure` aplica em produção no 1º acesso

```sql
CREATE TABLE IF NOT EXISTS fiscal_nota_rascunho (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), origem_tipo varchar(10) NOT NULL,
  proposal_id uuid, arquivo_nome text, arquivo_hash varchar(64),
  cliente_nome text, cliente_documento varchar(20),
  valor_total numeric(15,2) NOT NULL DEFAULT 0, status varchar(20) NOT NULL DEFAULT 'rascunho',
  nfe_id uuid, observacao text, criado_por text,
  criado_em timestamp NOT NULL DEFAULT now(), atualizado_em timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS ux_z5_rascunho_proposta ON fiscal_nota_rascunho (proposal_id)
  WHERE proposal_id IS NOT NULL AND status <> 'cancelado';
CREATE UNIQUE INDEX IF NOT EXISTS ux_z5_rascunho_arquivo ON fiscal_nota_rascunho (arquivo_hash)
  WHERE arquivo_hash IS NOT NULL AND status <> 'cancelado';
CREATE TABLE IF NOT EXISTS fiscal_nota_rascunho_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rascunho_id uuid NOT NULL REFERENCES fiscal_nota_rascunho(id) ON DELETE CASCADE,
  numero_item integer NOT NULL, codigo varchar(60), descricao varchar(200) NOT NULL,
  unidade varchar(6) NOT NULL DEFAULT 'UN', quantidade numeric(15,4) NOT NULL,
  valor_unitario numeric(15,10) NOT NULL, desconto_percent numeric(9,4) NOT NULL DEFAULT 0,
  valor_total numeric(15,2) NOT NULL, produto_id integer, produto_codigo varchar(60),
  ncm varchar(8), ncm_sugerido varchar(8), casamento varchar(20) NOT NULL DEFAULT 'nao_casado',
  confianca numeric(4,3), trecho_origem text, casado_por text,
  criado_em timestamp NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_z5_item_rascunho ON fiscal_nota_rascunho_item (rascunho_id);
```

**Duas tabelas novas, zero `ALTER` em tabela de outra frente, zero escrita em `proposals`.**

### Telas (grupo «Do orçamento à nota», no FIM do menu do fiscal)

| Aba | Deep-link | O que é |
|---|---|---|
| NF-e a partir de um orçamento | `/redesign/fiscal?t=nfe-do-orcamento` | as propostas aceitas, com «Gerar rascunho de nota» por linha |
| NF-e a partir de um arquivo | `/redesign/fiscal?t=nfe-do-arquivo` | upload; a prévia volta com confiança, trecho de origem e casado/não casado por item |
| Rascunhos de nota (origem) | `/redesign/fiscal?t=nfe-rascunhos` | o rastro: «Proposta PROP-2026-00096» ou «Arquivo x.pdf · sha e3a79039»; cancelar com motivo |
| Itens sem produto (casar) | `/redesign/fiscal?t=nfe-rascunho-itens` | onde a **pessoa** escolhe o produto do cadastro fiscal do item pendente |

Ações: `z5-rascunho-do-orcamento`, `z5-rascunho-do-arquivo`, `z5-rascunho-casar-item`,
`z5-rascunho-cancelar` (todas `POST /api/v1/redesign/action/…`, gate `module:fiscal`) e a leitura
`GET /api/v1/redesign/z5-rascunho/{id}/itens-para-nota`, que é **a porta da Z3**.

## §4 Oráculo

`backend/scripts/orq/test_oraculo_z5_orcamento_nota.py` — 6 afirmações: soma ao centavo; item sem
produto não vira item de nota; idempotência por origem; o extrator devolve os campos obrigatórios
e marca confiança; o rascunho guarda a origem; **e nenhuma rota da frente cria orçamento**
(varredura estática, sem `INSERT INTO proposals/proposal_items` nem `Proposal(`/`ProposalItem(`).

```bash
WT=<a worktree>
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
       | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,mode=1777 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_z5_orcamento_nota.py
```

**VERMELHO (antes do código):**

```
ImportError: cannot import name 'orcamento_para_nota' from 'modules.fiscal.services'
```

**VERDE (depois):**

```
· varredura estática: 2 arquivo(s)
· extrator: 2 item(ns) de 4 linhas cruas
· fixture PROP-2026-00096: itens somam R$ 46112.00 no orçamento e R$ 46112.00 no rascunho
· recusa correta: 2 item(ns) sem produto — «2 item(ns) sem produto do cadastro fiscal: item 1 «Câmera IP»
· depois do humano casar: 2 item(ns) liberados
· 1 rascunho(s) de proposta conferido(s) ao centavo · 2 no total
TOTAL desvios: 0
OK Z5: o emissor consome orçamento (proposta ou arquivo), soma ao centavo, guarda a origem e NÃO cria orçamento
```

**A varredura estática pegou o próprio autor antes de pegar qualquer outro.** A 1ª versão dela
acusou o serviço porque o **docstring** dele cita `INSERT INTO proposals` ao explicar a regra do
dono. A correção não foi apagar a explicação: foi ensinar a varredura a ler só o que executa
(`ast`, docstrings zeradas, comentários fora — **strings normais ficam**, porque é dentro de
string que o SQL da casa mora e é lá que um INSERT proibido apareceria).

### Prova viva (HTTP, porta 8285, contra o sandbox)

- Rascunho da `PROP-2026-00096`: 4 itens, **R$ 46.112,00** — igual à soma dos itens da proposta ao centavo (a proposta tem `total` 45.312,00 por causa de um desconto de cabeçalho; o rascunho copia os **itens**, e é isso que vira linha de nota).
- 2ª chamada: **mesmo id**, `ja_existia: true`, nada duplicado.
- `itens-para-nota` devolveu **HTTP 409** listando os 4 itens sem produto, por extenso.
- Upload de um orçamento de CFTV em texto: leu **4 itens** (R$ 18.981,00, idêntico ao documento), descartou `SUBTOTAL`/`TOTAL GERAL`, converteu `1.250,00 → 1250.00` e `1.781,00 → 1781.00` certo, e trouxe o trecho de origem de cada linha.
- Re-upload do mesmo arquivo: devolveu o mesmo rascunho **sem gastar uma segunda chamada de LLM** (o `sha256` responde antes).
- «Casar produto»: 94 opções do cadastro, item vinculado, e o `itens-para-nota` passou a cobrar só os 3 restantes.

Tudo o que o teste criou no sandbox foi apagado (`fiscal_nota_rascunho` voltou a 0 linhas). O
container `teste-dgx-z5` foi parado. **Nada foi transmitido à SEFAZ.**

## §5 O que NÃO foi feito, e por quê

1. **Não emite nota.** O fim desta frente é um rascunho. Emitir (homologação, `tpAmb = 2`) é Z2/Z3.
2. **Não criei o cadastro fiscal de produto.** É da Z1. `casar_produtos` pergunta ao banco se `fin_produtos` existe (`to_regclass`) e, quando não existe, devolve todos os itens pendentes com o motivo escrito — em vez de estourar. Isso foi medido de verdade: durante esta frente a tabela **sumiu e voltou** no sandbox, porque a Z1 estava recriando-a.
3. **Não toquei em `nfes`, `nfe_itens`, `fin_produtos`, `fin_produto_tributacao`** nem em qualquer arquivo das Z1–Z4.
4. **Não mexi no `departamento_pessoal.py`.** O alvo `orcamento` não cabe no `_CAMPOS_EXTRAIVEIS` (dict plano de campos) sem quebrar `admissao` e `prestador_pj`. Reusei o mecanismo, não o endpoint.
5. **Não aceito `.xlsx`.** O leitor da casa (`extrair_texto_arquivo`) abre PDF, DOCX e texto; planilha chega como binário e viraria lixo. A tela **diz isso** em vez de aceitar e falhar em silêncio.
6. **Não há tela de emissão nem DANFE aqui** — Z3.
7. **Não há CNPJ emitente no rascunho.** O orçamento não diz por qual empresa do grupo a nota sai. Quem escolhe é a tela de emissão (Z2/Z3), que já tem o seletor Eletrônica × Patrimonial.
8. **`fin_produtos.id` é `integer` e `nfe_itens.produto_id` é `uuid`.** Não são o mesmo cadastro. Guardei `produto_id integer` (aponta para a Z1) e deixei o `nfe_itens.produto_id` para quem emitir resolver — não inventei conversão.

## §6 Como o Jordan testa amanhã

1. **Fiscal → «NF-e a partir de um orçamento»** (último grupo do menu, «Do orçamento à nota»). Devem aparecer as propostas **aceitas** — hoje 3. Repare no subtítulo: ele diz quantas ficaram de fora e em que estágio.
2. Clique **«Gerar rascunho de nota»** numa delas e confirme. A mensagem diz quantos itens entraram, o total, e quantos ainda estão sem produto.
3. Clique de novo no mesmo orçamento: tem que dizer *«já tem um rascunho, abri o que existe»*. **Não pode aparecer um segundo rascunho.**
4. **«Rascunhos de nota (origem)»**: a 1ª coluna tem que dizer de onde veio — `Proposta PROP-…`.
5. **«NF-e a partir de um arquivo»**: suba um PDF de orçamento. O resultado lista item por item com a **leitura em %**, a **linha do documento** de onde saiu e se casou com o cadastro. Suba o MESMO arquivo de novo: tem que reabrir o que existe.
6. **«Itens sem produto (casar)»**: escolha o produto de um item e confirme. Ele sai da conta de pendentes.
7. Prova de que o item pendente não passa: `GET /api/v1/redesign/z5-rascunho/<id>/itens-para-nota` com o token — deve vir **409** listando quem falta.
8. Prova da regra do dono: em nenhuma das quatro telas existe botão de «novo orçamento».

## §7 Decisões que só o dono pode tomar

1. **Faturável é só `accepted`?** Hoje são 3 propostas de 37. Se o fluxo real fatura proposta `sent` (cliente aceitou por WhatsApp e o CRM não foi atualizado), diga — é uma linha (`STATUS_FATURAVEIS`).
2. **As 3 propostas aceitas são de SERVIÇO, não de material** (portaria 12x36, app Conecta Plus, aluguel de equipamento). Serviço é **NFS-e**, não NF-e. A onda 8 é «NF-e de material». Ou o material vem por arquivo (porta B), ou falta cadastrar no CRM os orçamentos de material — não dá para adivinhar.
3. **O que o rascunho faz com o desconto de cabeçalho da proposta?** Hoje: ignora. A `PROP-2026-00096` tem itens somando 46.112,00 e `total` 45.312,00 (800,00 de desconto geral). A nota sai pelos itens. Se o desconto geral tem de aparecer na nota, ele precisa virar desconto por item ou `valor_total_desconto` — e isso muda base de cálculo de imposto. **Não decidi sozinho.**
4. **Quem pode gerar rascunho?** Gatei em `module:fiscal`. Se o comercial também deve poder, é trocar o gate.
5. **`modules/fiscal/` está marcado como DEPRECATED** desde 03/2026, com remoção prevista para 05/2026 — que passou e não aconteceu. O serviço foi para lá porque o brief pediu esse caminho. Se o destino certo é `modules/fiscal_contabil/`, é um `git mv` e um import.
6. **Rascunho tem validade?** Hoje fica para sempre até alguém cancelar. Se orçamento vencido não deve virar nota, o `valid_until` da proposta já existe e pode virar trava.
