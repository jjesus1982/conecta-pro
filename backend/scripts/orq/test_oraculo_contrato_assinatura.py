"""Oráculo: o contrato NÃO mente sobre a própria assinatura.

Guarda dois defeitos reais, achados em 21/08/2026:

1. O fecho do instrumento dispensa testemunhas invocando o art. 784, § 4º do CPC, "uma vez
   que a integridade deste documento é conferida pelo provedor de assinatura, CONFORME
   MANIFESTO AO FINAL" — e não havia manifesto nenhum. O contrato afirmava sobre si mesmo
   algo falso, e era justamente essa afirmação que sustentava a dispensa da testemunha.

2. O bloco de assinatura precisa refletir o BANCO, nunca uma foto. Se ninguém assinou, ele
   diz "Aguardando"; se alguém assinou, ele carimba o nome de quem assinou. Um bloco que
   carimba nome sem linha em `sig_signature_requests` é fabricação de documento.

Afirma a REGRA, não a fotografia: vale para qualquer contrato renderizável, em qualquer
estado de assinatura. É READ-ONLY — não abre solicitação nem assina nada.

Roda no container.
"""
import asyncio
import re

from sqlalchemy import text

from core.database import async_session_factory
from modules.crm.services.contract_render import RenderError, renderizar_contrato

CASO = "CTR-2026-00019"


def _texto_do_pdf(pdf: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    import io
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)


async def _checar(db, numero: str) -> str:
    res = await renderizar_contrato(db, numero)
    pdf_txt = _texto_do_pdf(res.pdf)

    # 1 · promessa cumprida
    if re.search(r"manifesto ao final", res.texto, re.I):
        assert "MANIFESTO DE ASSINATURAS" in pdf_txt, (
            f"{numero}: o contrato promete 'manifesto ao final' e o PDF não tem a página de "
            "manifesto. O instrumento dispensa testemunha com base nessa promessa — sem a "
            "página, a dispensa fica sem lastro.")

    # 2 · exibido == banco
    assinados = (await db.execute(text(
        "SELECT signer_name FROM sig_signature_requests "
        "WHERE reference_code = :k AND signed_at IS NOT NULL"), {"k": numero})).scalars().all()

    for nome in assinados:
        primeiro = (nome or "").split()[0] if nome else ""
        assert primeiro and f"Assinado eletronicamente por {nome}" in pdf_txt, (
            f"{numero}: {nome} consta assinado no banco e o PDF não carimba a assinatura dele "
            "— o documento entregue esconde uma assinatura que existe.")

    if not assinados:
        assert "Aguardando assinatura" in pdf_txt, (
            f"{numero}: ninguém assinou no banco, mas o PDF não diz 'Aguardando assinatura'. "
            "Um contrato sem assinatura que não se declara pendente é documento fabricado.")
        # e não pode carimbar ninguém
        assert "Assinado eletronicamente por" not in pdf_txt, (
            f"{numero}: o PDF carimba 'Assinado eletronicamente' sem NENHUMA assinatura em "
            "sig_signature_requests — isso é fabricação de assinatura.")

    return (f"{numero}: {len(assinados)} assinatura(s) no banco, "
            f"{'com' if 'MANIFESTO DE ASSINATURAS' in pdf_txt else 'sem'} manifesto, "
            f"PDF {len(res.pdf) // 1024} KB")


async def main() -> None:
    async with async_session_factory() as db:
        print("OK 1 ·", await _checar(db, CASO))

        # a regra vale além do caso
        outros = (await db.execute(text(
            "SELECT contract_number FROM contracts WHERE template_id IS NOT NULL "
            "AND coalesce(is_active, true) AND contract_number <> :c LIMIT 5"),
            {"c": CASO})).scalars().all()
        feitos = 0
        for num in outros:
            try:
                await _checar(db, num)
            except RenderError:
                continue  # recusa por dado incompleto é comportamento CERTO
            feitos += 1
        print(f"OK 2 · a regra vale além do caso: {feitos} outro(s) contrato(s) conferido(s) "
              f"({len(outros) - feitos} recusado(s) por dado incompleto)")


if __name__ == "__main__":
    asyncio.run(main())
