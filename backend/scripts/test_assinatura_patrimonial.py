# -*- coding: utf-8 -*-
"""Self-check: assinatura ICP-Brasil multi-CNPJ (Eletrônica × Patrimonial).

Prova que o assinador escolhe o certificado A1 CERTO por empresa_slug:
- empresa_slug='conecta_patrimonial' → cert titular 66.014.833/0001-10
- empresa_slug=None (default)        → cert titular 35.710.481/0001-03

Requer no ambiente: CERT_A1_PASSWORD (Eletrônica) e CERT_A1_PASSWORD_PATRIMONIAL.
Rodar: docker exec -e PYTHONPATH=/app conecta-pro-backend python /app/scripts/test_assinatura_patrimonial.py
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from modules.signatures.services.qualified_signer import assinar_pdf_icp_brasil


def _pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(100, 700, "Documento de teste — assinatura ICP-Brasil")
    c.showPage()
    c.save()
    return buf.getvalue()


def main() -> None:
    r_pat = assinar_pdf_icp_brasil(_pdf(), empresa_slug="conecta_patrimonial")
    assert "66014833000110" in r_pat.certificate_subject_cn, r_pat.certificate_subject_cn
    assert r_pat.signed_pdf and len(r_pat.signed_pdf) > 1000
    print("PATRIMONIAL OK  ->", r_pat.certificate_subject_cn, "| serial", r_pat.certificate_serial)

    r_ele = assinar_pdf_icp_brasil(_pdf(), empresa_slug=None)
    assert "35710481000103" in r_ele.certificate_subject_cn, r_ele.certificate_subject_cn
    print("ELETRONICA OK   ->", r_ele.certificate_subject_cn, "| serial", r_ele.certificate_serial)

    # cross-check: os dois usam certificados DIFERENTES
    assert r_pat.certificate_serial != r_ele.certificate_serial, "mesmo cert para as duas empresas!"
    print("SELF-CHECK VERDE — cada CNPJ assina com o seu certificado")


if __name__ == "__main__":
    main()
