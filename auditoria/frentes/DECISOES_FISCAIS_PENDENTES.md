# Decisões fiscais que só o Jordan pode tomar — 24/09/2026

> Todas vieram de algo **medido**, não de dúvida teórica. Cada uma tem o número do impacto e o
> que acontece se ficar em aberto. Ordenadas por urgência.

## 🔴 Urgente — afeta nota que sai AGORA pela Portte

### 1. O vale-alimentação do Ideal Flores está pela metade na planilha
A linha de setembro deduz **R$ 6.648,00** da base do INSS mas discrimina só
**VA 2.244,00 + VT 2.160,00 = R$ 4.404,00**. Faltam R$ 2.244,00 — e `4.488 + 2.160 = 6.648`
fecha exato, então o VA deveria ler **R$ 4.488,00**.

A dedução está certa. O que falta é **lastro no texto da nota**, que é o que a fiscalização lê.
**R$ 246,84 de INSS glosável**, mais multa. Corrigir na planilha antes da Portte emitir.

*(Há também R$ 0,23 de diferença no INSS: 11% de 59.194,42 dá 6.511,39 e a planilha diz 6.511,62.)*

### 2. A série 70000 colide com o portal da contabilidade
O portal usa a **mesma série 70000** (DPS 125 em 17/09). Se o ERP e o portal emitirem no mesmo
dia, pegam o mesmo número e o fisco recusa com `E0141`. **Série própria para o ERP, ou 70000?**

## 🟡 Trava a produção

### 3. O último número real de cada documento
Sem isso a primeira emissão em produção é recusada por duplicidade. O sistema já **se recusa a
emitir** antes de alguém declarar (guarda de 24/09), mas o número é seu:

| Documento | Empresa | Último conhecido | Fonte |
|---|---|---|---|
| NF-e série 1 | Eletrônica | **10.026** | DANFE 17/09, protocolo 113263811849419 |
| DPS série 70000 | Eletrônica | **125** | NFS-e 121, 17/09 |
| DPS série 70000 | Patrimonial | **75** | NFS-e 31, 26/08 |

Confira no emissor em uso no dia — esses números crescem a cada nota que a Portte emite.

### 4. Manutenção de CFTV é 14.01 ou 14.06?
Mesma empresa, mesmo mês, descrição **idêntica**, códigos diferentes:

| Nota | Descrição | Código |
|---|---|---|
| 116 | contrato de manutenção de CFTV/cerca/portões/cancelas | **14.01.01** |
| 120 | contrato de manutenção de CFTV/cerca/portões/cancelas | **14.06.01** |

Uma está errada, e o código define o ISS. Pergunta para o contador.

### 5. PIS e COFINS na NF-e da Eletrônica
A sua nota real 10.026 traz **zero**. O nosso cálculo traz **1,65% e 7,60%** com a norma citada.
Não há fonte para decidir qual está certo — é do contador.

## 🟢 Recuperação de valor pago a mais

### 6. A dedução de VA/VT vale retroativo?
**13 das 25 notas** da Patrimonial (junho a agosto) saíram com **11% cheio sobre o bruto**, sem
dedução — R$ 267.581,00 de base, R$ 29.433,85 de INSS. As outras 12 deduziram e economizaram
R$ 9.062,38. Foi inconsistência do escritório, não política.

**Recuperar o que foi pago a mais, ou a regra vale daqui para a frente?**

### 7. Cancelar a nota 26 no fisco
Você confirmou que foi erro (Mirante, R$ 12.061,50, duplica a 27). Ela está marcada aqui como
`erro_confirmado` e **não conta mais como receita**. Mas **no fisco segue VÁLIDA**. Cancelar tem
prazo.

### 8. O rateio do Mirante
O Mirante recebe **duas notas no mesmo mês** e o VA+VT do contrato é **um só** (R$ 4.662,00).
Deduzir o valor inteiro nas duas deduziria **duas vezes**. Proporcional ao valor de cada nota?

## ⚪ Cadastro e efetivo

### 9. Prime Arena tem 4 alocados e 8 trabalhando
Faltam quatro alocações. Gente sem alocação some da cobertura do posto, do custo do contrato e
da dedução do INSS. Laranjeiras tem 9 no sistema e 8 na planilha.

### 10. 857 dos 867 produtos não podem sair numa NF-e
Não casam com nenhuma nota de compra, então não se sabe como a mercadoria entrou — e sem isso
o CFOP/CST de saída seria chute. Importar as notas de entrada que faltam, ou registrar à mão.

### 11. Uma linha do cronograma sem empresa
**Prime Arena · Manutenção · R$ 1.084,50** ("manutenção do motor de portão de entrada") não tem
dados bancários na descrição. Eletrônica ou Patrimonial?

### 12. Os 9 produtos com CST 20/41/50/400
Dependem de habilitação da empresa na SEFAZ-AM. Copiar o benefício do fornecedor seria usar
incentivo alheio — o sistema recusa e pergunta, de propósito.
