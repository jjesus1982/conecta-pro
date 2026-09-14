#!/usr/bin/env python3
"""Cada CNPJ do grupo emite NFS-e com o SEU certificado, o SEU CNPJ e a SUA IM.

Origem (13/09/2026): a Patrimonial — que é quem presta vigilância, portaria e limpeza —
não conseguia emitir nota nenhuma pelo Conecta PRO. Quatro defeitos empilhados:

  1. `get_nfse_nacional_service()` era um singleton SEM empresa: toda emissão saía
     com o CNPJ e o certificado da Eletrônica, qualquer que fosse o pedido.
  2. `_build_dps_xml` caía num valor fixo `"45177801"` quando a IM vinha vazia — a
     inscrição municipal DA ELETRÔNICA. Outra empresa emitiria com a IM alheia.
  3. O campo `cTribNac` levava um código NBS (`1.1701.10.00`). O fisco respondia
     E0310 «o código de tributação nacional informado não existe» em TODA emissão —
     inclusive da Eletrônica. NBS e cTribNac são listas diferentes.
  4. Empresa do Simples sem `regApTribSN` => E0166.

Este oráculo afirma a REGRA, sem rede: quem assina é quem emite. Uma nota da
Patrimonial assinada pela Eletrônica é pior do que nota nenhuma — e era o estado
em que uma troca de `empresa_slug` deixava o sistema.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/orq/test_nfse_identidade_fiscal.py

Linha canônica: `TOTAL: <n> divergência(s) de identidade fiscal`. Exit 1 se houver.
"""

from __future__ import annotations

import re
import sys

#: Empresas que emitem NFS-e e o CNPJ que cada uma DEVE usar. Não é configuração:
#: é o fato que o oráculo defende. CNPJ novo no grupo entra aqui de propósito.
EMPRESAS = {
    "conecta_patrimonial": "66014833000110",
    "conecta_eletronica": "35710481000103",
}


def _so_digitos(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def main() -> int:
    from modules.government_integrations.core.nfse_nacional import (  # noqa: PLC0415
        CTRIBNAC_PADRAO,
        ctribnac_de_lc116,
    )
    from modules.government_integrations.services.nfse_nacional_service import (  # noqa: PLC0415
        CertificadoDeOutraEmpresaError,
        get_nfse_nacional_service,
        resolver_empresa_slug,
    )

    falhas: list[str] = []

    # 1. cTribNac vem da LC 116 (Item+Subitem+Desdobro), nunca do NBS.
    if ctribnac_de_lc116("11.02") != "110201" or ctribnac_de_lc116("7.10") != "071001":
        falhas.append("ctribnac_de_lc116 não deriva o código do item da LC 116")
    if not re.fullmatch(r"\d{6}", CTRIBNAC_PADRAO):
        falhas.append(f"CTRIBNAC_PADRAO={CTRIBNAC_PADRAO!r} não tem os 6 dígitos do cTribNac")

    ims = {}
    for slug, cnpj_esperado in EMPRESAS.items():
        try:
            svc = get_nfse_nacional_service(slug)
        except Exception as e:  # noqa: BLE001
            falhas.append(f"{slug}: service não inicializa — {type(e).__name__}: {e}")
            continue

        # 2. O CNPJ da empresa é o que ela diz ser.
        if _so_digitos(svc.cnpj) != cnpj_esperado:
            falhas.append(f"{slug}: emitiria com CNPJ {svc.cnpj}, esperado {cnpj_esperado}")

        # 3. O certificado que assina é o DESSA empresa (a trava roda no _get_manager).
        try:
            svc._get_manager()
        except CertificadoDeOutraEmpresaError as e:
            falhas.append(f"{slug}: {e}")
            continue
        cert = getattr(svc, "_cert_manager", None)
        if cert is None:
            falhas.append(f"{slug}: sem certificado carregado — não assina nota nenhuma")
        elif _so_digitos(cert.info.subject_cpf_cnpj) != cnpj_esperado:
            falhas.append(f"{slug}: certificado é do CNPJ {cert.info.subject_cpf_cnpj}, não de {cnpj_esperado}")

        ims[slug] = _so_digitos(svc.inscricao_municipal)

        # 4. O XML carrega o CNPJ certo — e nenhuma IM de outra empresa.
        r = svc.emitir_dps(
            tomador_data={"cpf_cnpj": "00000000000191", "razao_social": "TESTE"},
            servico_data={"descricao": "oraculo", "valor_servico": 1},
            dry_run=True,
        )
        xml = r.get("xml_preview") or ""
        if f"<CNPJ>{cnpj_esperado}</CNPJ>" not in xml:
            falhas.append(f"{slug}: o XML não traz <CNPJ>{cnpj_esperado}</CNPJ>")

    # 5. A IM de uma empresa nunca pode aparecer no XML da outra (era o fallback fixo).
    for slug in EMPRESAS:
        svc = get_nfse_nacional_service(slug)
        xml = (
            svc.emitir_dps(
                tomador_data={"cpf_cnpj": "00000000000191", "razao_social": "TESTE"},
                servico_data={"descricao": "oraculo", "valor_servico": 1},
                dry_run=True,
            ).get("xml_preview")
            or ""
        )
        for outro, im_alheia in ims.items():
            if outro != slug and im_alheia and f"<IM>{im_alheia}</IM>" in xml:
                falhas.append(f"{slug}: o XML leva a IM {im_alheia}, que é de {outro}")

    # 6. A trava recusa reescrever o CNPJ do prestador por fora da empresa.
    try:
        get_nfse_nacional_service("conecta_patrimonial").emitir_dps(
            tomador_data={"cpf_cnpj": "00000000000191", "razao_social": "TESTE"},
            servico_data={"descricao": "oraculo", "valor_servico": 1},
            prestador_data={"cnpj": EMPRESAS["conecta_eletronica"]},
            dry_run=True,
        )
        falhas.append("prestador.cnpj de outra empresa passou — a trava de identidade caiu")
    except CertificadoDeOutraEmpresaError:
        pass

    # 7. Apelidos continuam resolvendo (a tela e a API mandam 'patrimonial').
    for apelido, esperado in (
        ("patrimonial", "conecta_patrimonial"),
        ("66.014.833/0001-10", "conecta_patrimonial"),
        ("eletronica", "conecta_eletronica"),
    ):
        if resolver_empresa_slug(apelido) != esperado:
            falhas.append(f"apelido {apelido!r} não resolve para {esperado}")

    for f in falhas:
        print(f"   ✗ {f}")
    if not falhas:
        for slug, cnpj in EMPRESAS.items():
            svc = get_nfse_nacional_service(slug)
            print(f"   ✓ {slug}: CNPJ {cnpj}, certificado {svc._cert_manager.info.subject_cn}")
    print(f"\nTOTAL: {len(falhas)} divergência(s) de identidade fiscal")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
