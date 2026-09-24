# Prontidão para PRODUÇÃO — NF-e e NFS-e, os dois CNPJs

> **Condição de parada dada pelo dono em 24/09/2026:** *«só para quando as emissões de notas
> dos cnpjs estiverem totalmente validadas, homologadas e prontas produção»*.
>
> Este documento é a régua. Cada linha é **medida**, com a data da medição. Enquanto houver
> ⬜ ou ⛔ nas colunas «homologado» e «pronto p/ produção», o loop não para.

## Quadro geral — 24/09/2026, 17:30

| Documento | Empresa | Emite? | Homologado | Pronto p/ produção |
|---|---|---|---|---|
| **NF-e 55** (produto) | ELETRÔNICA | sim | ✅ **cStat 100** · nProt 113260013553955 · série 2 nº 1, de PRODUÇÃO | ⬜ falta ICMS-ST e numeração |
| **NF-e 55** (produto) | PATRIMONIAL | **nunca** — decisão do dono, só tem inscrição municipal | — | — |
| **NFS-e** (serviço) | ELETRÔNICA | sim | ✅ **cStat 100** · nDFSe 19174/19176/19177 | ⬜ falta conciliação e numeração |
| **NFS-e** (serviço) | PATRIMONIAL | sim | ✅ **cStat 100** · nDFSe 19175 | ⬜ falta conciliação e numeração |

**Também exercidos contra o órgão, em homologação:** cancelamento de NF-e (cStat **135**),
inutilização de faixa (cStat **102**), status do serviço nos dois CNPJs (cStat **107**).

**Trava de produção, medida agora:** `producao_liberada = false` nos dois CNPJs ·
**0 notas gravadas com `tp_amb='1'`**.

---

## O que falta, por natureza

### A. Defeitos fiscais que fariam pagar imposto a mais — EM CORREÇÃO

| # | O quê | Dinheiro | Estado |
|---|---|---|---|
| A1 | **ICMS-ST na saída da NF-e.** A nota real 10.026 sai CFOP 5405 / CST 060 / ICMS 0,00; a régua devolvia 5102 e o emissor produzia CST 00 com ICMS 20%. **97 de 207 itens de compra (47%)** entram com ICMS já retido por ST. | ~20% sobre metade do catálogo | frente **AA5** rodando |
| A2 | **Base do IBS/CBS = valor − ISS.** Medido nas 4 notas da Eletrônica: as «Exclusões» são exatamente o ISSQN apurado. | 1% sobre o ISS de cada nota | frente **AA4** rodando |
| A3 | **PIS/COFINS não retidos na Eletrônica**, por decisão judicial citada na nota 121: processo **1038495-94.2024.4.01.3200**. | 4,65% sobre a base, por nota | frente **AA4** rodando |
| A4 | **INSS 11% com dedução de VA+VT** em toda nota da Patrimonial (cessão de mão de obra). Em agosto reteve-se 11% do **bruto**, sem dedução, nas 5 notas. | **R$ 1.431,98** só nas 3 linhas do cronograma de setembro | frentes **AA4** + **AA6** rodando |
| A5 | **IRRF: não reter.** Decisão do dono em 24/09. Parâmetro por empresa, não `if` no código. | 1% por nota da Eletrônica | frente **AA4** rodando |

### B. Numeração — impede a primeira emissão em produção

| # | O quê | Valor medido | Estado |
|---|---|---|---|
| B1 | **NF-e da Eletrônica está em nº 10.026, série 1** (DANFE de 17/09, protocolo 113263811849419). O contador daqui nasce em 1 e a SEFAZ recusa por duplicidade. | 10.026 | ⬜ gravar antes da 1ª emissão |
| B2 | **DPS da NFS-e: série 70000** nas duas empresas (o código assumia 900 → `E0141`). Último nº observado: Patrimonial **75**, Eletrônica **125**. | 75 / 125 | ⬜ conferir contra a conciliação |
| B3 | **Homologação é compartilhada com o sandbox.** Produção emite em série 2; o sandbox ficou com a 1. Série de produção é decisão do dono. | — | ⬜ decisão |

### C. Verdade do dado — o sistema não sabe o que já aconteceu

| # | O quê | Tamanho | Estado |
|---|---|---|---|
| C1 | **37 notas emitidas no fisco sem linha aqui** (33 Eletrônica, 4 Patrimonial). | 37 notas | frente **AA4** rodando |
| C2 | **27 NFS-e dizem «autorizada» e nunca foram transmitidas** — zero protocolo, zero XML. | R$ 542.673,92 | ⛔ **aguarda o dono** |
| C3 | **A precificação lê a tabela errada.** `faturado_na_competencia` soma `nfses` (as 27 fantasmas) e ignora `nfse_emitidas_nacional` (as 115 reais). De 03 a 09/2026 são **R$ 1.759.088,51** de faturamento real invisível. | R$ 1,76 mi | ⛔ **aguarda o dono** |
| C4 | **Nota 26 da Patrimonial foi erro** (confirmado pelo dono) e **segue válida no fisco**. Cancelar tem prazo. | R$ 12.061,50 | ⛔ **decisão fiscal do dono** |
| C5 | **Efetivo por contrato não confere.** Prime Arena tem 4 alocados e 8 trabalhando; Laranjeiras 9 contra 8. Alimenta a dedução do INSS. | 9 contratos | frente **AA6** rodando |

### D. O que não existe e o dono precisa saber

| # | O quê | Impacto |
|---|---|---|
| D1 | **Conciliação automática com o fisco.** Se o fisco autoriza e o INSERT falha, a nota existe lá e não aqui — foi assim que as 37 sumiram. | frente **AA4** |
| D2 | **VA e VT por contrato/mês não estão no sistema.** As tabelas de benefício têm 0 linhas; a folha só tem o **desconto do empregado**, que é base errada. | frente **AA6** |
| D3 | **Carta de correção (evento 110110)** não implementada. Só cancelamento e inutilização. | erro de texto na nota só se resolve cancelando |
| D4 | **Contingência (SVC-AN / FS-DA)** não implementada. SEFAZ fora do ar = emissão falha, com o motivo gravado. | sem caminho alternativo |
| D5 | **XSD local (PL_010) não está no repositório** — download com captcha. O validador real é a SEFAZ, que devolve 215 com a mensagem do schema. | pendência de infraestrutura |

---

## Como ligar produção, quando tudo acima estiver verde

1. `NFE_AMBIENTE=1` **e** `NFE_PRODUCAO_LIBERADA` com a frase-senha no `.env` (NF-e).
2. `UPDATE empresas SET nfse_ambiente='producao'` **e** `NFSE_PRODUCAO_LIBERADA` (NFS-e).
3. `nfe_numeracao` e `nfse_numeracao` nascem com o último número REAL por CNPJ+série.
4. Recomendação: antes, **uma competência inteira em homologação** com clientes e valores reais,
   conferida contra as notas que a Portte emitiu no mesmo mês.

> Setembro sai pela **Portte Contábil** — o cronograma já foi enviado a eles. Isso tira a pressa
> da emissão, não o rigor: o sistema precisa estar certo para assumir depois.
