# S-1010 — rubricas aguardando códigos legais do eSocial (2026-07-31)

> Para transmitir o S-1010 (pré-requisito do S-1200) cada rubrica precisa de 4 códigos
> legais. **Não são deduzíveis** dos flags `incide_*`: um booleano diz *se* incide; o
> eSocial exige *qual* incidência. Preencher por palpite = declarar base errada ao governo.

Preencher: **natRubr** (Tabela 3) · **codIncCP** (Tab. 20) · **codIncIRRF** (Tab. 21) · **codIncFGTS** (Tab. 22).
`tpRubr` já preenchido (1=provento, 2=desconto) — única dedução sem risco.

| codRubr | Descrição | tipo | tpRubr | incide INSS/IRRF/FGTS (nosso flag) | natRubr | codIncCP | codIncIRRF | codIncFGTS |
|---|---|---|:--:|:--:|---|---|---|---|
| 0001 | Salario Base | provento | 1 | S/S/S |  |  |  |  |
| 0010 | Hora Extra 50% | provento | 1 | S/S/S |  |  |  |  |
| 0011 | Hora Extra 100% | provento | 1 | S/S/S |  |  |  |  |
| 0020 | Adicional Noturno | provento | 1 | S/S/S |  |  |  |  |
| 0021 | Hora Noturna Reduzida | provento | 1 | S/S/S |  |  |  |  |
| 0030 | Intrajornada Nao Concedida | provento | 1 | S/S/S |  |  |  |  |
| 0040 | Adicional Ronda 15% | provento | 1 | S/S/S |  |  |  |  |
| 0041 | Adicional Ronda 30% | provento | 1 | S/S/S |  |  |  |  |
| 0050 | Adicional Insalubridade 10% | provento | 1 | S/S/S |  |  |  |  |
| 0051 | Adicional Periculosidade 30% | provento | 1 | S/S/S |  |  |  |  |
| 0060 | Vale Refeicao | provento | 1 | N/N/N |  |  |  |  |
| 0061 | Vale Transporte | provento | 1 | N/N/N |  |  |  |  |
| 0070 | 13o Salario 1a Parcela | provento | 1 | N/N/S |  |  |  |  |
| 0071 | 13o Salario 2a Parcela | provento | 1 | S/S/S |  |  |  |  |
| 0080 | Ferias | provento | 1 | S/S/S |  |  |  |  |
| 0090 | DSR sobre HE | provento | 1 | S/S/S |  |  |  |  |
| 0100 | Taxa Negocial Provento | provento | 1 | N/N/N |  |  |  |  |
| 1001 | INSS | desconto | 2 | N/N/N |  |  |  |  |
| 1002 | IRRF | desconto | 2 | N/N/N |  |  |  |  |
| 1010 | Desconto VT | desconto | 2 | N/N/N |  |  |  |  |
| 1011 | Desconto VR | desconto | 2 | N/N/N |  |  |  |  |
| 1020 | Desconto Plano Odontologico | desconto | 2 | N/N/N |  |  |  |  |
| 1021 | Desconto Seguro de Vida | desconto | 2 | N/N/N |  |  |  |  |
| 1030 | Taxa Negocial Desconto | desconto | 2 | N/N/N |  |  |  |  |

Depois de preenchido, gravar em `rubricas_folha` (colunas `esocial_nat_rubr`,
`esocial_cod_inc_cp`, `esocial_cod_inc_irrf`, `esocial_cod_inc_fgts`) + `esocial_validado_por`/`_em`.
O gerador `XMLBuilder.build_s1010_rubrica` **recusa** emitir enquanto faltar qualquer um.
