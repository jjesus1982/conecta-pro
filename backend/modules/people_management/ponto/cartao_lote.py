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
from datetime import date

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


def candidatos(
    db,
    condominio_id: str | None,
    funcao: str | None,
    incluir_demitidos: bool,
    employee_ids: list[str] | None = None,
) -> list[tuple[str, str]]:
    """(id, nome) de quem entra no lote pelos filtros — antes de olhar se tem espelho.

    28/09/2026 — `employee_ids` (a seleção da tela) existe porque este era o único lugar que
    decidia "quem entra no lote" e ele ignorava escolha nenhuma: a tela em lote mandava
    competência + condomínio + função e o PDF saía com TODOS os candidatos — medido: 53
    espelhos, 14.283.110 bytes, 23,0 s, sempre os mesmos 53. Filtro aqui, e não no chamador,
    porque `montar_cartao_lote` já recebe a lista pronta e este é o choke point de todos os
    chamadores. Seleção é INTERSEÇÃO com os outros filtros (quem foi escolhido mas não passa
    pelo condomínio/função NÃO entra) e lista vazia devolve lista vazia — cabe ao chamador
    dizer isso, nunca cair de volta para todos.
    """
    rows = db.execute(
        text(_SQL_CANDIDATOS),
        {"cond": condominio_id or None, "funcao": (funcao or "").strip() or None, "demitidos": bool(incluir_demitidos)},
    ).all()
    if employee_ids is None:
        return [(r[0], r[1]) for r in rows]
    alvo = {str(x).strip() for x in employee_ids if str(x).strip()}
    return [(r[0], r[1]) for r in rows if r[0] in alvo]


def montar_cartao_lote(
    db,
    mes: int,
    ano: int,
    employee_ids: list[str],
    *,
    apenas_com_ponto: bool = False,
    detalhes: bool = True,
    de: date | None = None,
    ate: date | None = None,
) -> tuple[bytes | None, list[dict]]:
    """(pdf_concatenado | None, relato por pessoa). Uma entrada no relato por id pedido:
    {employee_id, nome, paginas | motivo}.

    28/09/2026 (Pyetra: «não consigo colocar data de início e fim das folhas de ponto quando vou
    verificar os pontos ou emitir elas todas») — `de`/`ate` imprimem o PERÍODO em vez do mês civil.
    A janela dela é 26/07→25/08, que não é mês nenhum: sem isto o lote só sabia emitir 01→31.
    Delega em `espelho_do_periodo` (o mesmo choke point do espelho individual e a mesma marca
    `periodo_kit` que faz o PDF rotular os totais como do MÊS CIVIL) — o lote não ganha régua
    própria de apuração nem de janela, senão seriam duas verdades para a mesma folha.
    """
    from PyPDF2 import PdfMerger, PdfReader

    from modules.people_management.hr.services.espelho_ponto_pdf import montar_espelho_ponto_pdf
    from modules.people_management.hr.services.espelho_ponto_service import ler_espelho
    from modules.people_management.ponto.dias_corridos import espelho_do_periodo

    periodo = f"{de:%d/%m/%Y} a {ate:%d/%m/%Y}" if de and ate else None
    merger = PdfMerger()
    relato: list[dict] = []
    n = 0
    for eid in employee_ids:
        esp = (
            espelho_do_periodo(db, str(eid), de, ate)
            if periodo
            else ler_espelho(db, str(eid), int(mes), int(ano))
        )
        if not esp:
            relato.append(
                {
                    "employee_id": str(eid),
                    "nome": None,
                    "motivo": f"sem espelho calculado em {mes:02d}/{ano}"
                    + (f" (competência do fim do período {periodo})" if periodo else ""),
                }
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
