"""Cartão de ponto em LOTE — um PDF com o espelho de cada colaborador da competência.

DGX F7 (24/09/2026). A DGX imprime "Cartão Ponto Lote" com filtros (vigência, contrato, apenas
com ponto, trazer demitidos, exibir detalhes). Aqui não se reescreve espelho nenhum: cada página
é `ler_espelho` + `montar_espelho_ponto_pdf` (o mesmo PDF padrão-ouro do botão individual e do
kit do GEDEON), e as páginas são concatenadas com PyPDF2 (já no requirements).

Sem `time_sheets` calculado = sem página (anti-fabricação, mesma regra do espelho individual e
da ferramenta do Hermes). O chamador recebe quem ficou de fora e por quê.

Síncrono de propósito: `ler_espelho` é Session sync; quem chama de rota async usa
`run_in_threadpool`.
"""

from __future__ import annotations

import io

from sqlalchemy import text

_SQL_CANDIDATOS = """
SELECT e.id::text, e.nome
  FROM employees e
 WHERE coalesce(e.is_homologacao, false) = false
   AND (lower(coalesce(e.status, '')) = 'ativo' OR (:demitidos AND lower(coalesce(e.status, '')) = 'demitido'))
   AND (:cond IS NULL OR e.cliente_id = (SELECT c.client_id FROM condominios c WHERE c.id::text = :cond))
   AND (:funcao IS NULL OR upper(coalesce(e.cargo, '')) = upper(:funcao))
 ORDER BY e.nome
"""


def candidatos(db, condominio_id: str | None, funcao: str | None, incluir_demitidos: bool) -> list[tuple[str, str]]:
    """(id, nome) de quem entra no lote pelos filtros — antes de olhar se tem espelho."""
    rows = db.execute(
        text(_SQL_CANDIDATOS),
        {"cond": condominio_id or None, "funcao": (funcao or "").strip() or None, "demitidos": bool(incluir_demitidos)},
    ).all()
    return [(r[0], r[1]) for r in rows]


def montar_cartao_lote(
    db, mes: int, ano: int, employee_ids: list[str], *, apenas_com_ponto: bool = False, detalhes: bool = True
) -> tuple[bytes | None, list[dict]]:
    """(pdf_concatenado | None, relato por pessoa). Uma entrada no relato por id pedido:
    {employee_id, nome, paginas | motivo}."""
    from PyPDF2 import PdfMerger, PdfReader

    from modules.people_management.hr.services.espelho_ponto_pdf import montar_espelho_ponto_pdf
    from modules.people_management.hr.services.espelho_ponto_service import ler_espelho

    merger = PdfMerger()
    relato: list[dict] = []
    n = 0
    for eid in employee_ids:
        esp = ler_espelho(db, str(eid), int(mes), int(ano))
        if not esp:
            relato.append(
                {"employee_id": str(eid), "nome": None, "motivo": f"sem espelho calculado em {mes:02d}/{ano}"}
            )
            continue
        if apenas_com_ponto and (esp.get("horas_trabalhadas") in (None, "", "00:00")):
            relato.append(
                {"employee_id": str(eid), "nome": esp["employee_name"], "motivo": "sem ponto no mês (apenas com ponto)"}
            )
            continue
        if not detalhes:
            esp = dict(esp, dias=[])  # só o cabeçalho e os totais — a tabela diária fica vazia
        pdf = montar_espelho_ponto_pdf(esp)
        paginas = len(PdfReader(io.BytesIO(pdf)).pages)
        merger.append(io.BytesIO(pdf))
        relato.append({"employee_id": str(eid), "nome": esp["employee_name"], "paginas": paginas})
        n += 1
    if not n:
        return None, relato
    out = io.BytesIO()
    merger.write(out)
    merger.close()
    return out.getvalue(), relato
