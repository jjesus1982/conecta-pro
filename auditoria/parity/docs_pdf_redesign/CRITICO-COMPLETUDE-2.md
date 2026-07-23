# CRÍTICO DE COMPLETUDE — 2ª passada (convergência)

> Objetivo: achar o que AINDA falta DEPOIS das correções L1–L5 (já fechadas na matriz). Adversarial: assumi que ainda há buracos e provei na fonte. NÃO re-reporto L1–L5.

Método: varredura backend módulo-a-módulo (`FileResponse|StreamingResponse|reportlab|openpyxl|csv.writer|zipfile|Document(|Presentation|BytesIO`), cruzamento com `0-INVENTARIO-TELAS-REDESIGN.md` (258 telas) e `MATRIZ-MESTRE-REDESIGN.md`, checagem de montagem em `main_production.py` e sanidade de 8 rotas ✅.

---

## V1 — Cobertura backend módulo-a-módulo

Varri os 46 módulos. A grande maioria dos geradores já está na matriz (crm pdf, gedeon danfse/cnd/kit, ged kits/docs, people_management folha/holerite/trct/espelho/ppp/epi/nr1, hr payroll/afd/portal, juridico parecer/det, financial relatorio/aging, fiscal guias, operacional rondas). **Geradores REAIS não presentes na matriz nem em L1–L5:**

| # | Gerador | Rota (montada) | Fmt | Tela redesign | Estado |
|---|---|---|---|---|---|
| **N1** | `folha/services/recibo_vt_vr_pdf.py` (`montar_recibo_vt_vr_pdf`, padrão-ouro) | `GET /people-management/folha/recibo-vt-vr/{employee_id}/{mes}/{ano}/pdf` ✅ **live** (folha_router montado) | PDF | departamento-pessoal/folha; operacional/diaristas-fechamento | **READY, não mapeado** |
| **N2** | `financial/controllers/bank_reconciliation_controller.py::export_reconciliation` | `GET /financial/bank-reconciliations/{id}/export?export_format=csv` ✅ **live** (montado em `/financial`, linha 778) | CSV (dentro de JSON `{content,filename}`) | financeiro/conciliacao | **READY, não mapeado** — CSV vem embrulhado em JSON, precisa blob client-side (não `abrirPdf`) |
| **N3** | `crm/services/report_pdf.py::build_commercial_report_pdf` + `doc_pdf.py::build_visit_report_pdf` | `GET /crm/growth/reports/comercial/pdf`, `GET /crm/growth/relatorio-comercial`, `POST /crm/growth/visitas/pdf` ✅ **live** | PDF | crm/dashboard; relatorios/comercial | **READY, só parcialmente coberto** pelo guarda-chuva "crm docs ✅" |
| **N4** | `human_resources/.../candidatos_esteira_controller.py::dossie_candidato` + `baixar_documento_candidato` | `GET /human-resources/candidatos/{id}/dossie` (JSON) + `GET /human-resources/candidatos/{id}/documento/{doc_id}` (FileResponse) ✅ **live** (aggregator montado) | JSON→PDF / blob | recrutamento/candidatos; rh/candidatos | **doc download READY; dossiê KYC ainda só-JSON** (🔨 render). Memória diz que dossiê Infosimples deve virar PDF |
| **N5** | `hr/analytics_dashboard/controllers/report_controller.py::download_report` | `/{report_id}/download/{run_id}` → retorna `{"message":"Download não implementado nesta versão"}` | — | relatorios/dashboards; agendador | ⛔ **STUB**; e o router `analytics_dashboard` **não aparece montado** em main_production → provável morto (categoria L1) |

---

## V2 — Telas redesign sem documento mapeado que DEVERIAM ter

Cruzei as 258 telas. Buracos novos (fora dos já listados no §operacional/fiscal/financeiro da matriz):
- **recrutamento (5 telas)** e **rh/candidatos** — não têm linha na matriz, mas têm docs reais: dossiê KYC + documentos do candidato + ficha de admissão (N4). **Lacuna.**
- **relatorios/comercial** — CRM tem relatório comercial PDF real (N3). **Lacuna parcial.**
- **financeiro/conciliacao** — export CSV real (N2). **Lacuna.**

Telas legitimamente SEM documento gerado (convergiu, nada a ligar): agendador, automacoes, analytics, assistente, marketing, seguranca (LGPD — só ações), suprimentos, servicos, integracoes, configuracoes, meu-espaco (já L5), homologacao, bi (client-side já ✅).

---

## V3 — Notificações/comunicados com anexo

`notifications/` **não tem nenhuma rota de download/FileResponse**. `action_url` é deep-link interno (navegação), não documento. Não localizei endpoint servindo `communication_announcements.anexos` / `notification_queue.attachments`. **Convergiu** — nada para ligar. Ressalva: se anexos de comunicado existirem em disco, falta uma rota de serve (não provei binário; baixa prioridade).

---

## V4 — Checklists/vistorias/inspeções/OS com foto/assinatura

- **Ronda/inspeção**: `inspection_round_controller.py` → `GET /operacional/rondas/{id}/relatorio/pdf` já está na matriz (✅). Sem gap.
- **Fotos de checkpoint no portal do cliente**: `client_portal/operacao_controller.py::/visitas/{round_id}/checkpoints/{checkpoint_id}/fotos/{nome}` (FileResponse) — download de FOTO (não documento/PDF) na area-do-cliente. Minor; pode virar item em area-do-cliente/operacao se quiser galeria baixável.
- **Justificativa de ponto** (`time_tracking/justification_controller.py`), **checklist_preenchido**, **ordens_servico.fotos/assinatura**: **não geram PDF/relatório** — sem FileResponse/reportlab. **Convergiu.**

---

## V5 — Formatos exóticos (docx/pptx/ics/zip)

- **PPTX**: `crm/services/presentation_builder.py` — já na matriz (apresentacao ✅).
- **ZIP**: `ged/.../kit_pdf_controller` (download-zip ✅) e `people_management/ged/export_service.py::generate_zip` (kit ZIP — mesmo padrão, coberto por GED kits).
- **DOCX**: só **INPUT/leitura** (`cfo_controller`, `juridico/consultor_controller`, `resume_parser_service` leem .docx; não geram). Confirma nota da matriz "DOCX só input".
- **ICS/vCalendar**: inexistente. **Convergiu** — nada novo.

---

## V6 — Sanidade dos endpoints ✅ da matriz (8 amostrados)

Todos confirmados existentes e sob router montado em `main_production.py`. **Nenhum fantasma.**

| Rota ✅ | Prova |
|---|---|
| `/ged/documents/{id}/download` | document_controller.py:569 `download_file` |
| `/ged/kits/{id}/download-zip` | kit_pdf_controller.py:547 |
| `/gedeon/cnd/pdf/{type}` | cnd_controller.py:248 |
| `/rep/afd/export/{device}/download` | afd_controller.py:114 |
| `/crm/proposals/{id}/pdf` | proposal_controller.py:37 (media_type pdf) |
| `/juridico/pareceres/{id}/pdf` | documentos_controller.py:69 |
| `/financial/.../relatorio` (PDF) | relatorios_controller.py:1275 usa `gerar_relatorio_pdf` |
| `/operacional/rondas/{id}/relatorio/pdf` | inspection_round_controller.py:773 |

---

## VEREDITO

**LACUNAS NOVAS** (5, priorizadas):

1. **N1 — Recibo VT/VR PDF** (ALTA): rota real, padrão-ouro, **pronta para ligar** em DP/folha e operacional/diaristas-fechamento. `GET /people-management/folha/recibo-vt-vr/{emp}/{mes}/{ano}/pdf`. 💰
2. **N4 — Candidato: documentos + dossiê KYC** (MÉDIA-ALTA): download de documento **pronto** (`/human-resources/candidatos/{id}/documento/{doc_id}`); dossiê ainda só-JSON → 🔨 render PDF. Telas recrutamento/candidatos e rh/candidatos **não estavam na matriz**.
3. **N3 — CRM relatório comercial + relatório de visita PDF** (MÉDIA): rotas reais em `/crm/growth/...`, só parcialmente cobertas pelo guarda-chuva; mapear em crm/dashboard e relatorios/comercial.
4. **N2 — Conciliação bancária export CSV** (MÉDIA): rota real `/financial/bank-reconciliations/{id}/export`; **atenção**: CSV vem embrulhado em JSON → precisa de handler blob próprio (não o `abrirPdf`/`baixarArquivoAutenticado` padrão). Tela financeiro/conciliacao. 🔒
5. **N5 — HR scheduled reports download = STUB e provavelmente não-montado** (BAIXA): "Download não implementado"; router `analytics_dashboard` sem include em main_production — decidir reviver/matar (mesma classe do L1).

Não-lacunas confirmadas (convergiu): notificações/anexos, checklists/justificativa/OS, DOCX (só input), ICS (inexistente), 8 rotas ✅ sem fantasma, fotos de ronda no portal = mídia, não documento.
