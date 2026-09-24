# DGX Z4 — A tributação certa: Zona Franca, SUFRAMA e os dois regimes

**Frente:** Z4 · onda 8 · branch `dgx/z4-tributacao-nfe` · módulo `fiscal`
**Data:** 24/09/2026 · sandbox `conecta_pro_staging` · porta de teste 8284 (parada)
**Pedido do dono:** «preciso urgente emitir notas fiscais».

> A nota pode ser aceita pela SEFAZ e ainda assim estar **errada em tributo** — e aí o problema
> aparece meses depois, com multa. Esta frente não emite nada. Ela responde, antes da primeira
> nota, **qual** tributo sai em **qual** operação, **com a norma ao lado de cada número** — e onde
> a norma não existe no repositório, diz «sem fonte — decisão do contador» e deixa NULL.
> **Nenhuma transmissão à SEFAZ. Nenhuma nota emitida. Nenhuma linha gravada em banco.**

---

## §1 — O MAPA DA TRIBUTAÇÃO (o entregável que vai para o contador)

### 1.0 Quem são as duas empresas — medido em `empresas` (não é constante de código)

| | CONECTAMAIS ELETRONICA | CONECTAMAIS PATRIMONIAL |
|---|---|---|
| CNPJ | 35.710.481/0001-03 | 66.014.833/0001-10 |
| Regime (`regime_tributario`) | `lucro_real` | `simples_nacional` (Anexo III) |
| **CRT na NF-e** | **3** (Regime Normal) | **1** (Simples Nacional) |
| Inscrição Estadual | 05.426.574-6 | **vazia** |
| Inscrição SUFRAMA | **210140500** | — |
| Município (IBGE) | 1302603 — Manaus | 1302603 — Manaus |
| Na NF-e sai | **CST** de ICMS | **CSOSN** |

Norma do CRT: **MOC NF-e 4.00, campo B21a**. Não existe coluna `crt` em `empresas` — é derivado
de `regime_tributario`, e a UF é derivada dos dois primeiros dígitos do IBGE (tabela de UF do
IBGE, a mesma do campo `cUF`). Ambas as derivações estão no serviço, comentadas.

---

### 1.1 O ACHADO QUE MUDA A LEITURA INTEIRA — as duas empresas estão DENTRO da ZFM

O brief pedia a linha «venda para a própria ZFM (com SUFRAMA do destinatário)». **Essa linha não
existe para estes dois CNPJs.**

O incentivo do **Convênio ICM 65/88** (com o **Decreto-Lei 288/1967, art. 4º**, que equipara a
remessa à ZFM a uma exportação) vale para quem vende **DE FORA** para a Zona Franca. Quem já está
em Manaus e vende para outra empresa de Manaus faz **operação interna do Amazonas** — CFOP
5101/5102, ICMS destacado, sem desoneração e sem `vICMSDeson`. **Ter SUFRAMA não muda isso**: a
inscrição 210140500 serve para a Eletrônica **receber** o incentivo quando compra de fora, não
para concedê-lo quando vende.

Consequência prática: **o CFOP 6109/6110 é inalcançável para os dois CNPJs hoje.** O serviço
implementa e testa esse ramo (para o caso de a casa abrir filial fora do AM), mas o classifica
como bloqueado e diz por quê. O oráculo trava isso: se alguém fizer o emitente de Manaus
desonerar por SUFRAMA, ele fica vermelho.

> **Onde isto já está errado no sistema hoje:** `fiscal_contabil/notas_fiscais/nfe/controller.py`
> (emissor — território da frente Z2) tem `is_zfm: bool = True` como **default** e escreve o texto
> «ZONA FRANCA DE MANAUS. SUFRAMA: 210140500» no `infCpl` de **toda** nota, com CST 40 e
> `vICMSDeson` fixo em `"0.00"`. Para uma venda interna em Manaus isso é: isenção que não existe,
> ICMS não destacado, e uma menção de benefício sem o valor desonerado que o Convênio 65/88
> cláusula primeira §1º exige. **Não toquei nesse arquivo** (é da Z2), mas está registrado no §7.

---

### 1.2 CONECTAMAIS ELETRONICA — lucro real, CRT 3

Calculado pelo serviço sobre um produto-base (NCM 85311000, R$ 1.000,00, quantidade 1, origem 0):

| Operação | CFOP (revenda / produção) | CST | Base | Alíquota | ICMS | vICMSDeson | Norma da alíquota |
|---|---|---|---|---|---|---|---|
| Dentro do AM, a contribuinte | 5102 / 5101 | 00 | R$ 1.000,00 | **20,00%** | R$ 200,00 | — | RICMS-AM — alíquota interna (dispositivo **não localizado no repositório**) |
| Dentro do AM, a não contribuinte | 5102 / 5101 | 00 | R$ 1.000,00 | **20,00%** | R$ 200,00 | — | idem |
| Outro estado, a contribuinte | 6102 / 6101 | 00 | R$ 1.000,00 | **12,00%** | R$ 120,00 | — | **Resolução do Senado Federal nº 22/1989, art. 1º, caput** |
| Outro estado, a não contribuinte | 6108 / 6107 | 00 | R$ 1.000,00 | **12,00%** | R$ 120,00 | — | idem + DIFAL, ver abaixo |
| «Para a ZFM» com SUFRAMA do destinatário | **5102 / 5101** | **00** | R$ 1.000,00 | **20,00%** | R$ 200,00 | **—** | é operação INTERNA — ver §1.1 |

Complementos do mesmo cálculo, com norma:

| Linha | Valor | Norma | Origem do número |
|---|---|---|---|
| **PIS** | 1,65% (CST 01) | Lei 10.637/2002, art. 2º | norma citada; **medido em 39 itens** de fornecedores CRT=3 a exatamente 1,65% |
| **COFINS** | 7,60% (CST 01) | Lei 10.833/2003, art. 2º | idem, 7,60% |
| **IPI** | **NULL** | Decreto 7.212/2010 (RIPI), art. 24 | empresa de **revenda** não é contribuinte do IPI. Equiparação a industrial: **sem fonte — decisão do contador** |
| **ICMS interestadual de mercadoria importada** (origem 1, 2, 3, 8) | 4,00% | **Resolução do Senado Federal nº 13/2012, art. 1º** | norma citada; **nenhum** item de origem estrangeira medido no repositório |
| **DIFAL** (não contribuinte em outro estado) | **NULL** | EC 87/2015; LC 190/2022; Convênio ICMS 236/2021 | a alíquota interna da UF de destino **não existe no repositório** → **sem fonte — decisão do contador** |
| **Substituição tributária** | **NULL** | Convênio ICMS 142/2018 | **não determinável**: `ncms.icms_cest` e `ncms.icms_st_mva` estão **vazios nas 10.515 linhas**; `tax_configurations` e `suframa_configs` têm **0 linhas** |

#### Sobre os 20,00% do ICMS interno do AM — leia isto

É o único número do mapa **sem dispositivo legal citado**. Ele **não foi chutado**: foi **medido
em 76 itens** de NF-e AM→AM com CST 00 em `nfe_entradas` (2025–2026), **todos a 20,00%**. O
serviço devolve o número com `origem_regra` apontando para essa medição e `norma` dizendo
literalmente «RICMS-AM — alíquota interna do Amazonas (dispositivo NÃO localizado no
repositório)». **O contador precisa carimbar o artigo.** Conferência inversa que dá confiança na
direção da regra: a única NF-e interestadual entrante do conjunto (RS→AM) veio a **7,00%** —
exatamente a Resolução 22/1989, art. 1º, parágrafo único.

---

### 1.3 CONECTAMAIS PATRIMONIAL — Simples Nacional Anexo III, CRT 1

| Operação | CFOP (revenda / produção) | CSOSN | Base | Alíquota | ICMS | Norma |
|---|---|---|---|---|---|---|
| Dentro do AM, a contribuinte | 5102 / 5101 | **102** | R$ 1.000,00 | **NULL** | **NULL** | Ajuste SINIEF 07/2005, Anexo, Tabela B |
| Dentro do AM, a não contribuinte | 5102 / 5101 | **102** | R$ 1.000,00 | **NULL** | **NULL** | idem |
| Outro estado, a contribuinte | 6102 / 6101 | **102** | R$ 1.000,00 | **NULL** | **NULL** | idem |
| Outro estado, a não contribuinte | 6108 / 6107 | **102** | R$ 1.000,00 | **NULL** | **NULL** | idem |
| «Para a ZFM» com SUFRAMA | 5102 / 5101 | **102** | R$ 1.000,00 | **NULL** | **NULL** | operação INTERNA — §1.1 |

- **A alíquota é NULL de propósito, não por falta de dado.** No Simples o ICMS está dentro do DAS
  e **não se destaca na nota** — **LC 123/2006, art. 18**. Destacar seria erro.
- **CSOSN 102** = tributada **sem** permissão de crédito. O **101** (com crédito, **LC 123/2006,
  art. 23, §1º**) só vale se a empresa **optar** por transferir crédito — hoje não optou, e isso é
  **sem fonte — decisão do contador**.
- **PIS, COFINS e IPI: NULL, sem destaque** — tudo dentro do DAS (LC 123/2006, art. 18); CST 49/99.
- Mensagem fiscal obrigatória na nota: *«Documento emitido por ME/EPP optante pelo Simples
  Nacional — não gera direito a crédito de ICMS/IPI (LC 123/2006, art. 23).»*

#### 🚨 BLOQUEIO — esta empresa não pode emitir NF-e de mercadoria hoje

> **CONECTAMAIS PATRIMONIAL não tem Inscrição Estadual cadastrada.** Sem IE não se emite NF-e
> modelo 55 de mercadoria — o documento dela hoje é a NFS-e. **Ou cadastrar a IE, ou confirmar com
> o contador que a empresa não é contribuinte do ICMS.**

O serviço devolve esse bloqueio em **todas** as combinações dela, e o oráculo amarra a regra à
coluna do banco: se a IE for preenchida, o bloqueio some sozinho; se a Eletrônica perder a IE
dela, o bloqueio aparece lá. Nenhuma das duas metades é constante no código. É coerente com o
cadastro: Anexo III, CNAE 8111-7/00 (serviços de apoio a edifícios) — ela vende serviço, não
mercadoria.

---

### 1.4 Venda PARA a ZFM — a regra completa, para quando houver emitente fora do AM

Ramo implementado e testado; **hoje inalcançável** para os dois CNPJs (§1.1). Contraprova rodada
com um emitente fictício em São Paulo:

| Campo | Valor | Norma |
|---|---|---|
| CFOP | **6110** (revenda) / **6109** (produção) | Convênio SINIEF s/nº de 15/12/1970, Anexo |
| CST de ICMS | **40** (isenta) | Convênio ICM 65/88, cláusula primeira; **DL 288/1967, art. 4º** |
| Base | R$ 1.000,00 | — |
| Alíquota destacada | **NULL** (isenção — não há o que destacar) | idem |
| **vICMSDeson** | **R$ 120,00** | MOC NF-e 4.00, grupo N, campo **N27a** |
| **motDesICMS** | **7 (SUFRAMA)** | MOC NF-e 4.00, grupo N, campo **N28** |
| PIS / COFINS | **0,00** (CST 06, alíquota zero) | **Lei 10.996/2004, art. 2º** |
| IPI | isento (CST 52) | **Decreto 7.212/2010 (RIPI), art. 84** |

O `vICMSDeson` é quantificado pela **alíquota interestadual de saída** (12%), porque o Convênio
ICM 65/88, cláusula primeira, §1º manda **abater do preço** o ICMS que seria devido — e é esse
valor que a nota tem de provar.

**Texto que vai em `infAdProd` / `infCpl`** (gerado pelo serviço, com o SUFRAMA do destinatário
interpolado):

> Mercadoria destinada à Zona Franca de Manaus — isenta de ICMS nos termos do Convênio ICM 65/88
> e do Decreto-Lei 288/1967, art. 4º. Valor do ICMS desonerado R$ 120,00, abatido do preço
> (Convênio ICM 65/88, cláusula primeira, §1º). Inscrição SUFRAMA do destinatário: 210140500.
> IPI isento — Decreto 7.212/2010 (RIPI), art. 84. PIS/COFINS com alíquota zero — Lei
> 10.996/2004, art. 2º.

---

### 1.5 Tudo que ficou explicitamente «SEM FONTE — DECISÃO DO CONTADOR»

Nada disto foi preenchido por suposição. Cada item é um NULL declarado:

| # | O que | Por que não tem fonte | Risco se alguém chutar |
|---|---|---|---|
| 1 | Artigo do **RICMS-AM** da alíquota interna de 20% | o repositório não tem o RICMS | o número está medido em 76 notas; falta o carimbo legal |
| 2 | **Substituição tributária** (CEST, MVA, quais NCMs) | `ncms.icms_cest` e `icms_st_mva` vazios nas 10.515 linhas | **o maior risco do mapa — 51% do que a praça pratica é ST (§4)** |
| 3 | **DIFAL** para não contribuinte fora do AM | não há tabela de alíquota interna das 26 UFs | recolher a menos para o estado de destino |
| 4 | **Equiparação a industrial** (IPI da Eletrônica) | não há classificação de industrialização no cadastro | destacar IPI de quem não é contribuinte, ou omitir de quem é |
| 5 | **CSOSN 101 vs 102** (transferir crédito?) | depende de opção da empresa, não registrada | negar crédito legítimo ao cliente, ou dar crédito indevido |
| 6 | **Redução de base** (Conv. 52/91, Lei AM 2.826/2003, Lei AM 3.830/2012) | não modelada; nenhum cadastro de benefício | 3 itens de fornecedor usam (§4) |
| 7 | **`ncms`: todas as alíquotas** (IPI, PIS, COFINS, II) | 10.515 linhas com descrição e **zero** alíquota no banco | base fiscal do produto inexistente |

---

## §2 — O que o DGX tem e o que a casa tinha

`docs/dgx/lacunas/faturamento_financeiro.md` marca «CFOP / natureza → **TEMOS**». Medido: a tabela
`cfops` tem **2 linhas** — 5933 e 6933, as duas de **serviço** (ISSQN). **Zero CFOP de
mercadoria.** O DGX também aponta «tipos de serviço com NBS/CST/classificação tributária» como
lacuna de 2027 (IBS/CBS) — fora desta frente.

Estado medido no nascimento (sandbox, 24/09/2026):

| Fonte | Linhas | O que tem |
|---|---|---|
| `tax_configurations` | **0** | modelo completo (CST, CSOSN, origem, modBC, MVA, `special_rules` JSONB) — sem nenhuma configuração |
| `suframa_configs` / `suframa_operacoes` | **0** / **0** | modelo com benefícios e cálculo de economia — vazio |
| `cfops` | **2** | só 5933/6933 (serviço) |
| `ncms` | **10.515** | descrição da TIPI; **ipi/pis/cofins/cest/mva todos NULL** |
| `nfe_entradas` | **84** (51 com XML) | **207 itens reais** com CST/CSOSN/CFOP de fornecedores — a referência de mercado |
| `nfe_compras_estoque` | 147 | **não tem** CST/CSOSN/CFOP/alíquota — só `ncm` |
| `nfse_emitidas_nacional` | 114 | serviço (ISS), não mercadoria |

**Correção ao brief:** «`nfe_compras_estoque`, 147 itens com CST/CSOSN reais dos fornecedores» não
se confirma — essa tabela guarda NCM e custo, sem tributo nenhum. O parser do sync
(`nfe_entrada_sync_service.processar_xml_nfe`) lê `det/prod` e **descarta `det/imposto` inteiro**.
O dado existe, mas só dentro de `nfe_entradas.xml_raw` — e é de lá que o §4 lê.

**Regra de mercadoria: não existia nenhuma.** Os dois caminhos de NF-e gravavam tributo fixo:
`financial/integrations/nfe_provider.py` põe CFOP 5933 + CST 40 + ICMS zero (é a nota de serviço),
e `fiscal_contabil/.../nfe/controller.py` põe CST 40 + `vICMSDeson "0.00"`.

---

## §3 — O que foi feito

### Arquivos

| Arquivo | O quê |
|---|---|
| `backend/modules/fiscal/services/tributacao_nfe.py` (**novo**, 420 linhas) | a regra. `calcular(db, empresa_cnpj, produto, destinatario, operacao)` → `{cfop, cst_ou_csosn, base, aliquota, valor, deson, mensagem_fiscal, origem_regra, …}`. Determinístico, único I/O é ler `empresas`. `demo()` de autoteste sem banco. |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_z4_tributacao.py` (**novo**, 400 linhas) | as 3 telas + a ação. Sem régua própria. |
| `backend/modules/operacional/controllers/redesign_builders/fiscal.py` (**+22 linhas**) | plug: 3 itens no `EXTRA_MENU`, `await _z4.telas(db, out)` no fim do `build()`, e o `router` do módulo fiscal — que **não existia** até agora. |
| `backend/scripts/orq/test_oraculo_z4_tributacao_nfe.py` (**novo**) | o oráculo. |

### Reuso (cavado antes de construir)

- `modules.empresas.services.empresa_lookup.get_empresa(db, cnpj=…)` — identidade da empresa.
- `modules.financial.models.tax_configuration.{ICMSCST, ICMSCSOSN, ICMSOrigin}` — os enums já
  existiam e são a tabela oficial. Não recriei.
- `nfe_entradas.xml_raw` — 51 XMLs reais, relidos sem ir à SEFAZ.

> **Achado de reuso:** no enum `ICMSCSOSN` do repositório, o membro `TRIBUTADA_COM_CREDITO` vale
> `"102"` — que na Tabela B do Ajuste SINIEF 07/2005 é «tributada **SEM** permissão de crédito»
> (o com crédito é o 101). **O rótulo está trocado; o valor está certo.** Usei o valor e deixei o
> comentário. Não renomeei: o enum é usado em `nfe.py` e `nfe_itens`, e renomear sem medir os
> chamadores é o tipo de "limpeza" que quebra o que estava funcionando.

### DDL

**Nenhuma.** Esta frente não cria tabela, não altera coluna, não semeia, não tem `_ensure`. É
read-only. Nada para o orquestrador aplicar em produção no 1º acesso.

### Telas (deep-link `/redesign/fiscal?t=<id>`, grupo «Notas fiscais»)

| id | Tela | O que mostra | Medido |
|---|---|---|---|
| `nfe-tributacao-mapa` | **Mapa da tributação (NF-e)** | o §1 em tela: cada empresa × cada destino × revenda/produção, com CFOP, CST/CSOSN, base, alíquota, ICMS, desonerado e **a norma na coluna ao lado** | **20 linhas**, 10 bloqueadas |
| `nfe-tributacao-simulador` | **Simulador de tributação da NF-e** | o formulário do contador: empresa, operação, NCM, valor, quantidade, origem, UF, contribuinte s/n, SUFRAMA | **9 campos** |
| `nfe-tributacao-divergencias` | **Nossa regra × a praça de Manaus** | §4 — a nossa régua contra os XMLs reais dos fornecedores | **100 linhas** |

Ação: `POST /api/v1/redesign/action/nfe-tributacao-simular` (gate `module:fiscal`). Read-only —
não grava, não emite, não fala com a SEFAZ.

---

## §4 — CONFERÊNCIA CONTRA O QUE JÁ EXISTE

### 4.1 NF-e de entrada — 207 itens reais de fornecedores de Manaus

Lidos dos XMLs de 50 NF-e (`nfe_entradas.xml_raw`), 200 deles de operação interna do AM.
**52 das 100 linhas agregadas por NCM divergem da nossa regra.** Nenhuma delas é a nossa regra
estar *errada* — todas apontam para algo que a casa **não modela**:

| Divergência | Linhas | Leitura |
|---|---|---|
| **igual à nossa regra** | **44** | CFOP 5102 + CST 00 + 20,00% — bate exatamente, inclusive os 13 itens de fornecedor do Simples com CSOSN 102 |
| **ICMS já retido por ST** (CST 60 / CSOSN 500) | **49** | **a casa não tem CEST nem MVA para decidir** |
| CFOP de outra natureza (5912 — remessa/ordem) | 4 | fora do escopo de venda |
| **redução de base** (Conv. 52/91, Lei AM 2.826/2003, Lei AM 3.830/2012) | 3 | não modelada |
| nossa regra daria outro CFOP/CST | **0** | — |

**O número que importa: 106 dos 207 itens (51%) vieram com ICMS já retido por ST.** Metade do que
se compra em Manaus é mercadoria com substituição tributária — e a casa não tem uma única linha de
CEST ou MVA para saber se o que ela vende também é. Sair com CST 00 numa mercadoria sujeita a ST é
o erro que a SEFAZ autoriza e o fisco autua. **É a decisão nº 1 para o contador.**

Alíquotas medidas, que dão confiança nas duas do mapa: **20,00%** em 76 itens AM→AM (CST 00 e CST
20); **7,00%** no único RS→AM; **1,65% / 7,60%** exatos em 39 itens de PIS/COFINS de CRT=3.

Normas que os próprios fornecedores citam no `infCpl` — fonte primária dentro do repositório:

- «OS PRODUTOS DESTA NF SAO ISENTOS DE IPI CONF. **ART 81 INCISO II DECRETO 7.212/2010**.
  PRODUZIDO NA ZONA FRANCA DE MANAUS. ICMS CALCULADO CONF. **LEI 2.826/2003**»
- «ISENTO IPI CONFORME **DECRETO 7.212/2010 ART. 84**»
- «BC REDUZIDA CONF **CONV 52/91** LEI ESTADUAL **3830/2012** ART. 3 LEI ESTADUAL **2826/2003** ART. 19 INC. VI»
- «PROD JA TRIBUTADO **PROT 17,18/85, 41/08 CONV 74/94 E 03/99**» (ST)

### 4.2 NFS-e emitidas — o outro lado, para contraste

As 114 NFS-e nacionais emitidas são de **serviço (ISS)**, não de mercadoria — régua diferente,
já implementada em `fiscal/services/nfse_multi_empresa_service.py`, que **não toquei**. Medido:

| Empresa | Código | Notas | ISS médio | Valor |
|---|---|---|---|---|
| Eletrônica (lucro real) | 110201 | 34 | **5,00%** | R$ 1.320.588,53 |
| Eletrônica | 140601 | 32 | **5,00%** | R$ 138.520,00 |
| **Patrimonial (Simples)** | 110201 | 16 | **1,18%** | R$ 600.767,24 |
| Patrimonial | 071002 | 7 | **0,00%** | R$ 63.637,10 |

Coerente com o §1: a do lucro real recolhe ISS cheio; a do Simples mostra a parcela de ISS dentro
do DAS. **Confirma que a Patrimonial opera como prestadora de serviço** — o que reforça o bloqueio
de NF-e de mercadoria por falta de IE (§1.3).

---

## §5 — Oráculo

`backend/scripts/orq/test_oraculo_z4_tributacao_nfe.py`

```bash
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_z4_tributacao_nfe.py
```

**VERMELHO (antes da tela):**
```
combinações empresa × destino × operação conferidas: 20
empresas ativas lidas do banco: 2
FALHOU: tela do simulador não existe: cannot import name '_dgx_z4_tributacao' from
        'modules.operacional.controllers.redesign_builders'
1 desvio(s) na tributação da NF-e
EXIT=1
```

**VERDE (depois):**
```
combinações empresa × destino × operação conferidas: 20
empresas ativas lidas do banco: 2
OK tributação NF-e: toda combinação com CFOP e CST/CSOSN ou «sem fonte» declarado; nenhuma
alíquota sem origem; Simples com CSOSN e lucro real com CST; ZFM com desoneração e mensagem
fiscal; simulador e serviço com o mesmo número.
EXIT=0
```

Autoteste do serviço, sem banco (`python3 backend/modules/fiscal/services/tributacao_nfe.py`):
`demo tributacao_nfe: OK — 10 blocos, 30 combinações empresa × destino × operação`.

O oráculo **reconta a régua**, não a importa: a tabela de CST/CSOSN está escrita de novo dentro
dele; o regime, a IE e o município vêm de SQL próprio sobre `empresas`; e o item (5) chama a tela
e o serviço separadamente e compara campo a campo (`cfop`, `cst_ou_csosn`, `base`, `aliquota`,
`valor`, `origem_regra`, contagem de linhas, mensagem fiscal). **Se alguém arredondar na tela,
fica vermelho.** Fixtures: nenhuma criada; o item (7) varre 'FIXTURE DGX Z4' e não achou nada.

### Prova HTTP (porta 8284, container `teste-dgx-z4` — **parado**)

- `GET /api/v1/redesign/data/fiscal` → **200**, 642 KB; as 3 telas presentes com `extraMenu`
  `['nfe-tributacao-mapa', 'nfe-tributacao-simulador', 'nfe-tributacao-divergencias']`.
- `POST /api/v1/redesign/action/nfe-tributacao-simular` (Eletrônica, SP, contribuinte, 2 × R$ 1.500)
  → `cfop 6102 · CST 00 · base R$ 3.000,00 · 12,00% · ICMS R$ 360,00`, com as 11 linhas normadas.
- Mesmo POST para a Patrimonial → `CSOSN 102 · alíquota —` + o bloqueio da Inscrição Estadual.

**Bug pego pelo teste HTTP, não pelo oráculo:** `fiscal.py` não tinha `router`, e com o meu
`router = APIRouter()` declarado no fim do arquivo o discovery quebrava em ciclo de import
(«partially initialized module … has no attribute 'router'») e **o módulo fiscal inteiro caía para
o fallback do monólito** — sem nenhuma das telas, e sem erro visível na tela. O oráculo estava
verde porque importa o builder direto. Corrigido: `router` declarado **antes** do import do
`redesign_data_controller`, como os outros `_dgx_*` já faziam, com o comentário explicando.

---

## §6 — Como o Jordan testa amanhã

1. **Fiscal → Notas fiscais → Mapa da tributação (NF-e).** 20 linhas. Correr o olho na coluna
   **Norma**: toda alíquota tem uma. Filtrar por «Regime» = Simples: alíquota sempre `—` e
   situação **bloqueada** — é a falta da Inscrição Estadual, e é correto.
2. **Notas fiscais → Simulador de tributação da NF-e.** Escolher *Conecta Mais Eletrônica*,
   revenda, NCM `85311000`, valor `1000`, quantidade `1`, origem `0 — Nacional`, UF `AM`,
   contribuinte `Sim`, SUFRAMA vazio → **Calcular**. Esperado: **CFOP 5102 · CST 00 · 20,00% ·
   R$ 200,00**.
3. **O teste que importa:** repetir o passo 2 **preenchendo SUFRAMA = 210140500**. O resultado tem
   de ser **idêntico** — CFOP 5102, 20%, sem desoneração. Se aparecer 6110/isento, a frente falhou:
   a casa está **dentro** da ZFM (§1.1).
4. Trocar UF para `SP`, contribuinte `Não` → **CFOP 6108 · 12,00%**, e na mensagem fiscal o aviso
   de que o **DIFAL ficou NULL por falta de fonte**. É NULL de propósito.
5. **Notas fiscais → Nossa regra × a praça de Manaus.** Filtrar «Divergência» = *ICMS já retido por
   ST*. São **49 linhas**. É o §7, item 1.
6. Imprimir/enviar o **§1 deste relatório** ao contador antes da primeira nota.

---

## §7 — Decisões que só o dono (e o contador) podem tomar

| # | Decisão | Por quê agora | Custo de errar |
|---|---|---|---|
| **1** | **Substituição tributária: quais dos nossos produtos são ST?** Carregar CEST e MVA em `ncms` (10.515 linhas hoje sem nada). | **51% do que a praça de Manaus pratica é ST** | vender ST com CST 00 = ICMS a menos, autuação com multa |
| **2** | **Carimbar o artigo do RICMS-AM** da alíquota interna de 20% | é o único número do mapa sem dispositivo legal | se não for 20%, **todas** as notas internas saem erradas |
| **3** | **Inscrição Estadual da Patrimonial**: cadastrar, ou declarar que ela não é contribuinte do ICMS | ela **não pode** emitir NF-e 55 hoje | emitir sem IE = nota rejeitada ou inválida |
| **4** | **A Eletrônica é equiparada a industrial** (IPI)? Instala e monta CFTV/alarme. | muda o IPI de toda nota dela | destacar IPI de quem não é contribuinte, ou omitir de quem é |
| **5** | **CSOSN 101 ou 102** para a Patrimonial (transferir crédito ao cliente?) | é opção da empresa, não regra | negar crédito legítimo, ou dar crédito indevido |
| **6** | **Tabela de alíquota interna das UFs** para o DIFAL, se for vender fora do AM a não contribuinte | hoje o DIFAL sai NULL | recolher a menos ao estado de destino |
| **7** | 🚨 **Corrigir o emissor (frente Z2):** `is_zfm=True` é o **default** e `vICMSDeson` é fixo `"0.00"` — toda nota sai com menção de ZFM e CST 40, mesmo na venda interna em Manaus | **é o caminho que vai de fato à SEFAZ** | isenção inexistente + ICMS não destacado em **toda** nota |
| **8** | O emissor usa `EMITENTE_IE="45177801"` — esse número é a **Inscrição Municipal** da Eletrônica no cadastro. A IE dela é **05.426.574-6**. | idem (território Z2) | IE errada no XML |

---

## §8 — O que NÃO foi feito, e por quê

1. **Não emiti, não transmiti e não assinei nada.** Zero contato com a SEFAZ — condição do brief.
2. **Não toquei no emissor (Z2), na tela de emitir (Z3) nem em `fin_produtos` (Z1).** Os itens 7 e
   8 do §7 são bugs reais que eu vi e **deixei registrados em vez de consertar**, porque são de
   outra frente e corrigir fora do dono é como se criam conflitos de merge nesta casa.
3. **Não preenchi `tax_configurations`, `cfops` nem `suframa_configs`.** O modelo está pronto e
   vazio, e seria fácil semear — mas **semear é declarar uma regra**, e a regra aqui é do contador.
   Preferi que o serviço leia de constantes **com norma citada** e que as decisões pendentes fiquem
   visíveis no §7, em vez de sumirem dentro de linhas de banco sem dono.
4. **Não carreguei CEST/MVA em `ncms`.** É o §7-1 e depende de decisão fiscal por produto.
5. **Não modelei redução de base, diferimento nem crédito estímulo da Lei AM 2.826/2003.** São 3
   itens dos 207 medidos, e cada um depende de habilitação específica da empresa na SEFAZ-AM.
6. **Não mexi no parser de entrada** para passar a gravar CST/CSOSN por item. Seria a correção
   certa (`nfe_entrada_sync_service.processar_xml_nfe` descarta `det/imposto`), mas mexe na tabela
   de outra frente (F9 é dona de `nfe_compras_estoque`) e no sync da SEFAZ. A tela de divergências
   relê o `xml_raw`, que já está salvo — resolve o problema de hoje sem tocar no sync.
7. **Não renomeei `ICMSCSOSN.TRIBUTADA_COM_CREDITO`** apesar do rótulo estar trocado (§3).
8. **Não escrevi nenhuma linha em banco**, em nenhuma tabela, nem fixture. Produção não foi tocada.
