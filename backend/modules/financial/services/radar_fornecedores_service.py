"""Radar de fornecedores recorrentes — avisa o que vai vencer e não tem título.

O caso que motivou (19/08/2026): a Full Telecom é paga todo mês desde março e **nunca
teve conta a pagar**. Sem título, nada avisa no vencimento; o boleto venceu, e o banco
passou a exigir valor atualizado — R$4,48 de juros num boleto de R$149, e 30 dias sem
saber que devia. Mesma situação da Starlink. São 36 vencimentos por ano só de internet.

O `payable_sources_service` já cobre as obrigações que têm documento: NFS-e tomadas,
folha, guias. Telecom, energia, água e aluguel não emitem NFS-e — caem fora, e é esse
o buraco.

⚠️ **Este radar NÃO cria dívida.** Ele olha o que a empresa vem pagando de fato e avisa
quando um fornecedor recorrente está perto do vencimento sem título cadastrado. Criar um
pagável a partir de inferência seria afirmar uma dívida que ninguém emitiu — o oposto da
regra da casa. Radar mostra; boleto real ou humano cria.

⚠️ **A data é ESTIMADA e o aviso diz isso.** Só temos a data de PAGAMENTO, não a de
vencimento. Já custou caro confundir os dois: a moda do histórico de pagamento das guias
"provou" um vencimento que não era o legal e gerou alarme falso. Aqui o dia estimado
serve para ordenar a atenção, nunca para afirmar prazo.
"""

from __future__ import annotations

import logging
import re
import statistics
from datetime import date, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Mínimo de meses distintos com pagamento para considerar recorrente. Com 2 é ruído
#: (duas compras avulsas do mesmo lugar); com 3 já há cadência.
MESES_MINIMOS = 3

#: Janela de análise. 8 meses cobre o histórico real do extrato (começa em 01/2026) sem
#: arrastar fornecedor que a empresa deixou de usar.
MESES_ANALISE = 8

#: Antecedência do aviso. 10 dias dá tempo de pedir a segunda via antes de vencer.
DIAS_ANTECEDENCIA = 10

#: Fornecedores que NÃO são recorrência de fornecedor, mesmo parecendo. Folha, diaristas
#: e tributos têm motor próprio — avisar aqui seria ruído em cima de quem já cuida.
#: Categorias cujo vencimento tem motor próprio. Excluir por CATEGORIA (dado do extrato)
#: em vez de por nome evita tanto o falso positivo — VT de R$32 para uma pessoa física
#: parece "fornecedor recorrente" — quanto a adivinhação de quem é pessoa e quem é empresa.
CATEGORIAS_DE_OUTRO_DONO = (
    "Diaristas", "Diaristas VT+VR", "Folha", "folha_pagamento",  # a variante minúscula
    "Pagamento a funcionario", "Pró-labore", "Impostos",         # existe no dado real
)

IGNORAR = re.compile(
    r"(vale (transporte|alimenta)|diarист|diarista|folha|sal[áa]rio|pró-?labore|prolabore"
    r"|inss|fgts|darf|das |simples nacional|iss |irrf|tribut|guia |transfer|resgate"
    r"|aplica[çc][ãa]o|rendimento|estorno|tarifa|juros|iof|empr[ée]stimo)",
    re.IGNORECASE,
)


def _chave(nome: str) -> str:
    """Nome do fornecedor reduzido ao que identifica.

    "FULL TELECOM LTDA" e "PAGAMENTO DE TITULO - FULL TELECOM LTDA" são o mesmo
    fornecedor; sem normalizar, viram dois e nenhum atinge o mínimo de meses.
    """
    n = nome or ""
    # "PIX ENVIADO - Cp :00360305-Jeovane do Nascimento": o miolo é o nome da pessoa,
    # precedido de rótulo e do código do banco. Sem tirar isso, o nome fica escondido
    # dentro da chave e o cruzamento com o cadastro não casa.
    n = re.sub(r"(?i)^(pix\s+enviado|pix|ted|doc|boleto|pagamento de titulo|pagamento)\s*[:\-–]?\s*", "", n)
    n = re.sub(r"(?i)^cp\s*:?\s*\d+\s*[-–]?\s*", "", n.strip().strip('"'))
    n = re.sub(r"(?i)\b(ltda|s\.?a\.?|me|epp|eireli|servicos?|servi[çc]os?)\b", " ", n)
    n = re.sub(r"[^A-Za-zÀ-ÿ0-9 ]", " ", n)
    return " ".join(n.upper().split())[:60]


def varrer(db, hoje: date | None = None) -> dict:
    """Devolve os fornecedores recorrentes SEM título para o próximo vencimento."""
    hoje = hoje or date.today()
    inicio = hoje - timedelta(days=30 * MESES_ANALISE)

    linhas = db.execute(text("""
        SELECT COALESCE(NULLIF(t.counterparty_name,''), t.description) AS nome,
               t.transaction_date AS data, ABS(t.amount) AS valor
          FROM bank_transactions t
         WHERE t.amount < 0 AND t.transaction_date >= :ini
           AND COALESCE(NULLIF(t.counterparty_name,''), t.description) IS NOT NULL
           -- Exclui por CATEGORIA, não por nome: folha, diaristas e VT/VR já têm motor
           -- próprio, e avisar aqui seria ruído em cima de quem cuida. Categoria é dado
           -- do extrato; filtrar por nome de pessoa seria adivinhação.
           AND COALESCE(t.category,'') NOT IN :cats
    """), {"ini": inicio, "cats": CATEGORIAS_DE_OUTRO_DONO}).mappings().all()

    # PESSOAS do nosso cadastro (funcionários e diaristas). Parte do VT/VR cai no balde
    # "Historico sem contraparte" e escapa do filtro por categoria: um PIX de R$32 para
    # uma pessoa, três meses seguidos, tem a cara de fornecedor recorrente. Cruzar com o
    # cadastro é o jeito honesto de separar — não dá para adivinhar pessoa por nome.
    pessoas = {
        _chave(r[0]) for r in db.execute(text(
            "SELECT nome FROM diaria_diaristas WHERE nome IS NOT NULL "
            "UNION SELECT nome FROM employees WHERE nome IS NOT NULL"
        )).fetchall() if r[0]
    }
    pessoas.discard("")

    grupos: dict[str, list] = {}
    for ln in linhas:
        nome = ln["nome"]
        if IGNORAR.search(nome or ""):
            continue
        k = _chave(nome)
        if len(k) < 6:          # nome curto demais para identificar fornecedor
            continue
        if k in pessoas or any(pes in k for pes in pessoas if len(pes) > 12):
            continue            # é gente nossa, não fornecedor
        grupos.setdefault(k, []).append(ln)

    achados = []
    for k, itens in grupos.items():
        meses = {(i["data"].year, i["data"].month) for i in itens}
        if len(meses) < MESES_MINIMOS:
            continue

        valores = sorted(float(i["valor"]) for i in itens)
        valor_tipico = statistics.median(valores)
        # Valor muito instável não é mensalidade — é compra avulsa do mesmo fornecedor.
        if valor_tipico <= 0 or (max(valores) / valor_tipico) > 3:
            continue

        # Dia ESTIMADO a partir do dia de PAGAMENTO. Não é o vencimento — ver o aviso
        # no topo do arquivo. Serve só para ordenar a atenção.
        dia = statistics.mode([i["data"].day for i in itens])
        prox = _proximo_dia(hoje, dia)

        if (prox - hoje).days > DIAS_ANTECEDENCIA:
            continue

        nome_real = max((i["nome"] for i in itens), key=len)
        tem_titulo = db.execute(text("""
            SELECT 1 FROM payable_accounts
             WHERE status NOT IN ('cancelada','suspensa')
               AND due_date BETWEEN :a AND :b
               AND UPPER(COALESCE(supplier_name,'')) LIKE :like
             LIMIT 1
        """), {"a": prox - timedelta(days=7), "b": prox + timedelta(days=7),
               "like": f"%{k.split()[0]}%"}).fetchone()
        if tem_titulo:
            continue

        achados.append({
            "fornecedor": nome_real[:60],
            "chave": k,
            "meses_pagos": len(meses),
            "valor_tipico": round(valor_tipico, 2),
            "vencimento_estimado": prox.isoformat(),
            "dias": (prox - hoje).days,
            "ultimo_pagamento": max(i["data"] for i in itens).isoformat(),
        })

    achados.sort(key=lambda a: a["dias"])
    return {"analisados": len(grupos), "sem_titulo": len(achados), "achados": achados}


def _proximo_dia(hoje: date, dia: int) -> date:
    """Próxima ocorrência do dia do mês, a partir de hoje (inclusive)."""
    dia = min(max(dia, 1), 28)   # 28 evita mês curto virar mês seguinte
    if dia >= hoje.day:
        return hoje.replace(day=dia)
    prox = hoje.replace(day=1) + timedelta(days=32)
    return prox.replace(day=dia)
