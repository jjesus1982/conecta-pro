# O que os documentos REAIS têm e o nosso kit não tem (09/09/2026)

**Origem:** pasta enviada pelo Jordan em 09/09 (`uploads/referencia_kits/kit`): 5 contracheques reais da Portte/Domínio
(competências 07 e 08/2026), 1 recibo real de VT/VR, 1 boleto do SINETRAM, 1 relatório de pedido de VA (Sólides) e
1 relatório de pedido de VT (SINETRAM). Comparados com o holerite e o recibo que o Conecta PRO gera hoje
(kit do Conecta Village, 08/2026).

**Os reais cobrem cargos, salários e turnos diferentes de propósito:** AGP diurno (Jeovane, intrajornada diurna),
AGP noturno (Edward, hora noturna reduzida + intrajornada noturna + adicional noturno informativo), ASG com
insalubridade e salário-família (Ademir), artífice com afastamento por doença e falta parcial (Kalel), artífice
admitido no meio do mês (Nailson, 11 dias).

---

## 1. Contracheque — o que falta no NOSSO

### 1.1 Falta IMPRIMIR (o motor já calcula)

| Campo do real | Como aparece lá | Hoje no nosso |
|---|---|---|
| **Código da rubrica** | `8781 DIAS NORMAIS`, `998 I.N.S.S.`, `48 VALE TRANSPORTE` | temos código interno (0001, 1002…) e não imprimimos |
| **Referência com unidade** | `30,00` dias · `16:00` horas · `10,00` % insalubridade · `7,68` alíquota do INSS · `3,00` dependentes | texto livre ("base R$ 2143.28") |
| **Matrícula do funcionário** | `4`, `5`, `7`, `22` (código na folha) | imprime "—" |
| **Departamento e Filial** | `Depto: 3`, `Filial: 1` | imprime "—" |
| **Centro de custo / tipo de cálculo** | `CC: GERAL`, `Folha Mensal`, `Mensalista` | não existe |
| **Horas Mês contratuais** | `Horas Mês: 180,00` (12x36) e `220,00` (44h) | não existe |
| **Faixa IRRF** | coluna no rodapé | não existe |
| **Sal. Contr. INSS** (≠ base FGTS) | linha própria | mostramos só "Base INSS" |
| **Duas vias na mesma folha** | via do empregado + via do empregador | uma via só |

### 1.2 Falta CALCULAR (rubrica que o real tem e o nosso motor não emite sozinho)

Ordem de impacto no dinheiro (medido nos 5 reais):

1. **`981 DESC.ADIANT.SALARIAL`** — R$ 668,00 a R$ 697,01 por pessoa. É o adiantamento de 40% que você paga dia 20
   **descontado na folha**. Nosso holerite não tem essa linha: o líquido sai ~40% maior que o real. É o defeito
   mais grave para o kit de setembro em diante.
2. **`995 SALÁRIO FAMÍLIA`** — R$ 202,62 (3 quotas). O motor tem a constante (R$ 67,54/quota) mas não emite.
3. **`201/223 INSALUBRIDADE 10%`** — R$ 166,83 a R$ 167,00 (ASG e artífice). O motor tem a rubrica, mas nenhum
   dos nossos 12 de teste recebeu: falta o cadastro de quem tem direito por posto/função.
4. **`208/245 INTRAJORNADA NOTURNA` e `209 INTRAJORNADA DIURNO`** — R$ 222,67 a R$ 267,07. Existe no motor por
   `employees.recebe_intrajornada`, hoje vem do espelho da Portte (`USAR_ESPELHO_PORTTE = True`).
5. **`206/246 ADICIONAL NOTURNO (INFOR)`** — R$ 237,51: linha **informativa** (não soma), separada do adicional
   que soma. Nós somamos tudo numa linha só.
6. **`8870/8697 DIAS/HORAS AFAST. P/DOENÇA C/DIR. INTEGRAIS`** + nota no rodapé com o período do afastamento.
7. **`8069 HORAS FALTAS PARCIAL`, `8792 DIAS FALTAS`, `8794 DIAS FALTAS DSR`** — descontos de falta e do DSR.
8. **`150 HORAS EXTRAS 50%` e `250 REFLEXO EXTRAS DSR`** — o reflexo do DSR sobre extras não existe no nosso.
9. **`269/271/9750 DESC. EMP. CRED. TRAB Nº …`** — empréstimo consignado, R$ 108 a R$ 279 por pessoa, com o
   número do contrato na descrição. Não temos cadastro de consignado.
10. **`8181/8182/8184/832 DIFERENÇA MÉDIA/ADICIONAL 13º` e `8214 INSS DIFERENÇA 13º`** — acertos do 13º.
11. **`204/202 PLANO ODONTOLÓGICO`** — temos, mas com valor fixo; o real usa referência `8,50`.
12. **`8781 DIAS NORMAIS`** — o real paga por DIAS (30,00 / 29,00 / 11,00 no mês de admissão). O nosso escreve
    "Salário Base 30 dias" mesmo para quem foi admitido no meio do mês (Nailson: 11 dias, R$ 801,78).
13. **`ND` / `NF`** — número de dependentes de IR e de salário-família.
14. **`Informativa` / `Informativa Dedutora`** — totais de rubricas que não entram no líquido.

---

## 2. Recibo de VT/VR — o que falta no NOSSO

O recibo real (ADAILSON, 03/2026) tem:

- **Código da rubrica**: `218 VALE TRANSPORTE`, `219 VALE REFEIÇÃO` — os mesmos códigos da folha.
- **Valor unitário × quantidade** em colunas separadas (R$ 10,00 × 16 e R$ 22,00 × 16). O nosso junta em texto.
- **Período de utilização do benefício**: "para a minha utilização no decorrer do período de **17/03/2026 a
  16/04/2026**". O nosso só diz a competência. Esse período é o que prova a entrega antecipada exigida por lei.
- **Duas vias na mesma folha**.
- Não traz co-participação (o desconto aparece na folha, rubricas 48 e 9383). O nosso traz coluna de co-part.
  zerada — informação a mais, não a menos.

---

## 3. Documentos do kit real que NÃO existem no nosso kit

| Documento | O que prova | De onde vem |
|---|---|---|
| **Boleto SINETRAM (VT)** | a empresa comprou os créditos de vale-transporte do mês (R$ 270,00, venc. 21/07) | portal SINETRAM |
| **Relatório de Pedido de VT (SINETRAM)** | nº do pedido, CPF, nome, **nº do cartão** e valor por colaborador | portal SINETRAM |
| **Relatório de Pedido de VA (Sólides)** | pedido #332373, R$ 6.546,00, data de pagamento e distribuição, **por colaborador: alimentação e mobilidade**, status PAGO/DISTRIBUÍDO, intermediador (SWAP) | Sólides |

Esses três amarram o VT/VR: recibo do funcionário (nosso) + prova de compra (boleto) + prova de distribuição
(relatório). Hoje o nosso kit só tem o primeiro.

---

## 4. O que o NOSSO tem e o real não tem

Para não perder na troca: CBO na capa, escala (12x36), posto/condomínio, horas trabalhadas do ponto com a fonte
do adicional, bases de cálculo em destaque, timbrado, **assinatura eletrônica com hash e verificação**, e a
co-participação explicada com a base legal.

---

## 5. Ordem sugerida (do que muda o número para o que muda o layout)

1. `DESC.ADIANT.SALARIAL` — sem isso o líquido do nosso holerite está errado a partir de agosto.
2. Salário-família, insalubridade por posto, intrajornada e faltas/DSR próprios (desliga a dependência da Portte).
3. Consignado (cadastro + rubrica).
4. Layout: código de rubrica, referência com unidade, matrícula/depto/filial, horas-mês, faixa IRRF, duas vias.
5. Recibo VT/VR: código, unitário × quantidade, período de utilização, duas vias.
6. Kit: boleto do SINETRAM e os dois relatórios de pedido (VT e VA) como documentos do bloco de benefícios.
