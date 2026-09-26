---
name: tributario-simples-anexo-iv
agent: TaxCalculatorAgent
prioridade: CRITICA
versao: 1.0
---

# Skill 17 — Simples Nacional Anexo IV — Conecta Mais Patrimonial
## CNPJ 66.014.833/0001-10 | Manaus/AM | Simples Nacional | aberta em 31/03/2026

> Esta skill existe porque a skill 16 é de **outro regime e de outro CNPJ**, e aplicar uma
> na outra é o erro mais caro que se pode cometer aqui. Ler a 16 pensando na Patrimonial
> leva a procurar crédito de PIS/COFINS que não existe e a ignorar a CPP patronal que
> existe.

---

## 1. A regra que define tudo: Anexo IV, e o que isso muda

Vigilância, limpeza e conservação são **Anexo IV** (LC 123, art. 18 §5º-C). A consequência
não é a alíquota — é **quem paga a contribuição previdenciária patronal**:

| | Anexo III (substituída) | **Anexo IV (esta empresa)** |
|---|---|---|
| CPP patronal | **DENTRO do DAS** (~43% da guia) | **FORA do DAS** — devida à parte, art. 22 da Lei 8.212 |
| retenção de 11% do tomador | não se aplica | **aplica** (Lei 9.711/98, cessão de mão de obra) |
| ISS | dentro do DAS | dentro do DAS |

**Como provar em qual dos dois a empresa está, sem depender de cadastro:** abrir a guia do
DAS e ler a linha `1006 INSS - SIMPLES NACIONAL`. Medido em 26/09/2026:

```
DAS 07/2026  R$ 17.048,87  →  1006 INSS  R$ 171,06   (1,0% da guia)
DAS 08/2026  R$ 18.399,33  →  1006 INSS  (nenhuma linha)
```

No Anexo III essa linha seria ~R$ 7.400. **É Anexo IV.** A composição por tributo é
extraída pelo `DASExtractor` na importação e fica em
`onvio_documents.detalhes_json->composicao` — leia de lá, não do PDF.

**Vigia:** `backend/scripts/qa/checar_patronal_nao_declarada.py`.

---

## 2. As duas coisas que estão ERRADAS hoje (26/09/2026)

**a) A CPP patronal não está em documento nenhum.** A DCTFWeb de 07 e 08/2026 declara só
`1082-01 CP SEGURADOS` e se diz *"Classificação Tributária 1 — Simples com tributação
previdenciária SUBSTITUÍDA"*, que é justamente o que a guia do DAS desmente. Deveria ser
**classificação 03 — não substituída**, com o débito patronal declarado.

| competência | folha | patronal (20% + RAT 3%) | retenção 11% dos clientes | descoberto |
|---|---|---|---|---|
| 06/2026 | 111.388,40 | 25.619,33 | 27.512,95 | −1.893,62 |
| 07/2026 | 102.322,90 | 23.534,27 | 22.689,44 | +844,83 |
| 08/2026 | 106.577,20 | 24.512,76 | 26.845,79 | −2.333,03 |

A retenção cobre a patronal quase ao real. **O caixa não deve — falta a declaração.**

**b) O crédito da retenção está dormindo.** DCTFWeb 08/2026: R$ 19.544,08 informados de
"Retenção Lei 9711/98", R$ 7.011,23 usados, **R$ 12.532,85 de saldo disponível**. Todo mês.
Ele existe exatamente para abater o débito patronal que não está sendo declarado.

---

## 3. Tributos: o que é e o que NÃO é

**DAS — recolhimento único mensal**, vence no dia 20 do mês seguinte. Contém IRPJ, CSLL,
COFINS, PIS e **ISS**. A alíquota efetiva sobe com o RBT12 (medido: 6,675% em 07/2026,
7,018% em 08/2026, faixa 2 do Anexo IV, RBT12 ≈ R$ 348 mil).

**ISS: NÃO se lança à parte.** Ele é componente do DAS. A alíquota que aparece na NFS-e
(2,01% → 4,36% em quatro meses) é a alíquota **efetiva de ISS do Simples** subindo com o
RBT12, não um ISS municipal próprio. Lançar os dois conta o mesmo imposto duas vezes — foi
o que aconteceu até 26/09/2026 (R$ 9.792,84 num passivo `2.1.2.01` com 5 créditos e ZERO
débitos, porque não havia o que pagar).

**Fora do DAS, devidos à parte:** CPP patronal (§1), FGTS 8%, INSS retido do empregado
(`1082-01`, via eSocial/DCTFWeb).

---

## 4. O filtro contra literatura de Lucro Real

A maior parte do material de "economia fiscal" do mercado pressupõe Lucro Real ou Presumido.
No Simples o imposto incide sobre a **receita bruta**, então quase nada disso alcança.
Aplicado ao "Multiplicador de Economia Fiscal" (26/09/2026), 12 estratégias:

| não se aplica | por quê |
|---|---|
| crédito de PIS/COFINS sobre insumos | Simples não gera crédito — a apuração é sobre receita |
| exclusão do ICMS da base | idem |
| Lei do Bem / P&D | exige **Lucro Real com lucro tributável** |
| prejuízo fiscal acumulado | Simples não apura lucro real; não há prejuízo a compensar |
| otimização da base de ISS | o ISS está dentro do DAS |
| incentivo municipal de ISS | idem |
| regimes aduaneiros / importação | não há importação |
| holding patrimonial / sucessório | imobilizado do grupo: **R$ 1.725,00** |
| planejamento internacional | não há operação fora do Brasil |

| se aplica | como |
|---|---|
| **créditos dormentes** | não é PIS/COFINS: é a **retenção Lei 9.711**, R$ 12.532,85/mês parados |
| **otimização da folha** | no Anexo IV a patronal É devida — cada real fora da base vale 23%. PPR (Lei 10.101/2000) é isento de encargos, **mas exige acordo negociado com o sindicato**: a categoria é regida por CCT |

---

## 5. Dois riscos que a literatura induz — e que aqui já existem

**Distribuição de lucros sem pró-labore.** Medido em 26/09/2026: **zero holerites de sócio,
diretor ou administrador** nas duas empresas, e a Eletrônica com R$ 27.400 debitados na
conta de sócios carregando prejuízo acumulado de R$ 116.222,72. Distribuir lucro que não
existe é retirada requalificável como pró-labore disfarçado, com INSS e multa. O caminho de
"converter pró-labore em lucros" pressupõe que exista pró-labore para converter.

**Segregação de atividades em novos CNPJs.** No Simples isso tem nome — **fracionamento** —
e a LC 123 art. 29, IV permite exclusão com efeito retroativo. O grupo **já tem** dois CNPJs
com o mesmo sócio, mesmo endereço, mesma família de atividade e contratos que migraram de um
para o outro em junho/2026. Isso não é plano futuro: é exposição existente, que precisa de
propósito negocial documentado. Criar um terceiro CNPJ para "otimizar faixa" anda na direção
do problema, não para longe dele.

---

## 6. Onde isto vive no código

| fato | arquivo |
|---|---|
| composição do DAS por tributo | `backend/modules/gedeon/onvio/pdf_extractor/das_extractor.py` |
| lançamento do DAS por empresa e regime | `backend/modules/financial/services/ledger_auto_service.py` (`lancar_das_parcelamento`) |
| ISS não lançado à parte no Simples | idem (`_lancar_receita_e_iss_nacional`, `iss_no_das`) |
| retenção Lei 9.711 escriturada | idem (conta `1.1.3.02`) |
| corte contábil próprio (01/06/2026) | `empresas.corte_contabil` + `fn_bloqueia_periodo_fechado` |
| vigia da patronal | `backend/scripts/qa/checar_patronal_nao_declarada.py` |

Relatório completo: `auditoria/frentes/PATRIMONIAL_2026-09-26_ARRUMAR_PARA_O_CREDITO.md`.
