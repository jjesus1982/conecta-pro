# LENTE D — Storage físico de documentos (uploads/ e credenciais)

**uploads/** = 917 arquivos, 321MB (713 PDF · 142 HTML · 20 md · 19 png · 9 json · 7 txt). Montado no container em `/app/uploads`. Cada subpasta = um tipo de documento gerado/puxado/inserido que precisa de botão abrir-HTML/baixar-PDF no redesign.

| Arquivos | Subpasta | Tipo de documento |
|---:|---|---|
| 373 | onvio | Guias/documentos fiscais puxados do Onvio (FGTS/INSS/DAS) |
| 132 | ponto | Espelhos de ponto (Portaria 671) |
| 90 | ged | Documentos GED (histórico + kits) |
| 60 | solides_ged | Documentos GED puxados do Sólides/Tangerino |
| 49 | docs | Documentos diversos |
| 47 | solides_espelhos | Espelhos de ponto do Sólides |
| 35 | fiscal_guias | Guias fiscais (PDF) |
| 23 | sst_mb | SST (OCR extraído — ASO/PPRA/PGR) |
| 21 | candidatos_staging | Documentos de candidatos (currículo/KYC) |
| 8 | contratos_gerados | Contratos gerados (por UUID) |
| 6 | cnds | Certidões (CND) |
| 5 | funcionario | Documentos do funcionário |
| 4 | signed | Documentos assinados |
| 4 | kit_checklists | Checklists de kit |
| 4 | folhas | Folhas de pagamento |
| 3 | kit_indices | Capa/índice de kit |
| 2 | portal | Documentos do portal |
| 2 | avisos_gerados | Avisos prévios gerados |
| 1 | payslips / notas / kit_entregas / dp_conferencia | Holerite / NFS-e / entrega de kit / conferência DP |

> agent_knowledge/agent_media/assets/_backup_materiais = internos (RAG/marca), não são documentos de usuário.

**credentials/** = 10 arquivos (certs A1 .pfx/.crt/.key) — NÃO são documento de usuário, não expor (correto).

## Censo de endpoints que fazem STREAM de arquivo (FileResponse/StreamingResponse/media_type), backend
**50 endpoints** reais de stream de arquivo: people_management(17), financial(7), hr(5), government_integrations(3), crm(3), juridico(2), ged(2), client_portal(2), reimbursement(1), operacional(1), integrations(1), gedeon(1), fiscal_contabil(1), campo(1), ai(1).
