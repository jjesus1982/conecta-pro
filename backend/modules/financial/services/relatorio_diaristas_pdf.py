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

from modules.crm.services import pdf_branding as B

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


def gerar_tabela_pdf(*, titulo: str, subtitulo: str, colunas: list[dict],
                     linhas: list[list], rodape: list[tuple[str, str]] | None = None,
                     nota: str | None = None, empresa: dict | None = None,
                     tam: float = 8) -> bytes:
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
        for col, val in zip(colunas, linha):
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
        for pedaco in [nota[i:i + 170] for i in range(0, len(nota), 170)]:
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

    rs = db.execute(text("""
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
    """), {"i": inicio, "f": fim}).mappings().all()

    linhas, total_geral, total_dias = [], 0.0, 0
    for n, r in enumerate(rs, start=1):
        variavel = "" if r["minimo"] == r["maximo"] else " *"
        linhas.append([n, r["nome"], r["cpf"], r["chave"], r["dias_lista"], r["dias"],
                       _brl(float(r["media"])) + variavel, _brl(float(r["total"]))])
        total_geral += float(r["total"])
        total_dias += int(r["dias"])

    sem_chave = [r["nome"] for r in rs if "SEM CHAVE" in r["chave"]]
    resumo = {"diaristas": len(rs), "dias": total_dias, "total": round(total_geral, 2),
              "sem_chave": sem_chave}

    # Oito colunas em paisagem: corpo em 8pt e o que faz tudo caber sem espremer.
    # O corte por largura real (_cabe) acompanha o tamanho da fonte sozinho.
    mes = inicio.strftime("%m/%Y")
    colunas = [
        {"t": "#", "w": 9, "a": "C"},
        {"t": "DIARISTA", "w": 53},
        {"t": "CPF", "w": 26, "a": "C"},
        {"t": "CHAVE PIX", "w": 44, "a": "C"},
        {"t": f"DIAS TRABALHADOS EM {mes}", "w": 70, "a": "C"},
        {"t": "QTD", "w": 12, "a": "C"},
        {"t": "VALOR/DIA", "w": 26, "a": "C"},
        {"t": "TOTAL", "w": 28, "a": "C"},
    ]
    nota = ("* valor/dia e MEDIA: a pessoa trabalhou turnos de precos diferentes no periodo. "
            "Fonte: diaria_lancamentos com status 'lancado'. Nao inclui VT/VR, que e pago a parte "
            "e por dia.")
    if sem_chave:
        nota += f" ATENCAO: {len(sem_chave)} sem chave PIX cadastrada — {', '.join(sem_chave[:4])}."

    pdf = gerar_tabela_pdf(
        titulo=f"Diaristas — {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}",
        subtitulo=(f"Lista de pagamento · {len(rs)} diaristas · {total_dias} dias trabalhados · "
                   f"emitido em {date.today().strftime('%d/%m/%Y')}"),
        colunas=colunas, linhas=linhas,
        empresa=B.EMPRESA_PATRIMONIAL,  # diarista e prestador da PATRIMONIAL
        rodape=[(f"TOTAL A PAGAR — {len(rs)} diaristas, {total_dias} dias", _brl(total_geral))],
        nota=nota)
    return pdf, resumo


def extrato_diarista(db, *, diarista_id: int, inicio: date, fim: date) -> tuple[bytes, dict]:
    """Extrato de UM diarista: uma linha por dia trabalhado, com posto, turno e valor.

    O relatório geral responde "quanto pagar"; este responde "por quê". São documentos
    diferentes e é por isso que o valor/dia aparece aqui SEM média — cada dia com o seu
    valor real, que é o que a pessoa confere.
    """
    from sqlalchemy import text

    cab = db.execute(text(
        "SELECT nome, coalesce(cpf,'') AS cpf, coalesce(nullif(pix,''),'(SEM CHAVE PIX)') AS pix "
        "FROM diaria_diaristas WHERE id = :i"), {"i": diarista_id}).mappings().first()
    if not cab:
        raise ValueError(f"diarista {diarista_id} não encontrado")

    rs = db.execute(text("""
        SELECT l.data, coalesce(l.posto,'—') AS posto, coalesce(l.turno,'—') AS turno,
               coalesce(l.funcao,'—') AS funcao, l.valor
          FROM diaria_lancamentos l
         WHERE l.diarista_id = :i AND l.data BETWEEN :a AND :b AND l.status = 'lancado'
         ORDER BY l.data
    """), {"i": diarista_id, "a": inicio, "b": fim}).mappings().all()

    linhas = [[n, r["data"].strftime("%d/%m/%Y"), r["posto"], r["turno"], r["funcao"],
               _brl(float(r["valor"]))] for n, r in enumerate(rs, start=1)]
    total = round(sum(float(r["valor"]) for r in rs), 2)
    resumo = {"nome": cab["nome"], "cpf": cab["cpf"], "pix": cab["pix"],
              "dias": len(rs), "total": total}

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
        subtitulo=(f"CPF {cab['cpf']} · chave PIX {cab['pix']} · período "
                   f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"),
        colunas=colunas, linhas=linhas, empresa=B.EMPRESA_PATRIMONIAL,
        rodape=[(f"TOTAL — {len(rs)} diária(s) no período", _brl(total))],
        nota="Fonte: lancamentos de diaria com status 'lancado'. Nao inclui VT/VR, pago a parte e por dia.")
    return pdf, resumo


def recibo_diarista(db, *, diarista_id: int, inicio: date, fim: date) -> tuple[bytes, dict]:
    """Recibo de pagamento, para o diarista assinar.

    NÃO afirma que o pagamento foi feito: um recibo é a declaração de QUEM RECEBE, e
    quem assina é ele. Emitir "pago" antes da assinatura seria o sistema declarando em
    nome de terceiro — o mesmo defeito de dizer "ok" quando o e-mail do OTP falhou.
    """
    import io as _io

    from reportlab.lib.pagesizes import A4 as _A4
    from reportlab.pdfgen import canvas as _cv

    _, r = extrato_diarista(db, diarista_id=diarista_id, inicio=inicio, fim=fim)
    if r["dias"] == 0:
        raise ValueError("sem diárias lançadas no período — não há o que dar recibo")

    buf = _io.BytesIO()
    W, H = _A4
    c = _cv.Canvas(buf, pagesize=_A4)
    y = B.marca_canvas(c, titulo="RECIBO DE PAGAMENTO", pagesize=_A4,
                       empresa=B.EMPRESA_PATRIMONIAL)
    x0 = 20 * mm
    larg = W - 40 * mm

    c.setFillColor(_LARANJA)
    c.setFont("Helvetica-Bold", 20)
    c.drawRightString(W - 20 * mm, y - 2 * mm, _brl(r["total"]))
    y -= 16 * mm

    E = B.EMPRESA_PATRIMONIAL
    corpo = (
        f"Recebi de {E['razao']}, inscrita no CNPJ sob o nº {E['cnpj']}, a importância de "
        f"{_brl(r['total'])} ({_extenso(r['total'])}), referente a {r['dias']} diária(s) "
        f"prestada(s) no período de {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}, "
        f"conforme extrato anexo, dando plena e geral quitação quanto ao valor recebido."
    )
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 11)
    y = _paragrafo(c, corpo, x0, y, larg, 11, 6.2 * mm)

    y -= 6 * mm
    c.setFillColor(_AZUL)
    c.setFont("Helvetica-Bold", 10)
    for rot, val in (("Recebedor", r["nome"]), ("CPF", r["cpf"]), ("Chave PIX", r["pix"]),
                     ("Diárias no período", str(r["dias"])), ("Valor total", _brl(r["total"]))):
        c.setFillColor(_CINZA)
        c.drawString(x0, y, rot)
        c.setFillColor(colors.black)
        c.drawString(x0 + 42 * mm, y, str(val))
        y -= 6.5 * mm

    y -= 14 * mm
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.6)
    c.line(x0 + 20 * mm, y, x0 + larg - 20 * mm, y)
    y -= 5 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, y, r["nome"])
    y -= 4.5 * mm
    c.drawCentredString(W / 2, y, f"CPF {r['cpf']}")
    y -= 10 * mm
    c.setFillColor(_CINZA)
    c.setFont("Helvetica", 9)
    c.drawCentredString(W / 2, y, f"Manaus/AM, ____ de __________________ de {fim.year}.")

    B.rodape_canvas(c, pagesize=_A4, pagina=1, empresa=B.EMPRESA_PATRIMONIAL)
    c.save()
    return buf.getvalue(), r


def _paragrafo(c, texto: str, x: float, y: float, largura: float, tam: float,
               entrelinha: float) -> float:
    """Quebra por LARGURA medida. Quebrar por número de caracteres deixa linha curta ao
    lado de linha estourada, e num recibo isso parece documento improvisado."""
    palavras, linha = texto.split(), ""
    for p in palavras:
        teste = f"{linha} {p}".strip()
        if c.stringWidth(teste, "Helvetica", tam) > largura:
            c.drawString(x, y, linha)
            y -= entrelinha
            linha = p
        else:
            linha = teste
    if linha:
        c.drawString(x, y, linha)
        y -= entrelinha
    return y


_UNI = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
        "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CEM = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
        "setecentos", "oitocentos", "novecentos"]


def _ate999(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cem"
    c_, r_ = divmod(n, 100)
    d_, u_ = divmod(r_, 10)
    partes = [_CEM[c_]] if c_ else []
    if r_ < 20:
        partes += [_UNI[r_]] if r_ else []
    else:
        partes += [_DEZ[d_]] + ([_UNI[u_]] if u_ else [])
    return " e ".join([p for p in partes if p])


def _extenso(valor: float) -> str:
    """Valor por extenso — exigência de recibo. Escrito aqui em vez de dependência nova:
    são 30 linhas e o teto de um recibo de diária não chega perto do milhão."""
    reais, centavos = divmod(int(round(valor * 100)), 100)
    mil, resto = divmod(reais, 1000)
    partes = []
    if mil:
        partes.append("mil" if mil == 1 else f"{_ate999(mil)} mil")
    if resto:
        partes.append(_ate999(resto))
    txt = " e ".join(partes) or "zero"
    txt += " real" if reais == 1 else " reais"
    if centavos:
        txt += f" e {_ate999(centavos)} " + ("centavo" if centavos == 1 else "centavos")
    return txt
