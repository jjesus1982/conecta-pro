# Inventário de Geradores de Documento — Financeiro / Fiscal / Contábil

**Missão:** dar botões "abrir HTML" + "baixar PDF" para todo documento/relatório/guia/extrato/comprovante gerado pelo backend, na versão *redesign* do frontend.
**Escopo:** `backend/modules/{financial,financeiro,fiscal_contabil,fiscal,reports,analytics}/`
**Base de API em produção:** `main_production.py` → `api_router = APIRouter(prefix="/api/v1")` (linha 336). Todo path abaixo já vem prefixado.
**Data:** 2026-07-22 · READ-ONLY.

### Notas de topo (importantes)
- `modules/financeiro`, `modules/reports`, `modules/analytics`, `modules/fiscal` são **agregadores/deprecated** — reexportam routers cujo código real vive em `modules/financial`, `modules/fiscal_contabil`, `modules/empresas`, `modules/ged`, `modules/gedeon`.
- **Único gerador PDF de relatório compartilhado:** `financial/services/relatorio_financeiro_pdf.py:30` `gerar_relatorio_pdf()` (reportlab, marca Conecta). Usado por DRE/Balancete/Fluxo/Aging. Recebe seções já calculadas, **não recalcula**.
- **DANFSe (NFS-e) PDF:** gerado por `modules/gedeon/services/nfse_danfse_generator.py` (`gerar_danfse_de_nfse` / `gerar_danfse_pdf`) — **fora do path de escopo**, mas invocado pelas rotas em escopo.
- Gates de módulo em produção: `_FIN_GATE = require_permission("module:financeiro")` (main_production.py:321) e `_FISCAL_GATE = require_permission("module:fiscal")` (:322). Lembrete de MEMORY: financeiro = só Jordan; fiscal = Jordan + Pyetra.

---

## A) DOCUMENTOS COM ARQUIVO REAL (PDF/TXT) — botão HTML+PDF direto

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| DRE (Demonstração do Resultado) | GET `/api/v1/financial/relatorios/dre/pdf?ano=` | PDF (inline) | POR-TELA (agregado por ano) | `get_current_user` + `_FIN_GATE` | `financial/controllers/relatorios_controller.py:1267` |
| Balancete | GET `/api/v1/financial/relatorios/balancete/pdf?ano=&mes=` | PDF (inline) | POR-TELA (ano/mês) | `get_current_user` + `_FIN_GATE` | `financial/controllers/relatorios_controller.py:1292` |
| Fluxo de Caixa | GET `/api/v1/financial/relatorios/fluxo-caixa/pdf?ano=` | PDF (inline) | POR-TELA (ano) | `get_current_user` + `_FIN_GATE` | `financial/controllers/relatorios_controller.py:1321` |
| Aging Contas a Receber | GET `/api/v1/financial/receivables/aging/pdf?condominio_id=` | PDF (inline) | POR-TELA (filtro condomínio opcional) | `get_current_user` + `_FIN_GATE` | `financial/controllers/receivable_controller.py:943` |
| Aging Contas a Pagar | GET `/api/v1/financial/payables/aging/pdf?condominio_id=` | PDF (inline) | POR-TELA (filtro condomínio opcional) | `get_current_user` + `_FIN_GATE` | `financial/controllers/payable_controller.py:642` |
| **DANFSe — NFS-e EMITIDA** 🟡gov/fiscal | GET `/api/v1/financial/fiscal/nfse/{nfse_id}/danfse?download=` | PDF (inline ou attachment) | **POR-ITEM** (`nfse_id`) | `get_current_user` + `_FISCAL_GATE` | `financial/controllers/fiscal_controller.py:1734` |
| **DANFSe — NFS-e RECEBIDA/tomada** 🟡fiscal | GET `/api/v1/financial/nfse-entrada/{chave}/pdf` | PDF (inline; do `xml_raw` fiel ou fallback) | **POR-ITEM** (`chave` de acesso) | `get_current_user` + `_FIN_GATE` | `financial/controllers/nfse_entrada_controller.py:87` |
| **Guia fiscal oficial (DAS/DARF/FGTS/INSS/parcelamento)** 🟡gov | GET `/api/v1/fiscal/guias-drive/pdf/{obligacao_id}?download=` | PDF real do Drive (`FileResponse`) | **POR-ITEM** (`obligacao_id`) | `CurrentActiveUser` + `_FISCAL_GATE` | `fiscal_contabil/obrigacoes/guias_drive_controller.py:75` |

---

## B) RELATÓRIOS/LISTAS EM JSON — telas que HOJE não têm arquivo (candidatos a render HTML+PDF no front)

Estes retornam JSON puro (dado real, alimentam a tela). Não há PDF/HTML server-side — o redesign pode acrescentar o botão gerando client-side ou criando rota `/pdf` gêmea (padrão já usado em DRE/Balancete/Fluxo).

| Documento | Método + Path completo | Formato | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| Guias do mês (lista consolidada; cada item traz `pdf_url`) 🟡gov | GET `/api/v1/financial/relatorios/guias-do-mes?competencia=MM/AAAA` | JSON | POR-TELA (competência) | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:293` |
| DRE (dados) | GET `/api/v1/financial/relatorios/dre?ano=&mes_inicio=&mes_fim=&comparativo=` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:661` |
| DRE mensal | GET `/api/v1/financial/relatorios/dre/mensal` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:705` |
| Balancete (dados) | GET `/api/v1/financial/relatorios/balancete` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:773` |
| Balancete real (accounting_entries) | GET `/api/v1/financial/relatorios/balancete-real?ano=&mes=` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:366` |
| Balanço Patrimonial | GET `/api/v1/financial/relatorios/balanco-patrimonial` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:816` |
| Fluxo de Caixa (dados) | GET `/api/v1/financial/relatorios/fluxo-caixa` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:605` |
| Contas a Receber (relatório) | GET `/api/v1/financial/relatorios/contas-receber` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:612` |
| Contas a Pagar (relatório) | GET `/api/v1/financial/relatorios/contas-pagar` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:619` |
| Fornecedores (relatório) | GET `/api/v1/financial/relatorios/fornecedores` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:626` |
| Apuração Lucro Real 🟡fiscal | GET `/api/v1/financial/relatorios/apuracao-lucro-real` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:633` |
| Painel fiscal | GET `/api/v1/financial/relatorios/painel-fiscal` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:418` |
| Tributos | GET `/api/v1/financial/relatorios/tributos` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:536` |
| Orçamentos / execução / YTD | GET `/api/v1/financial/relatorios/orcamentos[/execucao|/ytd]` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:858,911,963` |
| Custeio ABC (resumo/margem/listar) | GET `/api/v1/financial/relatorios/custeio/{resumo,margem-por-tipo,listar}` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/relatorios_controller.py:1006,1043,1059` |
| Relatório executivo financeiro (Advisor IA) | GET `/api/v1/financial/advisor/relatorio?periodo=YYYY-MM` | JSON | POR-TELA (período) | `get_current_user` + `_FIN_GATE` | `financial/controllers/ai_controller.py:767` |
| Resumo fiscal NFS-e entrada | GET `/api/v1/financial/nfse-entrada/resumo-fiscal` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/nfse_entrada_controller.py:155` |
| Stats fiscais reais | GET `/api/v1/financial/nfse-entrada/fiscal/stats-real` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/nfse_entrada_controller.py:369` |
| Resumo de custos | GET `/api/v1/financial/nfse-entrada/custos/resumo` | JSON | POR-TELA | `_FIN_GATE` | `financial/controllers/nfse_entrada_controller.py:413` |
| DAS por competência / faixas / receita-12m 🟡gov | GET `/api/v1/financial/fiscal/das[...]` | JSON | POR-TELA | `_FISCAL_GATE` | `financial/controllers/fiscal_controller.py:1283,1347,1367` |
| Retenções NFS-e por competência 🟡fiscal | GET `/api/v1/financial/fiscal/nfse/retencoes/competencia` | JSON | POR-TELA | `_FISCAL_GATE` | `financial/controllers/fiscal_controller.py:989` |
| Painel/stats/dashboard fiscal | GET `/api/v1/financial/fiscal/{stats,dashboard}` | JSON | POR-TELA | `_FISCAL_GATE` | `financial/controllers/fiscal_controller.py:1495,1513` |
| SUFRAMA economia | GET `/api/v1/financial/fiscal/suframa/economia` | JSON | POR-TELA | `_FISCAL_GATE` | `financial/controllers/fiscal_controller.py:1471` |
| CFO IA — panorama/projeção/previsão | GET `/api/v1/financial/cfo/{panorama,projecao-caixa,previsao-custos,...}` | JSON | POR-TELA | `_FIN_GATE` | `financial/cfo_controller.py:36,72,81` |
| Consultor Fiscal IA — panorama | GET `/api/v1/fiscal/consultor/panorama` | JSON | POR-TELA | `_FISCAL_GATE` | `fiscal/controllers/consultor_fiscal_controller.py:35` |

*(Nota: `cfo/perguntar-arquivo` :170 e `consultor/perguntar-arquivo` :59 CONSOMEM upload PDF/DOCX — são entrada, não geram documento.)*

---

## C) EMISSÃO DE DOCUMENTO FISCAL (gera XML/documento gov) — 🟡gov/legal, dinheiro/tributo

| Documento | Método + Path completo | Formato(s) | Granularidade | Auth/gate | Arquivo:linha |
|---|---|---|---|---|---|
| **Emitir NF-e** (retorna `xml_autorizado` + `pdf_danfe`) 🟡gov | POST `/api/v1/financial/fiscal/nfe/emitir` | JSON c/ XML+PDF (base64/URL, campo `pdf_danfe`) | **POR-ITEM** (`nfe_id`) | `require_permission("fiscal:nfe:emitir")` | `financial/controllers/fiscal_controller.py:557` |
| **Emitir NF-e produto (mod.55) SEFAZ-AM** — gera+assina XML 4.00 | POST `/api/v1/fiscal/nfe/emitir` | XML assinado (persiste em `nfes`) | POR-TELA (payload) → cria item | `CurrentActiveUser` + `_FISCAL_GATE` | `fiscal_contabil/notas_fiscais/nfe/controller.py:518` |
| Listar NF-e emitidas | GET `/api/v1/fiscal/nfe/listar` | JSON | POR-TELA | `_FISCAL_GATE` | `fiscal_contabil/notas_fiscais/nfe/controller.py:737` |
| Emitir NFS-e 🟡fiscal | POST `/api/v1/financial/fiscal/nfse/emitir` | JSON | POR-ITEM | `_FISCAL_GATE` | `financial/controllers/fiscal_controller.py:848` |
| Preparar NFS-e multi-empresa | POST `/api/v1/fiscal/nfse-multi/...` | JSON | POR-TELA | `get_current_user` | `fiscal/controllers/nfse_multi_controller.py:54` |
| **Gerar SPED** ⚠️STUB (`TODO`, só cria registro `status=gerando`) 🟡gov | POST `/api/v1/financial/fiscal/sped/gerar` | JSON (sem arquivo ainda) | POR-TELA | `require_permission("fiscal:sped:gerar")` | `financial/controllers/fiscal_controller.py:1076` |
| SPED validar/transmitir ⚠️STUB | POST `/api/v1/financial/fiscal/sped/{id}/{validar,transmitir}` | JSON | POR-ITEM | `require_permission fiscal:sped:*` | `financial/controllers/fiscal_controller.py:1110,1129` |
| **Preparar pagamento de guia (gate OTP)** 🔴dinheiro-que-sai | POST `/api/v1/fiscal/guias-drive/{obligacao_id}/preparar-pagamento` | JSON (status=preparado, NÃO move dinheiro; saída só após gerar-otp→aprovar OTP→executar em `/financeiro/inter/payments`) | POR-ITEM | `get_current_user` + `_FISCAL_GATE` + **OTP humano** | `fiscal_contabil/obrigacoes/guias_drive_controller.py:93` |

---

## D) STUBS / DEPRECATED / NÃO MONTADOS EM PRODUÇÃO (cuidado — não ligar botão sem verificar)

| Item | Path | Situação | Arquivo:linha |
|---|---|---|---|
| Report exports (cria export + download por token) | `/api/v1/reports/exports`, `/exports/download/{token}` | Mounted (`report_router`, main_production.py:978) mas **retorna metadata/URL** (`download_url` string, ex. `/files/{path}`), **não faz stream do arquivo**; módulo `reports` marcado DEPRECATED | `reports/controllers/report_controller.py:274,320` |
| Intelligent Reports — gerar/exportar | `/api/v1/intelligent/generate/*`, `/export/{report_id}` | **NÃO montado em produção** (0 includes de `intelligent_reports_controller`); `export_report` retorna metadata SIMULADA (`download_url` fake, `file_size:"1.2 MB"`) | `reports/controllers/intelligent_reports_controller.py:28,285` |
| Executive Dashboard export | GET `/api/v1/analytics/executive/export?format_type=json\|csv` | Mounted (main_production.py:976) mas retorna **JSON com `data` embutido**, não é stream de CSV/arquivo; **sem gate de módulo explícito** | `analytics/controllers/executive_dashboard_controller.py:238` |
| Predictive Analytics | `/api/v1/analytics/*` | Mounted (`analytics_router`, :977); sem geradores de arquivo | `analytics/controllers/predictive_analytics_controller.py:27` |

---

## E) SEM ROTA HTTP (geradores internos — chamados por rotas ou tasks)

| Gerador | Papel | Arquivo:linha |
|---|---|---|
| `gerar_relatorio_pdf(titulo, subtitulo, secoes)` | Gerador PDF reportlab compartilhado (DRE/Balancete/Fluxo/Aging) | `financial/services/relatorio_financeiro_pdf.py:30` |
| `gerar_danfse_de_nfse` / `gerar_danfse_pdf` | Gera DANFSe PDF (fora do path de escopo; invocado por A6/A7) | `modules/gedeon/services/nfse_danfse_generator.py` |
| Serviços de cálculo (DRE, balanço, fluxo, custeio) — só dados, sem render | `dre_service.py`, `balance_sheet_service.py`, `fluxo_caixa_service.py`, `cost_by_type_service.py`, `apuracao_lucro_real_service.py` | `financial/services/` |
| Sync/geração de guias do Drive (task) | Baixa+classifica PDFs de guias → `fiscal_obligations` | `fiscal_contabil/obrigacoes/guias_drive_service.py`, `tasks.py` |

---

## F) RE-EXPORTADOS por `fiscal_contabil/__init__.py` mas com código FORA do path de escopo (`modules/empresas`, `modules/ged`) — relevantes p/ a missão, checar em varredura vizinha

| Documento | Método + Path | Formato | Arquivo:linha |
|---|---|---|---|
| **Domínio/TOTVS — plano de contas (export p/ contador)** | GET `/api/v1/empresas/dominio/download/plano-contas/{empresa_slug}` | **TXT** (`PlainTextResponse`, `attachment`) | `modules/empresas/controllers/dominio_controller.py:63` |
| Domínio — lançamentos/clientes/nfse (gera arquivos import) | POST `/api/v1/empresas/dominio/{lancamentos,clientes,nfse}` | JSON/arquivo | `modules/empresas/controllers/dominio_controller.py:48,53,58` |
| Demonstrativos — DRE / Balanço / DFC / Consolidado grupo | POST `/api/v1/empresas/demonstrativos/{dre,balanco,dfc,consolidado-grupo}` | JSON | `modules/empresas/controllers/statements_controller.py:40,45,50,55` |
| Escrituração contábil — lançamentos folha/impostos, resumo mensal | POST `/api/v1/empresas/contabilidade/{lancamentos/folha,lancamentos/impostos,resumo-mensal}` | JSON | `modules/empresas/controllers/bookkeeper_controller.py:38,43,48` |
| NFS-e Faturamento (emissão prestador) | `/api/v1/financial/...` (`nfse_router`, main_production.py:691) | — | `modules/ged/controllers/nfse_controller.py` |

*(Fora do escopo textual; mounted em produção. A missão de "docs clicáveis+PDF" idealmente cobre o export Domínio TXT e os demonstrativos.)*

---

## RESUMO EXECUTIVO

- **Total de endpoints geradores/relatores inventariados:** ~50 rotas relevantes.
- **Documentos com ARQUIVO real hoje (botão HTML+PDF plug-and-play):** **8** (5 PDF de relatório via reportlab: DRE, Balancete, Fluxo, Aging×2 + 3 documentos fiscais: 2 DANFSe + 1 guia PDF do Drive). Todos com `media_type=application/pdf` (7) e 1 `FileResponse`.
- **Emissão fiscal que gera XML/documento gov:** 5 (NF-e ×2, NFS-e ×2, SPED-stub) + preparar-pagamento (OTP).
- **Relatórios em JSON sem arquivo (candidatos a ganhar o botão):** ~25 (bloco B) — a maioria já tem "gêmeo" JSON dos PDFs existentes; o padrão do redesign é criar rota `/pdf` reusando `gerar_relatorio_pdf`.
- **Por-ITEM (id na URL):** 5 diretos — DANFSe emitida (`nfse_id`), DANFSe recebida (`chave`), guia PDF (`obligacao_id`), emitir/validar NF-e/SPED (`nfe_id`/`sped_id`), preparar-pagamento guia (`obligacao_id`). **Por-TELA (agregado):** todo o bloco A de relatórios (ano/mês/competência) + bloco B.
- **Gated:** praticamente TUDO. `_FIN_GATE` (module:financeiro = só Jordan) cobre relatórios/aging/DAS-via-financial; `_FISCAL_GATE` (module:fiscal = Jordan+Pyetra) cobre DANFSe emitida, guias, NF-e/SPED, consultor fiscal; `require_permission("fiscal:nfe:emitir"/"sped:gerar")` em emissões; **OTP humano** obrigatório no `preparar-pagamento` de guia (dinheiro-que-sai 🔴). Exceção sem gate: `analytics/executive/export` e `reports/*` (deprecated).
- **Sensíveis gov/fiscal/legal:** DANFSe (×2), guia fiscal PDF, emitir NF-e/NFS-e, SPED, DAS/retenções, apuração lucro real, preparar-pagamento (dinheiro que sai).
- **Armadilhas de produção:** (1) `intelligent_reports_controller` **não está montado** em `main_production` — export lá é simulado, não ligar. (2) `reports/exports` e `executive/export` retornam **metadata/JSON, não stream de arquivo**. (3) SPED gerar é **STUB (TODO)**. (4) Geradores reais de DANFSe/PDF-relatório vivem **fora do path de escopo** (`gedeon`, `crm.pdf_branding`), mas são o ponto único de mudança de marca.
