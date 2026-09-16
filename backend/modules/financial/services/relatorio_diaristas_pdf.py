"""Relatório de diaristas em PAISAGEM, com tabela de verdade.

Existe separado do `relatorio_financeiro_pdf` porque aquele é rótulo→valor em retrato:
serve para demonstrativo (DRE, balancete), não para lista operacional. Um relatório de
pagamento é lido linha a linha, conferindo nome contra chave PIX contra valor — isso é
tabela, com cabeçalho fixo e coluna alinhada, não texto corrido.

Mantém a marca da empresa reusando `pdf_branding.marca_canvas`, que aceita `pagesize`.
"""

from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as _canvas

from modules.crm.services import pdf_branding as B  # noqa: N812

_AZUL = colors.HexColor("#16277D")
_LARANJA = colors.HexColor("#F26522")
_CINZA = colors.HexColor("#6B7280")
_ZEBRA = colors.HexColor("#F3F4F6")


def _cabe(c, texto: str, largura: float, fonte: str = "Helvetica", tam: float = 9) -> str:
    """Corta pela LARGURA real, não por contagem de caracteres.

    Contar caractere só funciona em fonte monoespaçada. Em Helvetica, 'EULER FELIPE
    FERNANDES DA COSTA' passou por cima da coluna vizinha com 31 caracteres enquanto
    'JONILSON MARTINS' sobrava espaço — a régua estava calibrada para 7,5pt e a fonte
    subiu para 9. Aqui quem decide é o próprio renderizador.
    """
    if c.stringWidth(texto, fonte, tam) <= largura:
        return texto
    while texto and c.stringWidth(texto + "…", fonte, tam) > largura:
        texto = texto[:-1]
    return texto + "…"


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _cpf_mascara(cpf: str | None) -> str:
    """000.000.000-00. Onze dígitos crus num documento de pagamento se confere errado —
    o olho perde a conta e troca um dígito de lugar."""
    d = "".join(ch for ch in str(cpf or "") if ch.isdigit())
    if len(d) != 11:
        return str(cpf or "")
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def gerar_tabela_pdf(
    *,
    titulo: str,
    subtitulo: str,
    colunas: list[dict],
    linhas: list[list],
    rodape: list[tuple[str, str]] | None = None,
    nota: str | None = None,
    empresa: dict | None = None,
    tam: float = 8,
) -> bytes:
    """`colunas` = [{'t': cabeçalho, 'w': largura mm, 'a': 'L'|'R'|'C'}].

    Quebra de página repete o cabeçalho — sem isso a segunda página vira número solto
    sem nome de coluna, que é como se confere errado.
    """
    buf = io.BytesIO()
    W, H = landscape(A4)
    c = _canvas.Canvas(buf, pagesize=landscape(A4))
    largura_total = sum(col["w"] for col in colunas) * mm
    # Centralizada: sobra igual dos dois lados. Tabela colada na margem esquerda com
    # espaco morto a direita parece rascunho, e o olho perde a coluna de valor.
    x0 = (W - largura_total) / 2
    pagina = [1]

    def cabecalho() -> float:
        y = B.marca_canvas(c, titulo=titulo.upper(), pagesize=landscape(A4), empresa=empresa)
        c.setFillColor(_AZUL)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x0, y, subtitulo[:150])
        y -= 7 * mm
        # faixa do cabeçalho da tabela
        c.setFillColor(_AZUL)
        c.rect(x0, y - 6 * mm, largura_total, 6 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", tam)
        x = x0
        for col in colunas:
            w = col["w"] * mm
            if col.get("a") == "R":
                c.drawRightString(x + w - 1.5 * mm, y - 4.3 * mm, col["t"])
            elif col.get("a") == "C":
                c.drawCentredString(x + w / 2, y - 4.3 * mm, col["t"])
            else:
                c.drawString(x + 1.5 * mm, y - 4.3 * mm, col["t"])
            x += w
        return y - 6 * mm

    y = cabecalho()
    c.setFont("Helvetica", tam)
    for i, linha in enumerate(linhas):
        if y < 30 * mm:
            B.rodape_canvas(c, pagesize=landscape(A4), pagina=pagina[0], empresa=empresa)
            c.showPage()
            pagina[0] += 1
            y = cabecalho()
            c.setFont("Helvetica", tam)
        if i % 2:
            c.setFillColor(_ZEBRA)
            c.rect(x0, y - 6 * mm, largura_total, 6 * mm, stroke=0, fill=1)
        c.setFillColor(colors.black)
        x = x0
        for col, val in zip(colunas, linha, strict=False):
            w = col["w"] * mm
            # O corte vale para TODA coluna, não só a da esquerda: ao centralizar a
            # chave PIX, um e-mail de 33 caracteres passava por cima das vizinhas dos
            # DOIS lados — e centralizado o estrago é simétrico, mais difícil de ver.
            s = _cabe(c, str(val), w - 3 * mm, tam=tam)
            if col.get("a") == "R":
                c.drawRightString(x + w - 1.5 * mm, y - 4.1 * mm, s)
            elif col.get("a") == "C":
                c.drawCentredString(x + w / 2, y - 4.1 * mm, s)
            else:
                c.drawString(x + 1.5 * mm, y - 4.1 * mm, s)
            x += w
        y -= 6 * mm

    # totalizador
    if rodape:
        y -= 2 * mm
        c.setStrokeColor(_AZUL)
        c.setLineWidth(0.8)
        c.line(x0, y, x0 + largura_total, y)
        y -= 6 * mm
        c.setFont("Helvetica-Bold", 10.5)
        for rot, val in rodape:
            c.setFillColor(_CINZA)
            c.drawString(x0 + 1.5 * mm, y, rot)
            c.setFillColor(_LARANJA)
            c.drawRightString(x0 + largura_total - 1.5 * mm, y, val)
            y -= 5.5 * mm
    if nota:
        y -= 2 * mm
        c.setFillColor(_CINZA)
        c.setFont("Helvetica-Oblique", 8)
        for pedaco in [nota[i : i + 170] for i in range(0, len(nota), 170)]:
            c.drawString(x0, y, pedaco)
            y -= 3.6 * mm

    B.rodape_canvas(c, pagesize=landscape(A4), pagina=pagina[0], empresa=empresa)
    c.save()
    return buf.getvalue()


def relatorio_diaristas(db, *, inicio: date, fim: date) -> tuple[bytes, dict]:
    """Lista de pagamento das diárias do período. Uma linha por diarista.

    `valor da diária` é a MÉDIA quando a pessoa trabalhou em turnos de preço diferente —
    por isso a coluna existe junto com o total, e não no lugar dele: mostrar só a média
    esconde que R$90 × 2 dias pode ser R$100 + R$80.
    """
    from sqlalchemy import text

    rs = (
        db.execute(
            text("""
        SELECT coalesce(d.nome, '(sem cadastro)') AS nome,
               coalesce(d.cpf, '') AS cpf,
               coalesce(nullif(d.pix, ''), '(SEM CHAVE PIX)') AS chave,
               count(*) AS dias,
               round(avg(l.valor), 2) AS media,
               min(l.valor) AS minimo, max(l.valor) AS maximo,
               sum(l.valor)::numeric(12, 2) AS total,
               -- Os DIAS em que a pessoa trabalhou, nao so quantos. E o que o Jordan
               -- confere contra a escala: "11 dias" nao se discute, "dia 3, 7 e 12" sim.
               string_agg(to_char(l.data, 'DD'), ',' ORDER BY l.data) AS dias_lista
          FROM diaria_lancamentos l
          LEFT JOIN diaria_diaristas d ON d.id = l.diarista_id
         WHERE l.data BETWEEN :i AND :f AND l.status = 'lancado'
         GROUP BY 1, 2, 3
         -- Alfabetica, nao por valor: esta e lista de CONFERENCIA. Procurar "Loide"
         -- numa lista ordenada por dinheiro obriga a varrer tudo.
         ORDER BY 1
    """),
            {"i": inicio, "f": fim},
        )
        .mappings()
        .all()
    )

    linhas, total_geral, total_dias = [], 0.0, 0
    for n, r in enumerate(rs, start=1):
        variavel = "" if r["minimo"] == r["maximo"] else " *"
        linhas.append(
            [
                n,
                r["nome"],
                _cpf_mascara(r["cpf"]),
                r["chave"],
                r["dias_lista"],
                r["dias"],
                _brl(float(r["media"])) + variavel,
                _brl(float(r["total"])),
            ]
        )
        total_geral += float(r["total"])
        total_dias += int(r["dias"])

    sem_chave = [r["nome"] for r in rs if "SEM CHAVE" in r["chave"]]
    resumo = {"diaristas": len(rs), "dias": total_dias, "total": round(total_geral, 2), "sem_chave": sem_chave}

    # Oito colunas em paisagem (A4 = 297mm), somando 280mm — 8,5mm de folga de cada lado.
    #
    # As larguras de NOME, CPF e CHAVE PIX foram dimensionadas em 15/09/2026 pelo maior valor
    # REAL do cadastro, não por chute: 35 caracteres de nome (FRANCISCO EDINEY OLIVEIRA DE
    # ARAUJO) e 33 de chave (mauriciochagaschagas466@gmail.com). Antes a tabela somava 268mm
    # com a chave em 44mm, e o e-mail saía «mauriciochagaschagas466@g…». Numa lista cuja função
    # é PAGAR, chave PIX cortada não é estética — é o documento não servir para o que existe.
    # Quem cede espaço é a coluna de DIAS, que é conferência e tem a QTD ao lado.
    mes = inicio.strftime("%m/%Y")
    colunas = [
        {"t": "#", "w": 8, "a": "C"},
        {"t": "DIARISTA", "w": 64},
        {"t": "CPF", "w": 30, "a": "C"},
        {"t": "CHAVE PIX", "w": 56, "a": "C"},
        {"t": f"DIAS TRABALHADOS EM {mes}", "w": 64, "a": "C"},
        {"t": "QTD", "w": 11, "a": "C"},
        {"t": "VALOR/DIA", "w": 23, "a": "C"},
        {"t": "TOTAL", "w": 24, "a": "C"},
    ]
    # Nota em português de gente: acentuada e sem nome de tabela do banco. A anterior dizia
    # «Fonte: diaria_lancamentos com status 'lancado'» num documento que vai para o caixa.
    nota = (
        "* Valor/dia é a MÉDIA: a pessoa trabalhou turnos de preços diferentes no período — "
        "confira o total, não a média. Não inclui VT/VR, que é pago à parte e por dia."
    )
    if sem_chave:
        nota += f" ATENÇÃO: {len(sem_chave)} sem chave PIX cadastrada, não dá para pagar — {', '.join(sem_chave[:4])}."

    pdf = gerar_tabela_pdf(
        titulo=f"Diaristas — {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}",
        subtitulo=(
            f"Lista de pagamento · {len(rs)} diaristas · {total_dias} dias trabalhados · "
            f"emitido em {date.today().strftime('%d/%m/%Y')}"
        ),
        colunas=colunas,
        linhas=linhas,
        empresa=B.EMPRESA_PATRIMONIAL,  # diarista e prestador da PATRIMONIAL
        rodape=[(f"TOTAL A PAGAR — {len(rs)} diaristas, {total_dias} dias", _brl(total_geral))],
        nota=nota,
    )
    return pdf, resumo


def extrato_diarista(db, *, diarista_id: int, inicio: date, fim: date) -> tuple[bytes, dict]:
    """Extrato de UM diarista: uma linha por dia trabalhado, com posto, turno e valor.

    O relatório geral responde "quanto pagar"; este responde "por quê". São documentos
    diferentes e é por isso que o valor/dia aparece aqui SEM média — cada dia com o seu
    valor real, que é o que a pessoa confere.
    """
    from sqlalchemy import text

    cab = (
        db.execute(
            text(
                "SELECT nome, coalesce(cpf,'') AS cpf, coalesce(nullif(pix,''),'(SEM CHAVE PIX)') AS pix "
                "FROM diaria_diaristas WHERE id = :i"
            ),
            {"i": diarista_id},
        )
        .mappings()
        .first()
    )
    if not cab:
        raise ValueError(f"diarista {diarista_id} não encontrado")

    rs = (
        db.execute(
            text("""
        SELECT l.data, coalesce(l.posto,'—') AS posto, coalesce(l.turno,'—') AS turno,
               coalesce(l.funcao,'—') AS funcao, l.valor
          FROM diaria_lancamentos l
         WHERE l.diarista_id = :i AND l.data BETWEEN :a AND :b AND l.status = 'lancado'
         ORDER BY l.data
    """),
            {"i": diarista_id, "a": inicio, "b": fim},
        )
        .mappings()
        .all()
    )

    linhas = [
        [n, r["data"].strftime("%d/%m/%Y"), r["posto"], r["turno"], r["funcao"], _brl(float(r["valor"]))]
        for n, r in enumerate(rs, start=1)
    ]
    total = round(sum(float(r["valor"]) for r in rs), 2)
    resumo = {"nome": cab["nome"], "cpf": cab["cpf"], "pix": cab["pix"], "dias": len(rs), "total": total}

    colunas = [
        {"t": "#", "w": 12, "a": "C"},
        {"t": "DATA", "w": 34, "a": "C"},
        {"t": "POSTO", "w": 74, "a": "C"},
        {"t": "TURNO", "w": 40, "a": "C"},
        {"t": "FUNÇÃO", "w": 56, "a": "C"},
        {"t": "VALOR DA DIÁRIA", "w": 40, "a": "C"},
    ]
    pdf = gerar_tabela_pdf(
        titulo=f"Extrato de diárias — {cab['nome']}",
        subtitulo=(
            f"CPF {cab['cpf']} · chave PIX {cab['pix']} · período "
            f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"
        ),
        colunas=colunas,
        linhas=linhas,
        empresa=B.EMPRESA_PATRIMONIAL,
        rodape=[(f"TOTAL — {len(rs)} diária(s) no período", _brl(total))],
        nota="Fonte: lancamentos de diaria com status 'lancado'. Nao inclui VT/VR, pago a parte e por dia.",
    )
    return pdf, resumo


def _dias_do_diarista(db, *, nome: str, inicio: date, fim: date) -> list[tuple]:
    """Os dias trabalhados da pessoa no período — o detalhamento que o recibo mostra."""
    from sqlalchemy import text

    rs = db.execute(
        text("""
        SELECT l.data, coalesce(l.posto,'—'), coalesce(l.turno,'—'),
               coalesce(l.funcao,'—'), l.valor
          FROM diaria_lancamentos l JOIN diaria_diaristas d ON d.id = l.diarista_id
         WHERE upper(btrim(d.nome)) = upper(btrim(:n))
           AND l.data BETWEEN :i AND :f AND l.status = 'lancado'
         ORDER BY l.data
    """),
        {"n": nome, "i": inicio, "f": fim},
    ).fetchall()
    return [(r[0].strftime("%d/%m/%Y"), r[1], r[2], r[3], float(r[4])) for r in rs]


def _recibo_de_um(
    db, *, pagamento_id: int, competencia: str, inicio: date, fim: date, assinar: bool = True
) -> tuple[bytes, dict]:
    """Monta o recibo de UMA pessoa. É a MESMA função que o lote usa.

    Existia um recibo para o botão da linha e outro para o ZIP — o da linha saía sem a
    tabela de dias e sem assinatura. Dois geradores para o mesmo documento é como um
    deles fica para trás: o do lote ganhou dias e assinatura, o da linha não.

    Valor vem do PAGAMENTO (consolidado da competência), não da soma dos lançamentos:
    é o que de fato saiu do banco, e é o que o recibo declara.
    """
    from sqlalchemy import text

    from modules.crm.services.doc_pdf import build_recibo_diarias_pdf

    r = (
        db.execute(
            text("""
        SELECT id, beneficiario, coalesce(cpf,'') cpf, coalesce(pix_key,'') pix,
               valor, updated_at::date AS pago_em, coalesce(descricao,'') descr, status
          FROM financial_pagamentos_diaristas WHERE id = :i
    """),
            {"i": pagamento_id},
        )
        .mappings()
        .first()
    )
    if not r:
        raise ValueError(f"pagamento {pagamento_id} não encontrado")
    if r["status"] != "pago":
        raise ValueError(
            f"{r['beneficiario']} está '{r['status']}', não 'pago' — recibo declara "
            f"quitação e só se emite para quem recebeu"
        )

    dias = _dias_do_diarista(db, nome=r["beneficiario"], inicio=inicio, fim=fim)
    if not dias:
        raise ValueError(
            f"{r['beneficiario']} não tem diária lançada no período — sem o detalhamento, o recibo não dá para conferir"
        )

    ref = r["descr"].split("| e2e:")[-1].strip() if "| e2e:" in r["descr"] else ""
    numero = f"RECD-{competencia.replace('/', '')}-{r['id']:04d}"
    pdf = build_recibo_diarias_pdf(
        {
            "numero": numero,
            "data": fim,
            "valor": float(r["valor"]),
            "recebedor": r["beneficiario"],
            "documento": r["cpf"],
            "chave_pix": r["pix"],
            "ref_banco": ref,
            "data_pagamento": r["pago_em"],
            "competencia": competencia,
            "dias": dias,
            "empresa": B.EMPRESA_PATRIMONIAL,
        }
    )
    assinado = False
    if assinar:
        try:
            from modules.signatures.services.qualified_signer import assinar_pdf_icp_brasil

            res = assinar_pdf_icp_brasil(
                pdf,
                reason=f"Recibo de diarias — competencia {competencia}",
                location="Manaus/AM",
                empresa_slug="conecta_patrimonial",
                visivel=True,
                rect=_rect_assinatura_empresa(pdf),
            )
            pdf, assinado = res.signed_pdf, True
        except Exception:  # noqa: BLE001 — ver recibos_competencia
            pass
    return pdf, {
        "nome": r["beneficiario"],
        "valor": float(r["valor"]),
        "dias": len(dias),
        "numero": numero,
        "assinado": assinado,
        "cpf": r["cpf"],
    }


def recibo_diarista(db, *, diarista_id: int, inicio: date, fim: date) -> tuple[bytes, dict]:
    """Recibo da pessoa, pelo id do DIARISTA — resolve o pagamento da competência."""
    from sqlalchemy import text

    comp = f"{fim.month:02d}/{fim.year}"
    pid = db.execute(
        text("""
        SELECT p.id FROM financial_pagamentos_diaristas p
          JOIN diaria_diaristas d ON upper(btrim(d.nome)) = upper(btrim(p.beneficiario))
         WHERE d.id = :i AND p.competencia = :c AND p.tipo = 'diaria_mensal'
         ORDER BY (p.status = 'pago') DESC LIMIT 1
    """),
        {"i": diarista_id, "c": comp},
    ).scalar()
    if not pid:
        raise ValueError(f"diarista {diarista_id} não tem pagamento de diárias em {comp}")
    return _recibo_de_um(db, pagamento_id=pid, competencia=comp, inicio=inicio, fim=fim)


def recibos_competencia(
    db, *, competencia: str, inicio: date, fim: date, so_pagos: bool = True, assinar: bool = True
) -> tuple[bytes, dict]:
    """Gera UM recibo por diarista da competência e devolve tudo num ZIP.

    `so_pagos=True` de propósito: recibo é declaração de quem RECEBEU. Emitir para quem
    ainda não recebeu produz papel que afirma um fato que não aconteceu — e alguém
    assina. Quem não foi pago sai na lista de fora, com o motivo.
    """
    import io
    import zipfile

    from sqlalchemy import text

    filtro = "AND p.status = 'pago'" if so_pagos else ""
    rs = (
        db.execute(
            text(f"""
        SELECT p.id, p.beneficiario, coalesce(p.cpf,'') cpf, coalesce(p.pix_key,'') pix,
               p.valor, p.updated_at::date AS pago_em, coalesce(p.descricao,'') descr, p.status
          FROM financial_pagamentos_diaristas p
         WHERE p.competencia = :c AND p.tipo = 'diaria_mensal' {filtro}
         ORDER BY p.beneficiario
    """),
            {"c": competencia},
        )
        .mappings()
        .all()
    )
    if not rs:
        raise ValueError(f"nenhum pagamento {'pago ' if so_pagos else ''}na competência {competencia}")

    buf = io.BytesIO()
    gerados, sem_dias, sem_assinatura = [], [], []
    titular = None
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rs:
            # MESMA função do botão da linha — um gerador só, para os dois nunca
            # divergirem de novo (a versão da linha tinha ficado sem dias e sem assinatura).
            try:
                pdf, info = _recibo_de_um(
                    db, pagamento_id=r["id"], competencia=competencia, inicio=inicio, fim=fim, assinar=assinar
                )
            except ValueError as e:
                sem_dias.append(f"{r['beneficiario']}: {e}")
                continue
            if assinar and not info["assinado"]:
                sem_assinatura.append(r["beneficiario"])
            nome_arq = "".join(ch if ch.isalnum() else "_" for ch in r["beneficiario"])[:40]
            z.writestr(f"{info['numero']}_{nome_arq}.pdf", pdf)
            gerados.append(
                {"nome": info["nome"], "valor": info["valor"], "dias": info["dias"], "numero": info["numero"]}
            )
    titular = "CONECTAMAIS PATRIMONIAL LTDA:66014833000110" if assinar else None
    resumo = {
        "competencia": competencia,
        "recibos": len(gerados),
        "total": round(sum(g["valor"] for g in gerados), 2),
        "sem_dias_lancados": sem_dias,
        "detalhe": gerados,
        "assinados": len(gerados) - len(sem_assinatura) if assinar else 0,
        "sem_assinatura": sem_assinatura,
        "certificado": titular,
    }
    return buf.getvalue(), resumo


def _rect_assinatura_empresa(pdf_bytes: bytes) -> tuple[float, float, float, float] | None:
    """Onde desenhar o selo: em cima da LINHA de assinatura da empresa (a da direita).

    Localiza a linha no PDF em vez de fixar coordenada: o bloco de assinatura desce ou
    sobe conforme o número de diárias, então posição fixa acertaria num recibo de 3 dias
    e erraria no de 11. Se não achar, devolve None e o assinador usa o rodapé — selo no
    lugar errado é feio, selo ausente é documento sem prova.
    """
    try:
        import pymupdf

        d = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pg = d[-1]
        linhas = [w for w in pg.get_text("words") if "_" in w[4] and (w[2] - w[0]) > 100]
        if not linhas:
            return None
        # a da DIREITA é a da empresa (a da esquerda é de quem recebe)
        x0, y_top, x1 = (
            max(linhas, key=lambda w: w[0])[0],
            min(w[1] for w in linhas),
            max(linhas, key=lambda w: w[0])[2],
        )
        altura = 58.0
        return (x0, y_top - altura + 2, x1, y_top + 2)
    except Exception:  # noqa: BLE001
        return None
