# Prontidão para desligar a Portte — MEDIDO (2026-07-31)

> Este relatório **mede**, não estima. Cada número tem origem em código lido ou query rodada.
> Motivo: a lição desta frente foi justamente diagnosticar de memória e errar.

## Veredito de uma linha

**Reconciliar com a Portte: ~95% pronto. Substituir a Portte: ~35% pronto.**
São coisas diferentes, e a diferença é o que ainda falta construir.

---

## 1. O que está REALMENTE pronto (medido hoje)

| Pilar | Métrica medida | Estado |
|---|---|---|
| **Folha — cálculo** | Σ\|Δ\| líquido **6.395** sobre R$416.810 = **98,5% de paridade** | ✅ forte |
| **Folha — persistência** | 312 linhas `source='conecta'` em paralelo, Portte intacta | ✅ feito hoje |
| **Razão contábil** | Folha **Δ=0** · INSS **Δ=0** · FGTS ~5% · Receita/ISS batem jan-mai | ✅ forte |
| **ECD/SPED contábil** | gera do razão real (1.060 lançamentos, 17 contas) | ✅ real |
| **Apuração lucro real** | IRPJ/CSLL Q1=84.860 · Q2=56.469, do razão | ✅ real |
| **Espelho Portte** | 850 verbas backfilladas, 6 competências | ✅ real |
| **Encanamento de transmissão eSocial** | assinatura XMLDSig real, mTLS real, cert .pfx, **7 protocolos de produção** | ✅ o ativo mais valioso |

## 2. O que NÃO está pronto — e é exatamente o que a Portte faz

A Portte não "calcula folha". Ela **transmite ao governo**. É aí que estamos fracos.

| Obrigação | Prontidão | Evidência medida |
|---|--:|---|
| **eSocial S-1200/S-1210** (remuneração) | **5%** | 2 stubs incompletos; **zero** transmissões nossas. Os 4 S-1200 + 4 S-1210 com recibo no banco são **espelho baixado** — a Portte transmitiu |
| **S-1010 / S-1005 / S-1020** (tabelas base) | **0%** | não existem — são pré-requisito do S-1200 |
| **S-1299** (fechamento) | **0%** | sem ele o período não fecha e a DCTFWeb não é gerada |
| **S-2200 / S-2299** (admissão/desligamento) | **35%** | geradores bons e completos, mas o endpoint só faz **download do XML** — não transmite |
| **S-2206** (alteração contratual) | **0%** | só o nome no enum |
| **S-2230** (afastamento) | **75%** | transmite de verdade; 1 protocolo real, recibo não casado |
| **S-2210** (CAT) | **80%** | **único ciclo completo**: protocolo + recibo + `aceita` |
| **S-2220** (ASO) | **55%** | ⚠️ 5 protocolos, **0 recibos, 0 no espelho** — indício de rejeição silenciosa; a tela mostra "transmitida" |
| **S-2240** | **30%** | gate humano deliberado (código biológico MB) |
| **DCTFWeb** | **25%** | não tem webservice de envio (é montada na Receita); entrega hoje é e-CAC manual; extractor é stub |
| **FGTS Digital** | **5%** | calculadora de 8% com **PIX inventado** (`fgts@caixa.gov.br`); as 46 guias são **PDFs do Onvio** |

## 3. O caminho crítico é linear (não dá para paralelizar)

```
S-1010 (rubricas) → S-1005/S-1020 (estabelecimento/lotação)
      → S-1200 (remuneração) → S-1299 (fechamento)
            → DCTFWeb apura sozinha na Receita
                  → FGTS Digital libera a guia
```

**Nada de DCTFWeb nem FGTS anda antes do S-1200 fechar.** Investir neles agora é desperdício.

## 4. Correção de um achado meu anterior (honestidade)

Reportei que o DCTFWeb **superestimava o INSS em +34%** por usar alíquota cheia. **Estava parcialmente
errado.** Medindo a composição do DARF **completo** de junho: CPP 20,00% + GILRAT 4,07% + terceiros
5,80% = **29,87%** — praticamente a constante `0.288` do código. O "+34%" vinha das **guias de
jan-mai, que são PARCIAIS** (CPP declarada a 7-13%), não de erro de alíquota nossa.

O que segue verdadeiro: a constante `INSS_PATRONAL_RAT_TERCEIROS = 0.288` está fixa em dois arquivos
(`pareamento_fiscal_service.py:13`, `dctfweb_service.py:162-164`) e **ignora o FAP** (que multiplica o
RAT por 0,5–2,0). Deve virar parâmetro por empresa, não constante.

## 5. Riscos que encontrei e que ninguém está vendo

1. **CNPJ do transmissor hardcoded** no envelope SOAP (`esocial_transmitter.py:819-823`:
   `35710481000103` literal) — **quebra no CNPJ 2 (Patrimonial)**. Bomba-relógio multi-CNPJ.
2. **5 ASOs "transmitida" sem recibo** — se foram rejeitados, a tela está mentindo e há um bug de
   leiaute em produção. Rodar `sst.esocial_pull_recibos` e ler `desc_resposta` antes de qualquer coisa.
3. **Ponto do 12x36 noturno é inutilizável** (9% dos dias pareados) — hoje mascarado porque a folha
   usa o espelho Portte. Quando a folha for nativa, o adicional noturno não terá base apurável.
4. **14 desligados sem data de desligamento** no cadastro — quebra cálculo proporcional.

## 6. Ordem recomendada para os 6 meses

| Fase | O que | Por quê |
|---|---|---|
| **0 — agora** | 3 riscos acima (CNPJ hardcoded, ASOs sem recibo, ponto noturno) | são bombas, não features |
| **1** | S-1010 + S-1005 + S-1020 | destrava tudo; é cadastro, não cálculo |
| **2** | S-1200 completo + S-1299 | **o coração**: é isto que substitui a Portte |
| **3** | Ligar S-2200/S-2299 no transmissor existente | 35%→90% com pouco esforço (encanamento pronto) |
| **4** | DCTFWeb (confessar no e-CAC) + FGTS Digital | só depois que o S-1200 fechar |
| **5** | Flip `source='conecta'` para oficial | decisão de diretoria |

## 7. Resposta honesta à pergunta "estamos com 90%?"

**Não.** Estamos com ~95% no que foi construído até aqui (reconciliação, razão, cálculo) e com **~20%
no que a Portte de fato entrega** (transmissão ao governo). A boa notícia é que o pedaço mais difícil
de acertar — assinar XML com certificado e transmitir via mTLS ao webservice do eSocial — **está feito
e tem 7 protocolos reais de produção provando**. O que falta é conteúdo de leiaute: trabalhoso,
volumoso, mas sem incógnita técnica.

---

## 8. Medição dos ATOS de DP/RH (adendo — mesma data)

| Ato | Cálculo real | Documento legal | Uso real no banco | **%** |
|---|---|---|---|--:|
| Admissão | ✅ cria employee c/ piso CCT | ⚠️ contrato em HTML de 1,7KB, sem ficha de registro | ❌ **0 admissões concluídas** (3 linhas, 2 de teste) | 55% |
| Rescisão | ⚠️ excelente (Súmula 461/171, multa FGTS indenizatória) mas **2 entradas chutadas** | ✅ TRCT + aviso prévio, branded, assináveis | ❌ 1 linha com `total_amount` NULL, 0 assinadas | 45% |
| **13º salário** | ⚠️ só calculadora pura, não persiste | ❌ | ❌ **nenhuma tabela** | **20%** |
| Férias | ✅ 1/3 + abono | ⚠️ aviso sim, **recibo não** | ✅ 67 períodos, 44 solicitações | 65% |
| **Afastamento** | ❌ **CRUD apenas** — sem 15 dias empresa vs INSS | ❌ | ⚠️ 8 linhas | **25%** |
| Ponto/espelho | ✅ HE/noturno/DSR | ✅ PDF assinável | ⚠️ 6.385 batidas, **1 espelho fechado** | 70% |

**DP/RH global: ~45%.**

### O padrão (vale mais que os números)
**A engenharia de cálculo está à frente da engenharia de processo, que está muito à frente da adoção.**
`clt_calculator.py` é ativo real (quem escreveu conhecia Súmula 461, Súmula 171, natureza indenizatória
da multa do FGTS). Os PDFs são sérios. Mas **nenhum ato foi concluído ponta a ponta em produção**.

### Achados que viram trabalho
1. **Rescisão tem 2 entradas presumidas**: `saldo_fgts = remuneração × 8% × meses` (o código admite:
   `"fgts_estimado": True`) e `ferias_vencidas_dias = 30 if meses > 12` **hardcoded, sem olhar o
   histórico de férias gozadas** → quem já tirou férias seria superpago. Nenhum TRCT pode ser
   homologado sem conferência manual — que é exatamente o trabalho da Portte hoje.
2. **13º é ausência, não incompletude**: sem parcelas, sem prazos (30/11 e 20/12), sem recibo, sem tabela.
3. **Afastamento sem cálculo**: 15 dias empregador vs INSS é o núcleo do ato e não existe.
4. **3 tabelas de férias concorrentes** (10/19/15 linhas) — decidir a fonte de verdade.
5. ⚠️ **Armadilha de UX**: `/action/rescisao-calc` devolve string formatada e **não grava nada**
   ("Cálculo — não gera rescisão"). Se estiver num botão que parece "fazer a rescisão", produz
   confiança falsa. **Verificar.**
6. `modules/pessoas/departamento_pessoal/` tem 9 subpastas com `__init__.py` **vazios** — esqueleto,
   não código. O DP real vive em `modules/people_management/hr/`.

## 9. Placar consolidado

| Frente | Reconciliar c/ Portte | **Substituir a Portte** |
|---|--:|--:|
| Contábil / Fiscal / Razão | ~95% | ~60% |
| Folha (cálculo) | 98,5% | ~70% |
| DP / RH (atos) | — | **~45%** |
| eSocial / transmissão gov | — | **~20%** |
| **Global** | **~95%** | **~35%** |
