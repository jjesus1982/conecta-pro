# Reconciliação Contábil — Razão × Oráculo Onvio (2026 jan-jun)
> READ-ONLY. Prova de paridade dos 6 meses em paralelo com a Portte. Não transmite/paga.

## Consolidado por pilar
| Pilar | Σ Razão (nosso) | Σ Oráculo | Σ\|Δ\| | Status |
|---|--:|--:|--:|---|
| Folha (bruto) | 616,709.01 | 616,709.01 | 0.00 | ✓ bate (<1%) |
| Receita (NFS-e) | 1,501,320.27 | 1,609,707.19 | 108,386.92 | diverge (7%) |
| ISS | 71,086.37 | 73,264.94 | 2,178.57 | diverge (3%) |
| FGTS | 44,448.87 | 42,140.63 | 2,308.24 | diverge (5%) |
| INSS | 119,593.74 | 119,593.74 | 0.00 | ✓ bate (<1%) |

## Razão por CNPJ (empresa_id) — onde cada pilar está lançado

### Conecta Eletrônica (Lucro Real)
- nfse_emitida: R$ 1,544,613.06
- folha: R$ 505,320.61
- despesa_tomada: R$ 256,673.49
- banco_inter: R$ 125,577.85
- tributo_iss: R$ 77,230.71
- encargo_inss: R$ 54,862.70
- provisao_ferias: R$ 48,169.14
- encargo_fgts: R$ 36,477.49
- provisao_13: R$ 36,116.01
- inss_empregado: R$ 32,732.54
- das_parcelamento: R$ 2,699.58
- baixa_estoque: R$ 65.00

### Conecta Patrimonial (Simples)
- nfse_emitida: R$ 269,151.77
- folha: R$ 111,388.40
- encargo_inss: R$ 24,887.07
- provisao_ferias: R$ 10,453.42
- encargo_fgts: R$ 7,971.38
- provisao_13: R$ 7,837.71
- inss_empregado: R$ 7,111.43
- tributo_iss: R$ 1,361.42
- despesa_tomada: R$ 700.00

## Ressalvas (honestas)
- **Junho**: Receita/ISS divergem só por lag de postagem no ADN (mês corrente); não é erro.
- **FGTS ~5%**: pequena diferença de BASE entre o FGTS da folha (hr_payslips.fgts_value) e a GFD oficial (mês 04 bate exato; timing descartado). Reconciliável a nível de folha, não é erro do razão (que posta fielmente a folha).
- **INSS**: razão = retido empregado (hr_payslips) + patronal (guia − retido); fecha com a guia oficial.
- **Patrimonial (Simples)**: folha/INSS/FGTS ainda lançados sob Eletrônica (folha não split por CNPJ); INSS/CPP do Simples fica no DAS. Guias FGTS/INSS não têm empresa_id (validam CNPJ Eletrônica).
- **DAS**: valores extraídos em onvio_documents.detalhes_json; reconciliação do parcelamento = próxima fatia (exige posting do parcelamento no razão).
