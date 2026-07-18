"""Guard Multi-CNPJ: proibe CNPJ hardcoded NOVO no backend (E7).

Molde: tests/financial_release/test_money_guardrail.py. A identidade das
empresas vem da tabela empresas (helpers: empresa_lookup, empresa_context,
EMPRESAS_CONFIG, contexto_grupo) -- NUNCA de literal novo no codigo.

Baseline congelada em 2026-07-18 (arquivos legados, em reducao gradual).
Regra: arquivo FORA da baseline contendo 35710481000103 / 35.710.481 (ou o
CNPJ da Patrimonial 66014833000110 / 66.014.833) = FALHA. Arquivo da baseline
que ficou limpo = aviso para encolher a lista (remova-o daqui).

Rodar: python tests/multicnpj_release/test_cnpj_guardrail.py (ou via pytest).
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PADRAO = re.compile(r"35710481000103|35\.710\.481|66014833000110|66\.014\.833")
ALVOS = ["modules", "core", "main_production.py"]

BASELINE = {
    "core/config/settings.py",
    "modules/bidding/agents/assessor_agent.py",
    "modules/bidding/agents/compiler_agent.py",
    "modules/bidding/agents/orchestrator.py",
    "modules/bidding/agents/sentinel_agent.py",
    "modules/bidding/controllers/agent_controller.py",
    "modules/bidding/services/notification_service.py",
    "modules/bidding/tasks/notification_tasks.py",
    "modules/crm/services/pdf_branding.py",
    "modules/empresas/controllers/dashboard_controller.py",
    "modules/empresas/services/contexto_grupo.py",
    "modules/financial/agents/collection_negotiator.py",
    "modules/financial/agents/financial_advisor.py",
    "modules/financial/controllers/nfse_entrada_controller.py",
    "modules/financial/integrations/nfe_provider.py",
    "modules/financial/services/fiscal_dashboard_service.py",
    "modules/financial/services/ledger_auto_service.py",
    "modules/fiscal/services/nfse_multi_empresa_service.py",
    "modules/fiscal_contabil/notas_fiscais/nfe/controller.py",
    "modules/fiscal_contabil/notas_fiscais/nfe/entrada_controller.py",
    "modules/ged/controllers/kit_real_controller.py",
    "modules/gedeon/controllers/cnd_controller.py",
    "modules/gedeon/onvio/onvio_parser.py",
    "modules/gedeon/onvio/pdf_extractor/base.py",
    "modules/gedeon/onvio/pdf_extractor/inss_extractor.py",
    "modules/gedeon/services/cnd_kit_service.py",
    "modules/gedeon/services/comprovante_generator.py",
    "modules/gedeon/services/nfse_nacional_adn.py",
    "modules/gedeon/services/onvio_doc_scope_classifier.py",
    "modules/government_integrations/controllers/esocial_controller.py",
    "modules/government_integrations/controllers/nfce_controller.py",
    "modules/government_integrations/core/credentials/file_credential_provider.py",
    "modules/government_integrations/core/empresa_context.py",
    "modules/government_integrations/core/esocial_transmitter.py",
    "modules/government_integrations/services/ecac_service.py",
    "modules/government_integrations/services/esocial_espelho_service.py",
    "modules/government_integrations/services/nfe_entrada_sync_service.py",
    "modules/government_integrations/services/nfse_entrada_sync_service.py",
    "modules/government_integrations/services/nfse_manaus_service.py",
    "modules/government_integrations/services/nfse_nacional_service.py",
    "modules/government_integrations/services/simples_nacional_service.py",
    "modules/integrations/banking/adapters/inter.py",
    "modules/integrations/banking/controllers/banking_controller.py",
    "modules/integrations/banking/controllers/payment_controller.py",
    "modules/integrations/connectors/dominio/connector.py",
    "modules/juridico/consultor_service.py",
    "modules/juridico/det_service.py",
    "modules/juridico/riscos_service.py",
    "modules/operacional/disciplinary/services/disciplinary_service.py",
    "modules/people_management/ged/controllers/coleta_automatica_controller.py",
    "modules/people_management/ged/services/certidoes_updater_service.py",
    "modules/people_management/ged/services/coleta_automatica_service.py",
    "modules/people_management/ged/tasks/cnd_sync_task.py",
    "modules/people_management/hr/controllers/esocial_controller.py",
    "modules/people_management/hr/services/contract_service.py",
    "modules/people_management/hr/services/esocial_service.py",
    "modules/people_management/hr/services/payroll_export_service.py",
    "modules/people_management/sst/controllers/sst_controller.py",
    "modules/signatures/helpers/solicitar_assinatura_documento.py",
    "modules/signatures/services/qualified_signer.py",
    "modules/signatures/services/universal_signature_service.py"
}


def _varre():
    novos = []
    arquivos = []
    for alvo in ALVOS:
        p = RAIZ / alvo
        if p.is_file():
            arquivos.append(p)
        elif p.is_dir():
            arquivos.extend(p.rglob("*.py"))
    encontrados = set()
    for f in arquivos:
        if "__pycache__" in str(f):
            continue
        rel = str(f.relative_to(RAIZ))
        try:
            texto = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if PADRAO.search(texto):
            encontrados.add(rel)
            if rel not in BASELINE:
                novos.append(rel)
    limpos = sorted(BASELINE - encontrados)
    return novos, limpos


def test_sem_cnpj_hardcoded_novo():
    novos, limpos = _varre()
    assert not novos, (
        "CNPJ hardcoded NOVO (use a tabela empresas via empresa_lookup/"
        "empresa_context/EMPRESAS_CONFIG/contexto_grupo): " + repr(novos)
    )
    if limpos:
        print("[guard] arquivos da baseline ficaram limpos -- encolha a lista: "
              + repr(limpos[:8]))


if __name__ == "__main__":
    test_sem_cnpj_hardcoded_novo()
    print("GUARD_CNPJ_OK")
