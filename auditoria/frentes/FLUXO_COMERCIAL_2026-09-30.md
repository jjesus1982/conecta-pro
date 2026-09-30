# Fluxo comercial — os dois prompts, 30/09/2026

Estado do que foi pedido, do que foi feito, e do que ficou aberto. Os números todos foram
medidos em produção; nenhum é estimativa.

---

## Prompt 1 — os dez bugs

| # | Bug | Estado | A causa real |
|---|-----|--------|--------------|
| [0] | expurgo apagaria documento de cliente | feito (2f9359559) | prévia mostrava só contagem; 173 reais na mira |
| [1] | BUG-03 flag `teste` fixa | feito | `_gerar_doc(teste=True)` em `mcp-server/server.py:1779` |
| [2] | BUG-01 listagem 500 no 2º registro | feito (2f9359559) | `discount_type='percent'` fora do enum |
| [3] | BUG-02 `criar_proposta` 500 | feito | `proposal_items.empresa_id` NOT NULL e ninguém resolvia |
| [4] | BUG-05 emitente fixo no PDF | feito | `build_orcamento_pdf` nunca passava `empresa` |
| [5] | BUG-04 documento sem dono | feito | `ref_tipo`/`ref_id` existiam e ninguém preenchia |
| [6] | BUG-08 sem tool de oportunidade | feito | rota exige `contact_email` NOT NULL |
| [7] | BUG-06 `busca` rejeitada | feito | aceita e IGNORADA nas rotas REST |
| [8] | BUG-09 500 sem diagnóstico | feito | `request_id` aceito e ignorado no WHERE |
| [9] | BUG-07 fixtures em produção | feito | oráculo AA2 limpava só no INÍCIO |

### Onde o diagnóstico do prompt estava errado

**BUG-02.** O prompt supunha que a proposta era GRAVADA e o erro ocorria na resposta, e
pedia para procurar propostas órfãs. Não há nenhuma: a `NotNullViolationError` aborta a
transação inteira antes do commit, e o `repo.create` já tinha rollback. A atomicidade
estava certa; o que faltava era o diagnóstico sair.

**BUG-03.** O prompt dizia que os 8 documentos estavam com `teste=true` e pedia um script
de correção. Já estavam `false` — a correção de dado foi feita no commit anterior. O que
faltava era a origem, e ela estava no repositório apesar de eu ter escrito o contrário.

### Os 8 critérios de aceite, medidos

```
1. listar_propostas(50)              HTTP 200 · 12 propostas · 0 fixtures na lista
2. criar_proposta cliente novo       HTTP 201 · PROP-2026-00126
3. aparece em /redesign/crm          1ª linha da tela, com a coluna «Vira»
4. ficha do cliente                  Villa Toscana: 2 documentos
5. orçamento pela Patrimonial        cabeçalho e rodapé CNPJ 66.014.833/0001-10
6. documento nasce teste=false       f · ref_tipo=client · vinculado
7. listar_leads(busca=...)           46 sem filtro · 3 «Condominio» · 0 «zzz-nada»
8. os 8 documentos + PROP-00114      98 documentos · 98 teste=false · 98 vinculados
```

---

## Prompt 2 — taxonomia e split fiscal

### [0] As 7 notas de teste NÃO estão em produção

O prompt afirma que estão «autorizadas na SEMEF, com ISS apurado». Não estão.
`sefin.producaorestrita.nfse.gov.br` é o ambiente de ENSAIO do Padrão Nacional — a frase
«PRODUCAO RESTRITA» na discriminação é o NOME desse ambiente, não uma confissão.

O que **não** serviu de prova, e vale registrar:

- `ambiente='homologacao'` na linha é pista, não prova: 14 linhas têm esse rótulo e seis
  delas parecem notas reais;
- o `tpAmb` da chave de acesso **não serve** e quase me enganou: a posição 8 da chave de
  50 dígitos é o *Ambiente Gerador* (1=Prefeitura, 2=Sefin Nacional), não o ambiente de
  teste. Todas as 160 notas têm `2` ali, inclusive as reais de R$ 25.592,71.

O que provou: o código da conciliação já documenta o incidente por escrito — ela consulta
o endpoint do ambiente configurado na empresa e carimba a linha com o ambiente de onde a
resposta veio. Em 24/09 as empresas estavam em `homologacao`.

**Nada a cancelar. Nada a levar ao contador.** IDs, para registro: Eletrônica nº 11, 12,
13, 14, 15; Patrimonial nº 8, 9 — todas 24/09/2026, produção restrita.

### O que foi construído

| Item | Entrega |
|------|---------|
| [1] tipo de negócio | A/B/C/D derivado da NATUREZA dos itens, nunca do valor |
| [2] classe fiscal | `material`/`servico_tecnico`/`mao_de_obra` decide o CNPJ |
| [3] notas da proposta | `preview()` agrupa por classe — uma nota por grupo |
| [4] códigos de serviço | `fin_codigos_servico` já existia; o elo classe→código é novo |
| [5] retenção de INSS | confere ao centavo com a NFS-e nº 35 real |
| [6] dados bancários | por emitente, montados — nunca colados |
| [7] registro de execução | 3 campos na proposta, substituem a OS |
| [8] máquina de estados | a trava está de pé; o estado `faturada` fica pendente |

### Cenário 4, medido

```
NF-e  ELETRÔNICA  35710481000103  R$ 4.800,00  ICMS
NFS-e ELETRÔNICA  35710481000103  R$ 1.800,00  cód 140601  ISS 5%
NFS-e PATRIMONIAL 66014833000110  R$ 8.900,00  cód 110201  ISS 0% + INSS R$ 979,00
```

### Sobre o item [8]

A trava que o prompt pede — «nada vai de aceita para faturada sem emitente definido para
cada classe fiscal» — está de pé: é exatamente o que o `preview` recusa. O **estado**
`faturada` não foi criado porque nada o definiria ainda: a emissão continua pelo caminho
do `nfse_nacional` e não está ligada à proposta. Estado que ninguém escreve é mentira na
tela.

---

## ABERTO — decisão do Jordan

### R$ 65.695,59 possivelmente fora do faturamento

Seis NFS-e da Eletrônica estão marcadas `ambiente='homologacao'` com descrição e valor de
nota REAL, e os mesmos seis números **faltam** na sequência de produção:

| nº | data | valor | objeto |
|----|------|-------|--------|
| 6 | 23/01 | R$ 35.737,39 | portaria |
| 7 | 28/01 | R$ 13.561,50 | limpeza e jardinagem |
| 13 | 30/01 | R$ 8.346,70 | serviços gerais |
| 29 | 27/02 | R$ 500,00 | manutenção CFTV |
| 30 | 27/02 | R$ 1.700,00 | manutenção CFTV |
| 31 | 27/02 | R$ 5.850,00 | prestação de serviços |

Os buracos da produção da Eletrônica são 4, 5, 6, 7, 13, 29, 30, 31, 60–62, 74, 75, 81,
83, 94, 96, 108, 110, 118, 122. Seis deles casam exatamente com essas linhas.

**É pista forte, não prova.** Quem resolve é o fisco: rodar a conciliação contra a
produção para esses números de DPS. Faturamento não se corrige por dedução.

### NFS-e nº 3 da Patrimonial — R$ 42.544,50 apontando para a conta errada

Laranjeiras Village, 25/06/2026, autorizada e viva, mandando pagar no Inter com o CNPJ da
Eletrônica. As notas 1 e 2, mesmo valor e mesmo dia, já foram canceladas. A 22 (Prime
Arena, R$ 3.879,60) também. Cancelar e reemitir a 3 é decisão do contador.

Está declarada no `checar_conta_na_nota` com o motivo, para a trava vigiar o crescimento
sem ficar vermelha para sempre.

### 47 notas de «Vigilância» emitidas pela ELETRÔNICA

Mão de obra no CNPJ e no regime errados, entre janeiro e setembro. São o erro que o
módulo de classe fiscal passa a impedir. Não foram tocadas.

---

## Travas novas, todas provadas contra o código anterior

| Trava | Prova |
|-------|-------|
| `checar_flag_teste_padrao` | com `teste=True` acusa `_gerar_doc`; com `False`, 0 |
| `checar_fixture_viva` | desmarcando PROP-2026-00118 acusa; marcada, 0 |
| `checar_conta_na_nota` | 4 achados, 3 canceladas, 1 declarada |

## Oráculos novos

| Oráculo | Afirmações |
|---------|-----------|
| `test_oraculo_crm_classe_fiscal` | 20 |
| `test_oraculo_crm_docs_vinculo` | lê a tabela; não conhece a lista de tipos |
| `test_oraculo_request_id_correlacionado` | 5, de fora, contra produção |
| `test_oraculo_notas_da_proposta` | 14, monta e desmonta |
