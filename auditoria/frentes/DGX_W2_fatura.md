# DGX W2 — Fatura como DOCUMENTO: o papel que faltava entre o contrato e a NFS-e

**Data:** 24/09/2026 · **Branch:** `dgx/w2-fatura` · **Módulo:** financeiro · **Porta de teste:** 8252

---

## §1 Estado antes (medido) — a diferença entre «recebível» e «fatura»

A lacuna `faturamento_financeiro.md` classificou esta linha como **TEMOS PARCIAL**: «temos recebível,
não temos o DOCUMENTO». Esta é a medida, no sandbox (cópia de produção de 23/09), do que era cada coisa:

| | **RECEBÍVEL** — o que já tínhamos | **FATURA** — o que faltava |
|---|---|---|
| tabela | `receivable_accounts` — **52 linhas**, 31 de origem `'contrato'`, R$ 1.110.989,70 | `fin_faturas` — `to_regclass` **NULL**: não existia |
| como nasce | `gerar_recebiveis(mes, ano)` varre os 14 contratos ativos (R$ 289.800,06/mês) e cria um título por contrato/competência | a mão **ou** do contrato, e pode nascer **rascunho** (existe antes de valer) |
| o que descreve | uma linha: `description` + `gross_value`. **Sem itens** | período de prestação + **itens discriminados** (posto, adicional, avulso), com código LC 116 por item |
| número | `code` interno (`REC-<8 chars do uuid>-202609`) — identificador de sistema, não de documento | **número sequencial sem buraco** (00001, 00002…), como o recibo da F11 |
| papel | **não imprime**: não havia rota de PDF para um recebível | PDF timbrado, **uma fatura por página**, imprimível em **lote** por competência |
| quem paga | `customer_name` = quem contratou | sai no nome da **fonte pagadora** (F12) quando ela existe |
| repetir o mês | rodar `gerar_recebiveis` de novo é idempotente pelo `code` | «copiar em lote»: N faturas da competência viram rascunho da seguinte, de uma vez |

**O que o dono ganhou, em uma frase:** antes, o que o cliente podia conferir era a NFS-e (fiscal) e o
boleto (cobrança) — e entre o contrato e a nota não havia papel nenhum. Se o síndico perguntasse
«por que R$ 22.100 este mês?», a resposta estava numa linha de contas a receber, sem discriminação.
Agora existe o documento que responde item a item, antes da nota, e que o financeiro imprime em lote.

Outras medidas que definiram decisões de implementação:

- `contract_items`: **16 linhas**, mas só **2 dos 14 contratos ativos** as têm com valor.
- `posts.salario_base` (a vaga da T3): **NULL em 17/17** — o caminho «Σ vagas × salário × encargos»
  não produziria número nenhum hoje. Por isso «a partir do contrato» usa `contract_items` quando
  existem com valor, e senão **uma** linha com o `monthly_value`. Nunca número inventado.
- `crm_fontes_pagadoras` (F12): **0 linhas** hoje. O caminho está pronto e provado por fixture;
  quando o Jordan cadastrar a primeira administradora, a fatura já sai no nome dela.
- `fin_condicoes_pagamento` (4 semeadas) e `fin_codigos_servico` (8, LC 116) da F11: **reusados**.
  Nenhum cadastro novo foi criado nesta frente.
- `receivable_accounts.fonte_pagadora_id` e `payment_method_id` **já existiam** (F12/V5) — a fatura
  preenche o primeiro ao gerar a conta.

---

## §2 O que o DGX tem (`/Faturas`)

Do relatório `DGX_T4_faturamento_financeiro.md` e da passagem por dentro do trial: fatura manual com
**período, vencimento, itens, descrição padrão**, botão **GerarConta** (vira conta a receber),
**copiar em lote** (replica a competência) e **imprimir lote** (um PDF com todas). No trial,
`Faturas/GerarConta` e `Faturas/Imprimir` devolviam **HTTP 500** — ou seja, o DGX tem o desenho, e nem
sempre o funcionamento. As quatro capacidades foram implementadas aqui, com as paredes que o trial
não tinha (idempotência do GerarConta, não-duplicação do lote, trava de cancelamento).

---

## §3 O que foi feito

**Arquivos**

- `backend/modules/financial/services/fin_faturas.py` — **novo**. DDL (`ensure`), regra
  (`criar`, `itens_do_contrato`, `item_incluir`, `item_excluir`, `emitir`, `gerar_conta`, `copiar`,
  `copiar_lote`, `cancelar`, `dados_documento`, `pdf_lote`) e o gerador de PDF timbrado
  (`build_faturas_pdf`, marca vinda de `crm/services/pdf_branding`).
- `backend/modules/operacional/controllers/redesign_builders/_dgx_w2_fatura.py` — **novo**.
  4 telas, 7 ações, 2 GETs de PDF, gramática de item em texto (`itens_texto`).
- `backend/modules/operacional/controllers/redesign_builders/_fin_grupos.py` — 4 abas no **fim**
  de `g-receber` (`# dgx w2`).
- `backend/modules/operacional/controllers/redesign_builders/financeiro.py` — 3 linhas de plug
  (import + `telas(db, out)` antes de `montar_grupos`; `include_router`).
- `backend/scripts/orq/test_oraculo_w2_fatura.py` — **novo**, 19 checagens.

**DDL que `ensure` aplica em produção no 1º acesso** (idempotente, nunca alembic):

```sql
CREATE TABLE IF NOT EXISTS fin_faturas (id serial PK, numero int, cliente_id uuid,
  fonte_pagadora_id int, contrato_id uuid, competencia char(7), periodo_inicio date,
  periodo_fim date, vencimento date, condicao_pagamento_id int, descricao_padrao text,
  valor_total numeric(14,2), status text, receivable_id uuid, nfse_id uuid, observacao text,
  criado_por text, emitida_em timestamptz, created_at timestamptz,
  CHECK status IN (rascunho|emitida|enviada|paga|cancelada), CHECK periodo_fim >= periodo_inicio,
  CHECK (rascunho|cancelada) OR numero IS NOT NULL)
ALTER TABLE fin_faturas ADD COLUMN IF NOT EXISTS origem_fatura_id int
CREATE UNIQUE INDEX ux_fin_faturas_numero        ON fin_faturas (numero) WHERE numero IS NOT NULL
CREATE UNIQUE INDEX ux_fin_faturas_contrato_comp ON fin_faturas (contrato_id, competencia)
                                                 WHERE contrato_id IS NOT NULL AND status <> 'cancelada'
CREATE UNIQUE INDEX ux_fin_faturas_origem_comp   ON fin_faturas (origem_fatura_id, competencia)
                                                 WHERE origem_fatura_id IS NOT NULL AND status <> 'cancelada'
CREATE INDEX ix_fin_faturas_comp ON fin_faturas (competencia, status)
CREATE TABLE IF NOT EXISTS fin_fatura_itens (id serial PK, fatura_id int REFERENCES fin_faturas
  ON DELETE CASCADE, descricao text, quantidade numeric(12,3), valor_unitario numeric(14,2),
  valor_total numeric(14,2), codigo_servico_id int, posto_id uuid, created_at timestamptz,
  CHECK quantidade > 0)
CREATE INDEX ix_fin_fatura_itens_fat ON fin_fatura_itens (fatura_id)
```

Nenhum `DROP`, `DELETE` ou `UPDATE` em dado que a frente não criou. **Zero seed.**

**Telas** (grupo `g-receber`, deep-link `/redesign/financeiro?t=<id>`):

| id | aba | o que faz |
|---|---|---|
| `faturas` | Faturas | lista com nº, competência, sacado, contrato, nº de itens, vencimento, total, status e «conta gerada». Por linha: **+ Item** (só rascunho), **Emitir**, **Gerar conta**, **Copiar**, **Cancelar**, e o **PDF**. No topo, o PDF do **lote** da competência corrente. |
| `fatura-nova` | Nova fatura | cliente, contrato, fonte pagadora, competência, vencimento, período, condição, descrição padrão, itens em texto e observação. |
| `fatura-itens` | Itens das faturas | a discriminação que sai no PDF, com seletor por fatura; «Excluir» só enquanto rascunho. |
| `faturas-copiar-lote` | Copiar faturas em lote | form **gated + confirm**: competência origem → destino, opcionalmente um contrato. |

**Rotas de documento**

- `GET /api/v1/redesign/faturas/{id}/pdf` — a fatura avulsa (rascunho sai marcado «RASCUNHO»).
- `GET /api/v1/redesign/faturas/lote/pdf?competencia=MM/AAAA` — **uma fatura por página**, canceladas
  fora. Declarada ANTES da rota `{id}` para a rota literal casar primeiro.

**Gramática dos itens em texto** (a mesma do F9/U5), uma linha por item:
`descrição | quantidade | valor unitário | LC 116 (opcional)`. Código LC 116 desconhecido fica sem
vínculo — não derruba o lançamento.

**As paredes**

1. Número só existe depois de `emitir`. Rascunho não consome série → **sem buraco**.
2. `pg_advisory_xact_lock('fin_faturas')` na emissão: dois cliques simultâneos não pegam o mesmo número.
3. `valor_total` **nunca é digitado** — é recontado de `Σ quantidade × valor_unitario` a cada mudança.
4. Itens **travam na emissão** (409): fatura emitida é documento, não rascunho.
5. `gerar_conta` é **idempotente** por `receivable_id` e **não recebe** (o título nasce `pendente`).
6. Uma fatura viva por (contrato, competência) e por (fatura de origem, competência) — é o que faz
   «copiar em lote» rodado duas vezes **não duplicar**, inclusive para a fatura avulsa sem contrato.
7. `cancelar` recusa (409) quando o recebível está `paga`/`parcial` ou tem `paid_value > 0`.

**Marca do PDF:** a fatura sai no CNPJ da empresa **dona do contrato** (`contracts.empresa_id` →
`empresas.slug` → `pdf_branding.empresa_branding`). Medido: CTR-2026-00017 → **Eletrônica**;
CTR-2026-00019 → **Patrimonial**. Fatura avulsa (sem contrato) sai pela **Patrimonial** — mesma
decisão do recibo (F11 §7.4: é quem fatura serviços).

---

## §4 Oráculo

`backend/scripts/orq/test_oraculo_w2_fatura.py` — 19 checagens, fixtures `'FIXTURE DGX W2'` nas
competências `2099-03`/`2099-04`, apagadas ao fim (conferido: `fin_faturas`, `fin_fatura_itens` e
`receivable_accounts WHERE origem='fatura'` voltaram a **0**).

```bash
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
       | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_w2_fatura.py
```

**VERMELHO (antes de uma linha de código):**

```
FALHOU: módulo da frente W2 não importa: cannot import name 'fin_faturas' from 'modules.financial.services'
TOTAL w2_fatura: 1 falha
```

**VERDE (depois):**

```
TOTAL w2_fatura: 19 checagens · 0 falha(s)
OK w2_fatura: telas com porta, numeração sem buraco sob concorrência, total == Σ itens,
GerarConta idempotente e sem receber, lote copiado uma vez só, cancelar barra recebível pago,
impressão em lote com uma fatura por página, fonte pagadora no lugar do cliente
```

**Blocos:** (a) 4 telas com aba em `_fin_grupos` · (b) duas emissões **concorrentes** (sessões
separadas, `asyncio.gather`) → números distintos e consecutivos, série sem buraco por SQL próprio
(`count == max − min + 1`), 2ª emissão da mesma fatura recusada sem mexer na série · (c) `valor_total`
== Σ itens por SQL próprio, depois de incluir item · (d) `gerar_conta` 2× → mesmo `receivable_id`,
1 recebível, `net_value` == `valor_total`, status `pendente` · (e) `copiar_lote` 2× → copiadas uma
vez só · (f) `cancelar` recusa com 409 fatura de recebível pago · (f2) `cancelar` **aceita** fatura
com recebível apenas pendente · (g) PDF de N faturas tem N páginas · (i) contrato que já tem título
de «Gerar do mês» na competência faz `gerar_conta` **avisar** (o aviso é string: se o SQL dele estiver
errado ele nunca aparece, e aí seria verde cego numa tela de dinheiro) · (h) com fonte pagadora, o
sacado é a razão social + CNPJ **dela**; sem fonte, é o cliente.

**Vizinhos verdes (mesma rodada):**

```
TOTAL financeiro_cadastros: 28 checagens · 0 falha(s)
TOTAL t4_faturamento_financeiro: 19 checagens · 0 falha(s)
TOTAL v5_fiscal_relatorios: 23 checagens · 0 falha(s)
```

**Prova HTTP** (container `teste-dgx-w2`, porta 8252, **já parado**; fixtures apagadas):

- `GET /api/v1/redesign/data/financeiro` → **200**, as 4 telas com aba em `g-receber`.
- Fatura **do contrato** CTR-2026-00019 com itens em branco → puxou as 2 linhas de `contract_items`
  (AGP Diurno 2 × R$ 5.302,89 + AGP Noturno 2 × R$ 5.747,11) = **R$ 22.100,00**.
- Segunda fatura do mesmo contrato/competência → **409**.
- Fatura **avulsa** com itens em texto (`Portaria 12x36 | 3 | 4.500,00 | 11.02`) → R$ 14.400,00;
  «+ Item» (hora extra 2 × 150) → **R$ 14.700,00** (o total recontou sozinho).
- Emitir as duas → nº **00001** e **00002**; incluir item na emitida → **409**.
- `Gerar conta` 2× → `criado:true` e depois `criado:false` com o **mesmo** `receivable_id`.
- `Cancelar` com recebível **pendente** → aceito; com recebível marcado `paga` → **409**.
- `faturas/lote/pdf?competencia=03/2099` com 2 faturas vivas → **200, 2 páginas** (a cancelada fora).
- `copiar-lote 03/2099 → 04/2099` 2× → `copiadas: 2` e depois `copiadas: 0, puladas: 2`.
- PDF timbrado conferido por extração de texto: `FATURA DE SERVIÇOS`, CNPJ da empresa do contrato,
  `Nº 00003 • Período 01/03/2099 a 31/03/2099`, tabela de itens com TOTAL, rodapé
  «Fatura é documento de cobrança: não substitui a NFS-e».

**Dois defeitos que só a prova HTTP pegou** (o oráculo verde não bastava):

1. **Deadlock na emissão concorrente.** `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pega
   `ACCESS EXCLUSIVE` **mesmo quando a coluna já existe**; com `ensure` no começo de toda ação, duas
   ações simultâneas na mesma tabela travavam uma na outra. Corrigido com um guard barato por SQL
   (`to_regclass` + `information_schema`) que faz `ensure` sair sem tocar em DDL quando já está pronto.
2. **Cancelamento travado pelo status errado.** `gerar_conta` marcava a fatura como `enviada`, e
   `cancelar` só aceitava `rascunho`/`emitida` — resultado: **nenhuma** fatura com conta gerada podia
   ser cancelada, nem a que ninguém pagou. Corrigido na raiz: `gerar_conta` **não mexe no status**
   (ele cria o título, não envia nada a ninguém); quem barra o cancelamento é o **recebível pago**.
   Virou a checagem (f2) do oráculo.

---

## §5 O que NÃO foi feito, e por quê

1. **NFS-e não foi tocada.** A nota é o documento fiscal; a fatura é o comercial que a antecede.
   `fin_faturas.nfse_id` existe como elo e **não tem escritor** — amarrar fatura × nota é outra frente.
2. **Status `enviada` e `paga` não têm escritor.** Estão no `CHECK` porque são o ciclo do DGX, mas
   ninguém os escreve: não há envio ao cliente (e-mail da fatura) nem reflexo da baixa do recebível
   na fatura. O que a tela mostra de dinheiro é o status do **recebível**, que é verdade. Marcar
   «enviada» sem envio seria mentira de tela — foi exatamente o defeito 2 do §4.
3. **Boleto/PIX a partir da fatura** — fora do mandato (Inter não foi tocado). O caminho é:
   fatura → `Gerar conta` → recebível → emitir boleto pelas telas que já existem.
4. **Condição de pagamento não parcela a fatura.** O campo é gravado e sai impresso, mas `gerar_conta`
   cria **um** título com o vencimento da fatura. Parcelar em N títulos já existe em
   `receivable-condicao` (F11) e duplicar a regra aqui seria abstração para um caso que ninguém pediu.
5. **Itens por vaga/posto** (`posto_id` está na tabela, sem tela): `posts.salario_base` é NULL em
   17/17 hoje, então a tela não teria número para mostrar. A coluna fica pronta para quando a T3
   tiver salário por vaga preenchido.
6. **Proporcional por dias** na fatura do contrato: quem faz pró-rata é `gerar_recebiveis`
   (parâmetro `fiscal.nfse_valor_proporcional_dias`, T4, hoje vazio = desligado). A fatura cobra o
   item como ele está no contrato — se o dono ligar o pró-rata, os dois caminhos vão divergir e isso
   precisa de decisão dele (§7.3).
7. **Fatura com mais de uma página no lote**: há um `ponytail:` no código dizendo o teto — o timbrado
   casa página N com fatura N-1, então uma fatura que transbordasse levaria a marca da seguinte na
   folha de transbordo. Com os volumes de hoje (2 a 4 itens) não acontece; o conserto está anotado.
8. **`crm/services/doc_pdf.py` não foi tocado.** O gerador da fatura mora em `fin_faturas.py`: aquele
   arquivo está fora do formato do `ruff format` **desde antes desta frente**, e encostar nele faria
   o hook de pre-commit reescrever ~5 mil linhas de código de outras frentes no meio da onda. A marca
   continua centralizada em `pdf_branding`, que é o que a regra da casa exige.

---

## §6 Como o Jordan testa amanhã (cliques)

1. **Financeiro › Receber › Nova fatura.** Escolha um contrato ativo, competência `10/2026`,
   vencimento `10/10/2026`, **deixe os itens em branco** → «Criar rascunho». A mensagem diz quantos
   itens vieram do contrato e o total; o botão do PDF abre o rascunho timbrado.
2. **Receber › Faturas.** A fatura aparece como `rascunho`. Clique **+ Item**, acrescente
   «Hora extra · 2 · 150,00» e recarregue: o total mudou sozinho.
3. **Emitir** → a fatura ganha o nº `00001` e os itens travam (tentar **+ Item** some da linha).
   O PDF agora sai numerado, no CNPJ da empresa dona do contrato.
4. **Gerar conta** → aparece em **Contas a Receber** com o valor da fatura, `pendente`. Clique de
   novo: diz «já existe» e não cria a segunda. Boleto/PIX continuam sendo ato separado.
5. **Copiar** (na linha) para `11/2026`, ou **Receber › Copiar faturas em lote** de `10/2026` para
   `11/2026`. Rode **duas vezes**: a segunda diz «0 copiadas; N já existiam».
6. **Imprimir lote**: no topo de «Faturas», o botão do PDF da competência corrente — um PDF, uma
   fatura por página, canceladas fora.
7. **Cancelar** uma fatura cujo recebível ainda não foi pago: aceita, e ela fica no histórico como
   `cancelada`. Tente cancelar uma cujo recebível já foi baixado: recusa com o motivo e manda
   estornar pelo recebível.
8. **Fonte pagadora** (quando houver): cadastre em Negócios › Fontes pagadoras (F12) e crie a fatura
   escolhendo a fonte — o PDF sai com a razão social e o CNPJ **dela**, e o corpo mostra «Serviços
   prestados a <cliente>».

---

## §7 Decisões que só o dono pode tomar

1. **A fatura substitui alguma coisa, ou soma?** A lacuna dizia «baixo — condomínio recebe NFS-e +
   boleto; fatura à parte é papel a mais». O documento existe agora; o Jordan decide se ele vai ao
   cliente (e como: junto do boleto? antes da nota?) ou se fica como conferência interna.
2. **Quem passa a faturar: fatura ou `gerar_recebiveis`?** Hoje convivem dois caminhos para o mesmo
   recebível — o do mês inteiro (`Gerar do mês`, 14 contratos de uma vez, sem itens) e o da fatura
   (um por vez, com itens). Não há trava impedindo os dois no mesmo mês: o `code` é diferente
   (`REC-…` × `FAT-…`), então **daria para duplicar o título**. Não inventei a trava porque ela
   depende da escolha: se a fatura vira o caminho oficial, `gerar_recebiveis` deve parar de criar
   para contrato que já tem fatura na competência (é uma linha de `WHERE NOT EXISTS`). **O que foi
   feito enquanto isso:** `Gerar conta` detecta o título gêmeo e devolve «ATENÇÃO: este contrato já
   tem o título REC-… de R$ … na mesma competência… confira se não está cobrando duas vezes» — avisa,
   não trava, e tem checagem no oráculo (bloco i) para o aviso não apodrecer calado.
3. **Pró-rata na fatura.** Se o parâmetro `fiscal.nfse_valor_proporcional_dias` for ligado (T4), o
   recebível do mês passa a ser proporcional e a fatura continua cobrando o item cheio do contrato.
   Os dois precisam concordar — e a regra certa depende do que está escrito no contrato.
4. **Emitente da fatura avulsa.** Sem contrato, ela sai pela **Patrimonial** (é quem fatura serviço).
   Se a Eletrônica também for emitir fatura avulsa, precisa de um seletor de emitente — mesma pendência
   que o recibo da F11 deixou.
5. **Numeração única ou por empresa?** A série é **única** (00001, 00002…) para as duas empresas do
   grupo. Se o contador exigir série por CNPJ, é uma coluna a mais no índice único.
6. **Envio ao cliente.** Não existe «enviar fatura por e-mail». A F4/T4 já têm `send_email` e a régua
   de cobrança; ligar a fatura nisso é uma frente pequena, mas é decisão de processo comercial.
