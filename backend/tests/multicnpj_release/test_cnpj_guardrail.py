"""Guard Multi-CNPJ: proibe CNPJ hardcoded NOVO no backend (E7).

Molde: tests/financial_release/test_money_guardrail.py. A identidade das
empresas vem da tabela empresas (helpers: empresa_lookup, empresa_context,
EMPRESAS_CONFIG, contexto_grupo) -- NUNCA de literal novo no codigo.

Baseline por CONTAGEM congelada em 2026-07-20 (arquivos legados, em reducao
gradual). Diferente de uma allowlist binaria por arquivo (que deixava um arquivo
ja listado ganhar um CNPJ hardcoded NOVO sem o guard perceber — furo real da
auditoria 2026-07-20/B1), aqui cada arquivo tem um TETO de matches:

  Regra: arquivo FORA da baseline com qualquer match = FALHA.
         arquivo da baseline cujo numero de matches AUMENTOU = FALHA.
         arquivo cujo numero DIMINUIU (ou zerou) = aviso para baixar o teto.

Isso pega tanto o CNPJ hardcoded em arquivo novo quanto o hardcoded NOVO
enfiado num arquivo que ja estava na lista. `financial_mcp_server.py` (raiz do
repo) entra nos ALVOS — antes ficava fora da varredura.

Rodar: python tests/multicnpj_release/test_cnpj_guardrail.py (ou via pytest).
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PADRAO = re.compile(r"35710481000103|35\.710\.481|66014833000110|66\.014\.833")
ALVOS = ["modules", "core", "main_production.py", "financial_mcp_server.py"]

# Teto de matches por arquivo (baseline 2026-07-20). Reduzir sempre que um
# arquivo for higienizado — o teste avisa quando um teto ficou folgado.
BASELINE_COUNTS = {
    "core/config/settings.py": 1,
    "modules/bidding/agents/assessor_agent.py": 1,
    "modules/bidding/agents/compiler_agent.py": 2,
    "modules/bidding/agents/orchestrator.py": 2,
    "modules/bidding/agents/sentinel_agent.py": 2,
    "modules/bidding/controllers/agent_controller.py": 2,
    "modules/bidding/services/notification_service.py": 1,
    "modules/bidding/tasks/notification_tasks.py": 2,
    "modules/crm/services/pdf_branding.py": 2,
    "modules/empresas/services/contexto_grupo.py": 2,
    "modules/financial/agents/collection_negotiator.py": 2,
    "modules/financial/controllers/nfse_entrada_controller.py": 3,
    "modules/financial/integrations/nfe_provider.py": 1,
    "modules/financial/services/fiscal_dashboard_service.py": 1,
    "modules/financial/services/ledger_auto_service.py": 2,
    "modules/fiscal/services/nfse_multi_empresa_service.py": 2,
    "modules/fiscal_contabil/notas_fiscais/nfe/controller.py": 2,
    "modules/fiscal_contabil/notas_fiscais/nfe/entrada_controller.py": 1,
    "modules/ged/controllers/kit_real_controller.py": 1,
    "modules/gedeon/controllers/cnd_controller.py": 1,
    "modules/gedeon/onvio/onvio_parser.py": 6,
    "modules/gedeon/onvio/pdf_extractor/base.py": 2,
    "modules/gedeon/onvio/pdf_extractor/inss_extractor.py": 1,
    "modules/gedeon/services/cnd_kit_service.py": 1,
    "modules/gedeon/services/comprovante_generator.py": 1,
    "modules/gedeon/services/nfse_nacional_adn.py": 1,
    "modules/gedeon/services/onvio_doc_scope_classifier.py": 5,
    "modules/government_integrations/controllers/esocial_controller.py": 1,
    "modules/government_integrations/controllers/nfce_controller.py": 2,
    "modules/government_integrations/core/credentials/file_credential_provider.py": 2,
    "modules/government_integrations/core/empresa_context.py": 2,
    "modules/government_integrations/core/esocial_transmitter.py": 2,
    "modules/government_integrations/services/ecac_service.py": 2,
    "modules/government_integrations/services/esocial_espelho_service.py": 2,
    "modules/government_integrations/services/nfe_entrada_sync_service.py": 1,
    "modules/government_integrations/services/nfse_entrada_sync_service.py": 2,
    "modules/government_integrations/services/nfse_manaus_service.py": 1,
    "modules/government_integrations/services/nfse_nacional_service.py": 1,
    "modules/government_integrations/services/simples_nacional_service.py": 1,
    "modules/integrations/banking/adapters/inter.py": 6,
    "modules/integrations/banking/controllers/banking_controller.py": 2,
    "modules/integrations/banking/controllers/payment_controller.py": 1,
    "modules/integrations/connectors/dominio/connector.py": 2,
    "modules/juridico/consultor_service.py": 1,
    "modules/juridico/det_service.py": 1,
    "modules/juridico/riscos_service.py": 1,
    "modules/operacional/disciplinary/services/disciplinary_service.py": 1,
    "modules/people_management/ged/controllers/coleta_automatica_controller.py": 1,
    "modules/people_management/ged/services/certidoes_updater_service.py": 1,
    "modules/people_management/ged/services/coleta_automatica_service.py": 1,
    "modules/people_management/ged/tasks/cnd_sync_task.py": 1,
    "modules/people_management/hr/controllers/esocial_controller.py": 1,
    "modules/people_management/hr/services/contract_service.py": 1,
    "modules/people_management/hr/services/esocial_service.py": 1,
    "modules/people_management/hr/services/payroll_export_service.py": 3,
    "modules/people_management/sst/controllers/sst_controller.py": 2,
    "modules/signatures/helpers/solicitar_assinatura_documento.py": 1,
    "modules/signatures/services/qualified_signer.py": 1,
    "modules/signatures/services/universal_signature_service.py": 2,
}


def _varre():
    """Retorna {rel: n_matches} para todo arquivo com >=1 match."""
    arquivos = []
    for alvo in ALVOS:
        p = RAIZ / alvo
        if p.is_file():
            arquivos.append(p)
        elif p.is_dir():
            arquivos.extend(p.rglob("*.py"))
    cont = {}
    for f in arquivos:
        if "__pycache__" in str(f):
            continue
        rel = str(f.relative_to(RAIZ))
        try:
            texto = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        n = len(PADRAO.findall(texto))
        if n:
            cont[rel] = n
    return cont


def test_sem_cnpj_hardcoded_novo():
    cont = _varre()
    violacoes = []
    for rel, n in sorted(cont.items()):
        teto = BASELINE_COUNTS.get(rel, 0)
        if n > teto:
            violacoes.append(f"{rel}: {n} matches (teto {teto})")
    assert not violacoes, (
        "CNPJ hardcoded NOVO (arquivo novo ou aumento num arquivo da baseline). "
        "Use a tabela empresas via empresa_lookup/empresa_context/EMPRESAS_CONFIG/"
        "contexto_grupo:\n  " + "\n  ".join(violacoes)
    )
    # Aviso (nao falha): tetos que ficaram folgados -> baixar a baseline.
    folgados = [
        f"{rel}: {cont.get(rel, 0)}/{teto}"
        for rel, teto in BASELINE_COUNTS.items()
        if cont.get(rel, 0) < teto
    ]
    if folgados:
        print("[guard] tetos folgados (baixe a baseline): " + repr(folgados[:8]))


if __name__ == "__main__":
    test_sem_cnpj_hardcoded_novo()
    print("GUARD_CNPJ_OK")
