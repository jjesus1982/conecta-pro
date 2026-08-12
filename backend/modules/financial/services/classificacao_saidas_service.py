"""Classificação das saídas do extrato — agrupada, com sugestão, decisão humana.

Por que existe: o razão só conhece **6% dos lançamentos do extrato** (268 de 4.502),
e quase só entradas. Para o razão refletir o caixa, cada saída precisa dizer o que
foi. São 1.241 saídas sem etiqueta (R$1.054.752,65) — rever uma a uma é inviável.

Medido em 2026-08-11 e é o que torna isto viável:
  • as 380 saídas ≥ R$1.000 se repetem entre apenas **183 contrapartes**;
  • **235** delas são para FUNCIONÁRIO cadastrado (R$409.174,72) → regra, não decisão;
  • 1.099 pagamentos de R$32,00 (VT+VR de diarista) já estão etiquetados.

Desenho: o sistema PROPÕE por regra e o humano CONFIRMA por grupo. Pedir
classificação do zero, uma a uma, é abandonado em três semanas.

Parede: sugestão nunca vira etiqueta sozinha. Nada aqui grava sem alguém confirmar.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Lista FECHADA. O campo livre já produziu dialeto na base: `imposto` e `impostos`,
# `outros` e `outro` convivem hoje. Categoria nova entra AQUI, não digitada.
CATEGORIAS: tuple[tuple[str, str], ...] = (
    ("salario", "Salário — funcionário CLT"),
    ("beneficio_vtvr", "Benefício — VT / VR / VA"),
    ("pj_prolabore", "PJ / Pró-labore — prestador"),
    ("diarista", "Diarista — diária ou cobertura"),
    ("socio", "Sócio — retirada, distribuição ou empréstimo"),
    ("fornecedor", "Fornecedor — serviço ou material"),
    ("imposto", "Imposto / guia — INSS, FGTS, DAS, DARF"),
    ("transferencia_interna", "Transferência entre empresas do grupo"),
    ("taxa_bancaria", "Taxa bancária"),
    # Despesa da EMPRESA que alguém adiantou (café, Uber, material). Não é
    # remuneração de quem recebe — sem esta opção, um reembolso de R$56,85 ao
    # Eliziel entrava como pró-labore dele e inflava o que ele ganhou.
    ("reembolso", "Reembolso — despesa da empresa adiantada por alguém"),
    # Devolução de dinheiro que a empresa TOMOU emprestado. Não é despesa: abate
    # o passivo. A Denise emprestou R$12.000 em 06/07 para completar a folha de
    # julho, e a entrada estava lançada como "cliente pagou" — abatendo R$12.000
    # de contas a receber que ninguém devia.
    ("emprestimo", "Empréstimo — devolução de dinheiro tomado"),
    ("diversos", "Diversos — pequeno valor, sem enquadramento"),
)
CATEGORIAS_VALIDAS = frozenset(k for k, _ in CATEGORIAS)

# Normaliza a contraparte: tira o código mascarado do banco e a pontuação.
_SQL_CONTRAPARTE = (
    "regexp_replace(regexp_replace(upper(coalesce(counterparty_name, "
    "regexp_replace(coalesce(description,''),'^.*?-\\s*',''))), "
    "'[^A-Z0-9 ]', ' ', 'g'), ' +', ' ', 'g')"
)

# Empresas do PRÓPRIO grupo: dinheiro entre CNPJs nossos não é despesa, é
# transferência. Sem esta regra a heurística de fornecedor sugeria "Fornecedor"
# para R$70.000 indo de uma empresa nossa para outra — sugestão errada com cara
# de certa, que é pior que não sugerir: o humano confirma em bloco e grava o erro.
_GRUPO = ("CONECTA MAIS", "CONECTAMAIS", "CONECTA PRO", "CONECTA ELETRONICA",
          "CONECTA PATRIMONIAL", "CONECTA MAIS REDES")

# SÓCIO: retirada, pró-labore, distribuição de lucro ou empréstimo. Precisa vir
# ANTES do teste de funcionário — o sócio também está em `employees`, e a regra
# sugeria "Salário — CLT" para pagamento ao dono. O enquadramento fino
# (pró-labore x distribuição x mútuo) muda o imposto e é decisão dele.
_SOCIO = ("JORDAN SANTOS DE JESUS", "JORDAN S DE JESUS", "JORDAN JESUS")

# PJ vem de `employees.status IN ('pj_ativo','pj_pendente')` — o banco já sabe
# quem é PJ, e a lista chumbada de primeiros nomes errava feio: "RUAN" casava
# com RUAN RODRIGUES FIGUEIREDO (AGENTE DE PORTARIA, CLT) em vez do Sidney Ruan
# Souza, e "RAMON" casava com FRANCISCO RAMON FARIAS (também CLT). Ambos iam
# virar pró-labore. Ver `e_pj` no SQL de listar_grupos.
_FOLHA_TERCEIRO = ("SOLIDES", "S LIDES", "SINETRAN")
_IMPOSTO = ("RECEITA FEDERAL", "CEF MATRIZ", "CAIXA ECONOMICA", "DARF", "GPS",
            "SIMPLES NACIONAL", "PGFN", "FGTS", "INSS", "PREVID", "SINDECOMPRESTS",
            "SINDICATO", "CONTRIB SINDICAL")

# Razão social: pagou empresa, é fornecedor. Serve de rede para os pequenos que
# não têm NFS-e tomada casada — melhor que jogar tudo em "diversos", que é
# desistir com aparência de organização.
_EMPRESA = (" LTDA", " S A", " SA", " S/A", " ME", " MEI", "EIRELI", "SERVICOS", "SERVICO",
            "DISTRIBUIDORA", "TELECOM", "COMERCIO", "TECNOLOGIA", "PAGAMENTOS", "INDUSTRIA",
            "SISTEMAS", "SUPERMERC", "ADVOGAD", "CONTABIL", "ASSESSORIA", "CONSULTORIA",
            "TRANSPORTE", "LOCADORA", "SEGURANCA", "ENGENHARIA", "MATERIAIS", "EQUIPAMENTOS",
            "SEGUROS", "CLINICA", "LABORATORIO", "POSTO ")

# Banco NÃO entra em _EMPRESA. Pagamento a banco quase nunca é "fornecedor de
# serviço": é tarifa, financiamento, consórcio ou fatura de cartão — e cada um vai
# para uma conta diferente. "ITAU UNIBANCO HOLDING S A" veio sugerido como
# Fornecedor e era a fatura do cartão que o Jordan usa para comprar material da
# empresa. Sugestão errada com cara de certa é pior que não sugerir: o humano
# confirma em bloco e grava o erro. Aqui a regra cala e devolve a decisão.
_BANCO = ("ITAU", "NUBANK", "NU PAGAMENTOS", "BRADESCO", "SANTANDER", "BANCO DO BRASIL",
          "BANCO C6", "C6 BANK", "BTG", "SICOOB", "SICREDI", "BANRISUL", "SAFRA",
          "PAGSEGURO", "MERCADO PAGO", "PICPAY", "WILL FINANCEIRA", "AGIBANK")
_TAXA = ("TARIFA", "TAXA", "IOF", "ANUIDADE", "PACOTE DE SERVICOS")

_RE_NAO_ALFA = re.compile(r"[^A-Za-z ]")


def _casa_nome(tabela: str, campo_alvo: str, onde: str = "TRUE") -> str:
    """EXISTS que casa primeiro E último nome do cadastro dentro da contraparte.

    `unaccent` porque o cadastro tem "Ramon Araújo" e o extrato traz "RAMON
    ARAUJO" — sem isso o Ú vira espaço na normalização e o nome nunca casa.
    Exigir os DOIS extremos evita o que já aconteceu: "SILVA" sozinho casava
    com centenas de pessoas.
    """
    return f"""EXISTS (
        SELECT 1 FROM {tabela} c WHERE c.nome IS NOT NULL AND length(c.nome) > 8
          AND {onde}
          AND {campo_alvo} LIKE '%' || split_part(unaccent(upper(c.nome)), ' ', 1) || '%'
          AND {campo_alvo} LIKE '%' || split_part(unaccent(upper(c.nome)), ' ',
                array_length(string_to_array(c.nome, ' '), 1)) || '%')"""


def _sugerir(contraparte: str, valor: float, e_funcionario: bool, tem_nfse: bool,
             e_diarista: bool = False, e_pj: bool = False) -> tuple[str | None, str]:
    """(categoria_sugerida, motivo). None = o sistema não sabe; decide o humano.

    Ordem importa: o teste mais específico primeiro. Um funcionário que também é
    PJ deve cair em PJ, não em salário.
    """
    c = (contraparte or "").upper()
    if any(g in c for g in _GRUPO):
        return "transferencia_interna", "outra empresa do grupo Conecta"
    if any(x in c for x in _SOCIO):
        return "socio", "favorecido é o sócio — enquadramento fino é decisão dele"
    if any(t in c for t in _IMPOSTO):
        return "imposto", "favorecido é órgão arrecadador"
    if any(t in c for t in _FOLHA_TERCEIRO):
        return "beneficio_vtvr", "operadora de VT/VR (Sólides/Sinetran)"
    if e_pj:
        return "pj_prolabore", "favorecido está cadastrado como PJ"
    if any(t in c for t in _TAXA):
        return "taxa_bancaria", "descrição de tarifa bancária"
    if any(b in c for b in _BANCO):
        # Vem ANTES de _EMPRESA e do teste de valor: sem isto, "ITAU UNIBANCO
        # HOLDING S A" caía em `fornecedor` por ser razão social de empresa.
        return None, "favorecido é banco — pode ser fatura de cartão, financiamento, consórcio ou tarifa; decide o humano"
    if abs(valor) == 32.0:
        return "beneficio_vtvr", "R$32,00 = VT + VR de diarista"
    if e_funcionario:
        return "salario", "favorecido é funcionário cadastrado"
    if e_diarista:
        return "diarista", "favorecido está no cadastro de diaristas"
    if tem_nfse:
        return "fornecedor", "há NFS-e tomada deste CNPJ"
    if any(t in c for t in _EMPRESA):
        return "fornecedor", "razão social de empresa"
    if abs(valor) < 50:
        return "diversos", "valor pequeno, sem enquadramento"
    return None, "sem regra — precisa de decisão humana"


async def listar_grupos(db: AsyncSession, *, minimo: float = 0.0, limite: int = 60) -> dict:
    """Saídas SEM classificação, agrupadas por contraparte, com sugestão."""
    rows = (await db.execute(text(f"""
        WITH sem AS (
            SELECT {_SQL_CONTRAPARTE} AS contraparte,
                   count(*) AS n, sum(abs(amount)) AS valor,
                   min(transaction_date)::date AS de, max(transaction_date)::date AS ate,
                   max(upper(regexp_replace(coalesce(counterparty_name,
                       regexp_replace(coalesce(description,''),'^.*?-\\s*','')),'[^A-Za-z ]','','g'))) AS alvo,
                   max(coalesce(counterparty_document,'')) AS doc
            FROM bank_transactions
            WHERE amount < 0 AND justificativa_categoria IS NULL
            GROUP BY 1
            HAVING sum(abs(amount)) >= :minimo
        )
        SELECT s.contraparte, s.n, s.valor, s.de, s.ate,
               {_casa_nome("employees", "s.alvo",
                           "c.status NOT IN ('pj_ativo','pj_pendente')")} AS e_func,
               {_casa_nome("employees", "s.alvo",
                           "c.status IN ('pj_ativo','pj_pendente')")} AS e_pj,
               {_casa_nome("diaria_diaristas", "s.contraparte")} AS e_diarista,
               EXISTS (SELECT 1 FROM nfse_tomadas_nacional t
                       WHERE upper(coalesce(t.prestador_nome,'')) <> ''
                         AND s.contraparte LIKE '%' || split_part(upper(t.prestador_nome),' ',1) || '%') AS tem_nfse
        FROM sem s
        ORDER BY s.valor DESC
        LIMIT :limite
    """), {"minimo": minimo, "limite": limite})).mappings().all()

    grupos = []
    for r in rows:
        cat, motivo = _sugerir(r["contraparte"], float(r["valor"]), r["e_func"],
                               r["tem_nfse"], r["e_diarista"], r["e_pj"])
        grupos.append({
            "contraparte": r["contraparte"].strip(),
            "movimentacoes": int(r["n"]),
            "valor": round(float(r["valor"]), 2),
            "periodo": f"{r['de']} a {r['ate']}",
            "sugestao": cat,
            "sugestao_label": dict(CATEGORIAS).get(cat, "—") if cat else "—",
            "motivo": motivo,
        })
    return {"grupos": grupos, "categorias": [{"value": k, "label": v} for k, v in CATEGORIAS]}


async def classificar_grupo(db: AsyncSession, *, contraparte: str, categoria: str,
                            responsavel: str) -> dict:
    """Aplica a categoria a TODAS as saídas sem classificação daquela contraparte.

    Só toca `amount < 0` e `justificativa_categoria IS NULL` — nunca reclassifica o
    que já foi decidido antes.
    """
    if categoria not in CATEGORIAS_VALIDAS:
        return {"ok": False, "erro": f"categoria inválida: {categoria!r}"}
    alvo = (contraparte or "").strip()
    if len(alvo) < 3:
        return {"ok": False, "erro": "contraparte muito curta para casar com segurança"}

    label = dict(CATEGORIAS)[categoria]
    r = (await db.execute(text(f"""
        UPDATE bank_transactions SET
            justificativa_categoria = :cat,
            justificativa = :just,
            justificativa_responsavel = :resp,
            justificativa_data = NOW(),
            updated_at = NOW()
        WHERE amount < 0 AND justificativa_categoria IS NULL
          AND trim({_SQL_CONTRAPARTE}) = trim(:alvo)
        RETURNING abs(amount)
    """), {"cat": categoria, "just": label, "resp": responsavel, "alvo": alvo})).fetchall()
    await db.commit()
    if not r:
        # Sucesso com 0 linhas é mentira educada: o usuário clica, lê "ok" e
        # acha que classificou. Aconteceu de verdade — a lista fazia strip() no
        # nome e o UPDATE comparava sem trim, então nunca casava.
        return {"ok": False, "erro": (f"nenhuma saída sem classificação encontrada para "
                                      f"{alvo[:40]!r} — o grupo pode já ter sido classificado")}
    total = round(sum(float(x[0]) for x in r), 2)
    return {"ok": True, "contraparte": alvo, "categoria": categoria, "categoria_label": label,
            "classificadas": len(r), "valor": total}


async def aplicar_sugestoes(db: AsyncSession, *, responsavel: str,
                            preview: bool = True) -> dict:
    """Aplica em massa as classificações que a REGRA já sabe.

    Grupo sem sugestão fica intocado — o "não sei" é resposta, e forçar categoria
    nele seria fabricar. `preview=True` é o padrão: gravar em massa sem ver antes
    foi o que quase marcou o sócio como CLT hoje.
    """
    dados = await listar_grupos(db, minimo=0.0, limite=5000)
    alvo = [g for g in dados["grupos"] if g["sugestao"]]

    # `listar_grupos` agrupa pela contraparte crua e faz strip() só na saída, então
    # " ACME" e "ACME" chegam como dois grupos que viram o MESMO UPDATE. O primeiro
    # leva as linhas dos dois, o segundo casa zero. Sem dedup aqui, o relatório
    # somava o grupo fantasma e informava mais do que gravou.
    vistos: set[str] = set()
    unicos = []
    for g in alvo:
        chave = g["contraparte"].strip().upper()
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(g)

    por_cat: dict[str, dict] = {}
    mov = 0
    valor = 0.0
    falhas = []
    for g in unicos:
        n, v = g["movimentacoes"], g["valor"]
        if not preview:
            r = await classificar_grupo(db, contraparte=g["contraparte"],
                                        categoria=g["sugestao"], responsavel=responsavel)
            if not r.get("ok"):
                falhas.append({"contraparte": g["contraparte"][:60], "erro": r.get("erro")})
                logger.warning("mutirão: %r não aplicado: %s", g["contraparte"][:40], r.get("erro"))
                continue
            # O que o banco gravou, não o que a lista previa.
            n, v = r["classificadas"], r["valor"]
        c = por_cat.setdefault(g["sugestao"], {"grupos": 0, "movimentacoes": 0, "valor": 0.0})
        c["grupos"] += 1
        c["movimentacoes"] += n
        c["valor"] = round(c["valor"] + v, 2)
        mov += n
        valor += v
    return {
        "modo": "preview" if preview else "aplicado",
        "grupos": sum(c["grupos"] for c in por_cat.values()),
        "movimentacoes": mov,
        "valor": round(valor, 2),
        "por_categoria": por_cat,
        "sem_sugestao": len(dados["grupos"]) - len(alvo),
        "falhas": falhas,
    }


# ═══════════════════ classificação pelo MEMO do Cora ═══════════════════
# O Cora deixa escrever uma justificativa na hora de pagar, e o Jordan JÁ escreve:
# 67% das saídas de agosto (74% do valor) vieram com memo. É a melhor fonte que
# existe — são as palavras dele, não uma heurística minha sobre o nome do
# favorecido. E ela denunciava erros: "Salario julho" (34 saídas, R$52.790,86)
# estava classificado como `(sem)`, `fornecedor` E `salario` ao mesmo tempo.
#
# A PRECEDÊNCIA é o que faz isso funcionar, e são dois grupos com regras opostas:
#
#  • NATUREZA (o que foi comprado) VENCE o cadastro. "Uber" e "Café treinamento"
#    pagos ao Eliziel viravam pró-labore dele porque ele é PJ — mas café é café
#    independentemente de quem recebeu.
#  • RELAÇÃO (salário, pró-labore) PERDE para o cadastro. O Jordan escreve
#    "Salario" ao pagar a Pyetra, que é PJ: o vínculo é fato do cadastro, a
#    palavra é coloquial. Aqui o cadastro manda.
_MEMO_NATUREZA: tuple[tuple[tuple[str, ...], str], ...] = (
    (("UBER", "99 TECN", "TAXI", "COMBUSTIVEL", "GASOLINA"), "reembolso"),
    (("CAFE", "LANCHE", "ALMOCO", "AGUA", "GARRAFAO", "IFOOD"), "reembolso"),
    (("MATERIAL", "MATERIAIS", "FERRAMENTA"), "reembolso"),
    (("VT/VR", "VT E VR", "VALE TRANSPORTE", "VALE ALIMENTACAO", "VALE REFEICAO"), "beneficio_vtvr"),
    (("PLANO CORA", "TARIFA", "ANUIDADE"), "taxa_bancaria"),
)
_MEMO_RELACAO: tuple[tuple[tuple[str, ...], str], ...] = (
    # "SALRIO" sem o A é digitação real do extrato, não engano meu.
    (("SALARIO", "SALARIO", "SALRIO", "DIFERENCA SALARIAL", "RESCISAO", "FERIAS",
      "13 SALARIO", "DECIMO TERCEIRO"), "salario"),
    (("ADIANTAMENTO", "ADIANTANENTO", "VALE "), "adiantamento"),
    (("DIARIA", "DIARIAS", "COBERTURA"), "diarista"),
)


def _memo(descricao: str) -> str:
    """Só o que a pessoa escreveu — sem o prefixo do conector."""
    d = _RE_ACENTO.sub(lambda m: _SEM_ACENTO.get(m.group(0), m.group(0)),
                       (descricao or "").upper())
    return re.sub(r"^\[CORA\]\s*", "", d).strip()


_SEM_ACENTO = {"Á": "A", "À": "A", "Â": "A", "Ã": "A", "É": "E", "Ê": "E", "Í": "I",
               "Ó": "O", "Ô": "O", "Õ": "O", "Ú": "U", "Ç": "C"}
_RE_ACENTO = re.compile("[" + "".join(_SEM_ACENTO) + "]")


def sugerir_por_memo(descricao: str, *, e_pj: bool = False,
                     favorecido: str = "") -> tuple[str | None, str]:
    """(categoria, motivo) a partir do memo. None = o memo não diz.

    `favorecido` decide reembolso × fornecedor: reembolso é devolver dinheiro a
    uma PESSOA que adiantou. "Garrafão de água" pago à SILVA DISTRIBUIDORA é
    compra direta de fornecedor — a mesma palavra, natureza diferente conforme
    quem recebeu.
    """
    m = _memo(descricao)
    if not m or m in ("PIX", "TED", "PAGAMENTO", "TRANSFERENCIA"):
        return None, "sem memo — nada escrito na hora de pagar"
    e_empresa = any(t in (favorecido or "").upper() for t in _EMPRESA)
    for termos, cat in _MEMO_NATUREZA:
        if any(t in m for t in termos):
            if cat == "reembolso" and e_empresa:
                return "fornecedor", f'memo diz "{m[:34]}" — compra direta, favorecido é empresa'
            return cat, f'memo diz "{m[:40]}" — natureza da despesa'
    if e_pj:
        # cadastro vence a palavra: PJ recebendo é pró-labore mesmo que o memo
        # diga "salário"
        return None, "favorecido é PJ no cadastro — o vínculo decide, não a palavra"
    for termos, cat in _MEMO_RELACAO:
        if any(t in m for t in termos):
            return cat, f'memo diz "{m[:40]}"'
    return None, f'memo "{m[:40]}" não tem regra — decide o humano'
