"""Gera o Excel das lacunas do financeiro — o que falta é INFORMAÇÃO, não código.

O Jordan pediu "um arquivo em excel pra eu preencher o que falta". Este script
monta esse arquivo com as LINHAS REAIS do banco: cada aba já vem preenchida com
o que o sistema sabe, e as colunas em laranja são as que só ele pode responder.

Nada aqui é inventado. Toda linha sai de uma query; onde o sistema não sabe, a
célula fica vazia — nunca com um exemplo plausível que depois vira "dado".

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
        /app/scripts/gerar_excel_lacunas_financeiro.py /app/uploads/lacunas.xlsx
"""
from __future__ import annotations

import re
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import text

from core.database.session import SyncSessionLocal

NAVY = "16277D"
LARANJA = "F26522"
CINZA = "F2F2F2"

H_SISTEMA = PatternFill("solid", fgColor=NAVY)          # o que o sistema já sabe
H_VOCE = PatternFill("solid", fgColor=LARANJA)          # o que só o Jordan sabe
ZEBRA = PatternFill("solid", fgColor=CINZA)
BRANCO = Font(color="FFFFFF", bold=True)
BORDA = Border(*[Side(style="thin", color="D0D0D0")] * 4)


def _limpa(historico: str) -> str:
    """Tira o prefixo 'Extrato dd/mm/aaaa: ' e o sufixo ' — motivo' do histórico."""
    h = re.sub(r"^Extrato \d{2}/\d{2}/\d{4}:\s*", "", historico or "")
    return re.sub(r"\s+—\s.*$", "", h).strip()


def _contraparte(historico: str) -> str:
    """Nome de quem recebeu. O Inter escreve 'PIX ENVIADO - Cp :00000000-Fulano';
    o Cora escreve a justificativa que o Jordan digitou no app, sem nome de pessoa."""
    h = _limpa(historico)
    if h.startswith("[CORA]"):
        return ""  # a justificativa do app não nomeia quem recebeu
    # "PIX ENVIADO INTERNO - 00019 122760174 ELIZIEL FLORES" → o nome vem depois
    # da agência e da conta; sem cortar isso o mesmo Eliziel vira duas pessoas.
    for padrao in (r"Cp\s*:\s*\d+\s*-\s*(.+)$", r"INTERNO\s*-\s*\d+\s+\d+\s+(.+)$"):
        m = re.search(padrao, h)
        if m:
            h = m.group(1).strip()
            break
    # o Inter às vezes ainda prefixa o CPF/CNPJ ao nome depois do traço
    return re.sub(r"^\d{6,}\s+", "", h).strip()


def _aba(wb, titulo, colunas, linhas, larguras, nota=None):
    """colunas: lista de (rótulo, 'sistema'|'voce')."""
    ws = wb.create_sheet(titulo)
    linha0 = 1
    if nota:
        ws.cell(1, 1, nota).font = Font(italic=True, color="555555")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(colunas))
        ws.row_dimensions[1].height = 30
        ws.cell(1, 1).alignment = Alignment(wrap_text=True, vertical="center")
        linha0 = 3

    for i, (rotulo, dono) in enumerate(colunas, start=1):
        c = ws.cell(linha0, i, rotulo)
        c.fill = H_SISTEMA if dono == "sistema" else H_VOCE
        c.font = BRANCO
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        ws.column_dimensions[get_column_letter(i)].width = larguras[i - 1]
    ws.row_dimensions[linha0].height = 32

    for j, linha in enumerate(linhas):
        for i in range(len(colunas)):
            v = linha[i] if i < len(linha) else None
            c = ws.cell(linha0 + 1 + j, i + 1, v)
            c.border = BORDA
            if j % 2:
                c.fill = ZEBRA
            if isinstance(v, float):
                c.number_format = 'R$ #,##0.00'

    ws.freeze_panes = ws.cell(linha0 + 1, 1)
    return ws


def main(destino: str) -> None:
    db = SyncSessionLocal()
    wb = Workbook()
    wb.remove(wb.active)

    # ── LEIA-ME ─────────────────────────────────────────────────────────────
    ws = wb.create_sheet("LEIA-ME")
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 34
    ws.column_dimensions["C"].width = 96
    ws.cell(1, 2, "O que falta para fechar o financeiro").font = Font(size=16, bold=True, color=NAVY)
    ws.cell(2, 2, "Coluna AZUL = o sistema já sabe (não mexer). Coluna LARANJA = só você sabe.").font = Font(italic=True)
    guia = [
        ("1", "Notas de julho", "Duas notas do mesmo serviço, uma por CNPJ. Decidir qual vale. Sem isso o faturamento de julho fica R$108 mil acima do real."),
        ("2", "Saídas a classificar", "Cada saída de agosto que o sistema não soube enquadrar. Você diz o que é; ele aprende o padrão e não pergunta de novo."),
        ("3", "Fornecedores PJ", "CNPJ e valor de cada prestador. Sem CNPJ o pagamento não vira despesa dedutível nem casa com nota."),
        ("4", "Contas a pagar fixas", "Por isso 'a pagar nos próximos 7 dias' mostra R$0,00: não existe nenhuma conta cadastrada com vencimento futuro."),
        ("5", "Contas a pagar antigas", "76 contas em aberto desde janeiro. Dizer se foram pagas, se cancelo, ou se ainda devo."),
        ("6", "Contratos a receber", "O valor mensal e o dia de vencimento de cada cliente, por CNPJ. É o que enche a carteira de recebíveis."),
        ("7", "Patrimônio e cartões", "Capital social, lucros até 2025, limites e faturas de cartão. É o único bloco que impede o balanço de ficar completo."),
    ]
    for i, (n, aba, pq) in enumerate(guia, start=4):
        ws.cell(i, 1, n).font = Font(bold=True, color=LARANJA)
        ws.cell(i, 2, aba).font = Font(bold=True)
        ws.cell(i, 3, pq).alignment = Alignment(wrap_text=True)
        ws.row_dimensions[i].height = 30

    # ── 1. Notas de julho ───────────────────────────────────────────────────
    notas = db.execute(text("""
        SELECT n.numero, coalesce(e.nome_fantasia, e.razao_social, '?'),
               to_char(n.data_emissao, 'DD/MM/YYYY'), n.tomador_nome, n.valor_servicos
        FROM nfse_emitidas_nacional n
        LEFT JOIN empresas e ON e.id = n.empresa_id
        WHERE to_char(n.data_emissao, 'YYYY-MM') = '2026-07'
          AND EXISTS (SELECT 1 FROM nfse_emitidas_nacional o
                       WHERE o.chave_acesso <> n.chave_acesso
                         AND o.tomador_nome = n.tomador_nome
                         AND o.valor_servicos = n.valor_servicos
                         AND to_char(o.data_emissao, 'YYYY-MM') = '2026-07')
        ORDER BY n.tomador_nome, n.data_emissao
    """)).fetchall()
    _aba(wb, "1. Notas de julho",
         [("Nº nota", "sistema"), ("CNPJ emissor", "sistema"), ("Emissão", "sistema"),
          ("Tomador", "sistema"), ("Valor", "sistema"),
          ("Esta nota VALE? (sim/não)", "voce"), ("Se não: cancelar ou já cancelada?", "voce")],
         [(str(n[0]), n[1], n[2], n[3], float(n[4])) for n in notas],
         [10, 24, 12, 40, 14, 20, 26],
         nota=("Julho fechou R$378.286,98 — R$108.386,92 acima dos outros meses. São pares do MESMO "
               "serviço faturados pelos DOIS CNPJs na transição. Nenhuma está cancelada no Ambiente "
               "Nacional, e o cliente pagou uma vez só. Marque qual vale; eu NÃO cancelo nota — "
               "cancelamento é ato fiscal e vai com o contador."))

    # ── 2. Saídas a classificar (agosto em diante) ──────────────────────────
    saidas = db.execute(text("""
        SELECT a.data_lancamento::text, a.valor,
               coalesce(a.historico, ''),
               CASE WHEN a.historico LIKE '%[CORA]%' THEN 'Cora' ELSE 'Inter' END
        FROM accounting_entries a
        WHERE a.conta_debito = '5.9.9.01' AND a.data_lancamento >= DATE '2026-08-01'
        ORDER BY a.data_lancamento DESC, a.valor DESC
    """)).fetchall()
    _aba(wb, "2. Saidas a classificar",
         [("Data", "sistema"), ("Banco", "sistema"), ("Valor", "sistema"), ("Descrição do extrato", "sistema"),
          ("O que é (natureza)", "voce"), ("Para quem", "voce"), ("Tem nota fiscal?", "voce"), ("Observação", "voce")],
         [(s[0], s[3], float(s[1]), _limpa(s[2])) for s in saidas],
         [12, 9, 13, 62, 24, 28, 15, 30],
         nota=("Só agosto — de julho pra trás você decidiu fechar. Natureza sugerida: combustível, "
               "alimentação, material, uniforme, adiantamento, reembolso, aluguel, comissão, "
               "equipamento, empréstimo, transferência entre contas, retirada de sócio."))

    # ── 3. Fornecedores PJ ──────────────────────────────────────────────────
    brutos = db.execute(text("""
        SELECT coalesce(historico, ''), valor FROM accounting_entries
        WHERE data_lancamento >= DATE '2026-05-01' AND conta_credito LIKE '1.1.1%'
    """)).fetchall()
    agrupado: dict[str, list] = {}
    for hist, valor in brutos:
        nome = _contraparte(hist)
        if not nome or len(nome) < 3:
            continue
        alvo = agrupado.setdefault(nome[:60], [0, 0.0])
        alvo[0] += 1
        alvo[1] += float(valor)
    pj = sorted(((k, v[0], v[1]) for k, v in agrupado.items() if v[0] >= 2 and v[1] >= 500),
                key=lambda r: -r[2])[:60]
    _aba(wb, "3. Fornecedores PJ",
         [("Quem recebeu (do extrato)", "sistema"), ("Nº de pagamentos", "sistema"), ("Total pago", "sistema"),
          ("É PJ? (sim/não)", "voce"), ("CNPJ", "voce"), ("Razão social", "voce"),
          ("Serviço prestado", "voce"), ("Emite nota?", "voce")],
         [(p[0], int(p[1]), float(p[2])) for p in pj],
         [46, 14, 14, 13, 22, 34, 30, 12],
         nota=("Quem recebeu 2 vezes ou mais desde maio. Você já confirmou como PJ: Eliziel, Orlailson, "
               "Pyetra, Ramon Araujo, Pedro Rafael, Ruan Souza, Diego Ferreira, José Rodrigo e "
               "Francisco Ediney. Falta o CNPJ de cada um — sem ele o pagamento não casa com nota."))

    # ── 4. Contas a pagar fixas ─────────────────────────────────────────────
    _aba(wb, "4. Contas a pagar fixas",
         [("Despesa", "voce"), ("CNPJ que paga", "voce"), ("Fornecedor", "voce"), ("Valor mensal", "voce"),
          ("Dia do vencimento", "voce"), ("Forma de pagamento", "voce"), ("Tem contrato?", "voce")],
         [(v,) for v in ("Aluguel", "Energia", "Água", "Internet", "Telefonia", "Contador",
                         "Software / sistemas", "Seguro", "Vale-transporte", "Vale-alimentação",
                         "Uniformes", "Manutenção de veículos", "Combustível", "", "", "", "", "", "", "")],
         [30, 20, 34, 15, 17, 22, 15],
         nota=("A tela mostra 'a pagar nos próximos 7 dias: R$0,00' porque NÃO existe uma única conta "
               "cadastrada com vencimento futuro — hoje a conta só nasce depois que o dinheiro já saiu. "
               "Preenchendo isto, o sistema passa a avisar ANTES do vencimento. A lista é um ponto de "
               "partida: apague o que não existe, acrescente o que falta."))

    # ── 5. Contas a pagar antigas ───────────────────────────────────────────
    antigas = db.execute(text("""
        SELECT p.due_date::text, coalesce(p.supplier_name, p.fornecedor_nome, p.description, '?'),
               p.net_value, coalesce(e.nome_fantasia, e.razao_social, '')
        FROM payable_accounts p LEFT JOIN empresas e ON e.id = p.empresa_id
        WHERE p.status = 'pendente' ORDER BY p.due_date
    """)).fetchall()
    _aba(wb, "5. Contas a pagar antigas",
         [("Vencimento", "sistema"), ("Fornecedor / descrição", "sistema"), ("Valor", "sistema"),
          ("CNPJ (se o sistema soube)", "sistema"),
          ("Situação: paga / cancelar / ainda devo", "voce"), ("Se paga: quando e por qual conta", "voce")],
         [(a[0], str(a[1])[:60], float(a[2]), a[3]) for a in antigas],
         [13, 56, 14, 24, 30, 30],
         nota=("76 contas continuam 'pendentes', a mais antiga de 03/01. Ou foram pagas e ninguém deu "
               "baixa, ou não existem mais. Enquanto estiverem assim, qualquer número de dívida do "
               "sistema está errado — e 46 delas nem sabem de qual CNPJ são."))

    # ── 6. Contratos a receber ──────────────────────────────────────────────
    receb = db.execute(text("""
        SELECT coalesce(r.customer_name, r.description, '?'),
               coalesce(e.nome_fantasia, e.razao_social, ''),
               r.gross_value, r.due_date::text
        FROM receivable_accounts r LEFT JOIN empresas e ON e.id = r.empresa_id
        WHERE r.status = 'pendente' ORDER BY r.gross_value DESC
    """)).fetchall()
    _aba(wb, "6. Contratos a receber",
         [("Cliente", "sistema"), ("CNPJ emissor", "sistema"), ("Valor do título", "sistema"),
          ("Vencimento", "sistema"),
          ("Já recebeu? (sim/não)", "voce"), ("Se sim: data e conta", "voce"),
          ("Valor mensal do contrato", "voce"), ("Dia de vencimento", "voce")],
         [(r[0][:50], r[1], float(r[2]), r[3]) for r in receb],
         [46, 24, 16, 13, 18, 24, 22, 16],
         nota=("Os R$152.077,82 de 'recebíveis vencidos' são estes títulos — a carteira de contratos dos "
               "DOIS CNPJs somada (Patrimonial R$141.577,82 + Eletrônica R$10.500,00), não a soma das "
               "contas bancárias. Todos venceram em 10/08. Diga quais já caíram."))

    # ── 7. Patrimônio e cartões ─────────────────────────────────────────────
    _aba(wb, "7. Patrimonio e cartoes",
         [("Item", "sistema"), ("CNPJ", "voce"), ("Valor", "voce"), ("Data / referência", "voce"), ("Observação", "voce")],
         [("Capital social integralizado — Eletrônica",),
          ("Capital social integralizado — Patrimonial",),
          ("Lucros ou prejuízos acumulados até 31/12/2025",),
          ("Cartão de crédito Itaú — limite",),
          ("Cartão de crédito Itaú — fatura em aberto hoje",),
          ("Cartão de crédito Nubank — limite",),
          ("Cartão de crédito Nubank — fatura em aberto hoje",),
          ("Empréstimos ou financiamentos em aberto",),
          ("Veículos, equipamentos e imóveis da empresa",),
          ("Dinheiro que a empresa deve a você (conta de sócio)",),
          ("Dinheiro que você deve à empresa",)],
         [50, 22, 16, 22, 44],
         nota=("Este é o único bloco que impede o balanço de sair completo. Hoje ele sai declarando "
               "'pl_completo: false' — honesto, mas incompleto: capital social e lucros até 2025 só "
               "existem no balanço do contador. Os cartões são o outro lado: você paga a fatura pela "
               "empresa, mas o que foi comprado com o cartão não está em lugar nenhum."))

    wb.save(destino)
    print(f"OK {destino}")
    for aba in wb.sheetnames:
        print(f"   {aba}: {wb[aba].max_row - (3 if aba != 'LEIA-ME' else 0)} linhas")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/app/uploads/lacunas_financeiro.xlsx")
