"""GEDEON — Faturamento do kit: emitir NFS-e e/ou boleto direto do condomínio.

Resolve condomínio → cliente (clients) + valor (contracts.monthly_value / clients.mrr) e
monta o faturamento do mês do KIT (competência+1). Por SEGURANÇA emite SÓ com confirmar=True;
sem confirmar devolve um PREVIEW (o que SERIA emitido), pra revisão antes de criar nota/cobrança REAL.

Reaproveita os emissores nativos: NFS-e Manaus (nfse_manaus_service) e Inter (cobranca_service).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text

CODIGO_SERVICO_VIGILANCIA = "11.02"  # LC 116 — vigilância, segurança e monitoramento


def _mes_kit(competencia: str) -> tuple[int, int]:
    m, a = int(competencia.split(".")[0]), int(competencia.split(".")[1])
    return (a, m + 1) if m < 12 else (a + 1, 1)


def _dados_faturamento(db, condominio: str) -> dict:
    from modules.gedeon.services.kit_ficha_service import _client_id_do_condominio

    cid = _client_id_do_condominio(db, condominio)
    if not cid:
        raise ValueError(f"condomínio '{condominio}' não casou com nenhum cliente (clients)")
    row = db.execute(
        text(
            """SELECT name, document_number, address_street, address_number, address_complement,
                      address_neighborhood, address_city, address_state, address_zipcode,
                      email, phone, municipal_registration, mrr, billing_day, pix_key
               FROM clients WHERE id = :cid"""
        ),
        {"cid": cid},
    ).mappings().first()
    valor = db.execute(
        text("SELECT monthly_value FROM contracts WHERE client_id = :cid AND status = 'active' ORDER BY monthly_value DESC LIMIT 1"),
        {"cid": cid},
    ).scalar()
    valor = Decimal(str(valor)) if valor else (Decimal(str(row["mrr"])) if row and row["mrr"] else None)
    return {"client_id": str(cid), "cliente": dict(row) if row else {}, "valor": valor}


def montar_preview(competencia: str, condominio: str, optante_simples: bool = False) -> dict:
    """Monta o que SERIA emitido (NFS-e + boleto) sem emitir nada."""
    from core.database.session import get_sync_db

    ka, km = _mes_kit(competencia)
    comp_nfse = f"{ka}-{km:02d}"
    with get_sync_db() as db:
        d = _dados_faturamento(db, condominio)
    cli = d["cliente"]
    valor = d["valor"]
    if not valor or valor <= 0:
        raise ValueError(f"sem valor de contrato/MRR para '{condominio}' — cadastre o contrato antes de faturar")
    discr = f"Prestação de serviços de segurança/portaria — competência {km:02d}/{ka} ({condominio})"
    billing_day = cli.get("billing_day") or 10
    venc = date(ka, km, min(int(billing_day), 28))
    nfse = {
        "tomador": {
            "cpf_cnpj": (cli.get("document_number") or "").replace(".", "").replace("/", "").replace("-", ""),
            "razao_social": cli.get("name"),
            "endereco": cli.get("address_street") or "S/N",
            "numero": cli.get("address_number") or "S/N",
            "bairro": cli.get("address_neighborhood") or "Centro",
            "cidade": cli.get("address_city") or "Manaus",
            "uf": cli.get("address_state") or "AM",
            "cep": (cli.get("address_zipcode") or "69000000").replace("-", ""),
            "email": cli.get("email"),
            "inscricao_municipal": cli.get("municipal_registration"),
        },
        "servico": {
            "codigo_servico": CODIGO_SERVICO_VIGILANCIA,
            "discriminacao": discr,
            "valor_servicos": float(valor),
            "aliquota_iss": 0.05,
        },
        "competencia": comp_nfse,
        "optante_simples": optante_simples,
    }
    boleto = {
        "cliente_crm_id": d["client_id"],
        "valor": float(valor),
        "vencimento": venc.isoformat(),
        "descricao": discr,
        "pagador": {
            "nome": cli.get("name"),
            "cpfCnpj": nfse["tomador"]["cpf_cnpj"],
            "email": cli.get("email"),
        },
    }
    return {
        "condominio": condominio,
        "competencia": competencia,
        "mes_emissao": comp_nfse,
        "valor": float(valor),
        "nfse": nfse,
        "boleto": boleto,
        "aviso": "PREVIEW — nada foi emitido. Use confirmar=true p/ emitir nota/cobrança REAL.",
    }


async def emitir_faturamento(
    competencia: str, condominio: str, tipo: str = "ambos", confirmar: bool = False, optante_simples: bool = False
) -> dict:
    """tipo: nfse | boleto | ambos. confirmar=False → só preview (não emite nada)."""
    prev = montar_preview(competencia, condominio, optante_simples=optante_simples)
    if not confirmar:
        return {"emitido": False, **prev}

    resultado: dict = {"emitido": True, "condominio": condominio, "competencia": competencia, "nfse": None, "boleto": None}
    if tipo in ("nfse", "ambos"):
        from modules.government_integrations.services.nfse_manaus_service import NFSeManausService

        svc = NFSeManausService()
        resultado["nfse"] = svc.emitir_nfse(
            tomador_data=prev["nfse"]["tomador"],
            servico_data={
                "codigo_servico": prev["nfse"]["servico"]["codigo_servico"],
                "discriminacao": prev["nfse"]["servico"]["discriminacao"],
                "valor_servicos": prev["nfse"]["servico"]["valor_servicos"],
                "aliquota_iss": prev["nfse"]["servico"]["aliquota_iss"],
            },
            competencia=prev["nfse"]["competencia"],
            optante_simples=optante_simples,
        )
    if tipo in ("boleto", "ambos"):
        from core.database.session import get_async_db_session
        from modules.integrations.inter.cobranca_service import CobrancaService

        async with get_async_db_session() as db:
            cs = CobrancaService(db)
            resultado["boleto"] = await cs.emitir(
                cliente_crm_id=prev["boleto"]["cliente_crm_id"],
                valor=prev["boleto"]["valor"],
                vencimento=date.fromisoformat(prev["boleto"]["vencimento"]),
                descricao=prev["boleto"]["descricao"],
                pagador=prev["boleto"]["pagador"],
            )
    return resultado
