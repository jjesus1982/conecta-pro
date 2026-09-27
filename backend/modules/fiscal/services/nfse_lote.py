"""DGX AA4 — as 14 notas de setembro que o dono digita à mão, PROPOSTAS pela tela.

O que o dono faz hoje
---------------------
Abre `Cronograma de Emissão de Notas Conectamais 2026.ods`, e digita 14 notas por mês no
portal do fisco: tomador, CNPJ, valor bruto, tipo de serviço e um parágrafo de descrição
que traz, por dentro, a conta da retenção de INSS e os dados bancários da empresa certa.

O que esta camada faz
---------------------
**Propõe** as 14 — tomador, valor, código de serviço, empresa emitente, descrição montada
e o INSS calculado — e para por aí. **Cada nota exige o clique dele.** Nada sai sozinho:
não há laço que transmita, não há agendamento que emita. O agendamento desta frente é o
da conciliação (que só LÊ o fisco), nunca o da emissão.

De onde vem cada número da proposta, e por que três deles discordam
-------------------------------------------------------------------
**Valor bruto, tomador e descrição:** do cronograma do dono (`fonte='cronograma_ods…'`).

**Código de serviço:** do que o FISCO já registrou para aquele tomador —
`nfse_emitidas_nacional`, a nota mais recente. Só quando não há precedente é que vale o
rótulo do cronograma. Os dois aparecem na tela, com a fonte de cada um, porque **eles
discordam em casos reais**: o mesmo texto «CONTRATO DE MANUTENÇÃO DE CFTV/CERCA/PORTÕES/
CANCELAS» saiu como **14.01.01** na NFS-e 116 (Villa dos Pássaros) e como **14.06.01** na
NFS-e 120 (Parise Village), as duas em 08/2026 e as duas pela Eletrônica.

**Empresa emitente:** pelos dados bancários que o próprio dono escreveu na descrição —
CORA 403 / ag. 0001 / c. 7382527-7 é a **Patrimonial**; INTER 077 / ag. 0001 /
c. 37099007-2 é a **Eletrônica**. Uma linha do cronograma não traz banco nenhum
(Prime Arena, R$ 1.084,50): fica **sem fonte** e a tela diz isso.

**INSS (11%, Art. 31 da Lei 9.711/98):** a base é o valor bruto **menos** vale-alimentação
e vale-transporte do mês. Este sistema tem os dois, por funcionário e por competência
(`folha_beneficio_conferencia`), ligados ao cliente por `employee_alocacoes → condominios
→ clients`. **E eles não batem com o que o dono digitou.** Medido em 24/09/2026 para
08/2026:

    Prime Arena    VA folha 2.090,00 · dono 1.804,00   VT folha (vazio) · dono   880,00
    Laranjeiras    VA folha 2.816,00 · dono 2.552,00   VT folha (vazio) · dono 1.136,00
    Ideal Flores   VA folha 5.082,00 · dono 2.244,00   VT folha 2.090,00 · dono 2.160,00

O VT só está valorizado em UM dos oito condomínios — nos outros a linha existe com o
total vazio. Então a tela mostra **as duas contas lado a lado** e não escolhe: quem
escolhe é o dono, que assina a nota.

**E há um terceiro árbitro, melhor que os dois:** o que o fisco de fato reteve na nota do
mês anterior para o mesmo tomador e o mesmo serviço. Nas cinco notas da Patrimonial de
08/2026 a retenção foi **11% do bruto, sem dedução nenhuma** — 12.061,50 → 1.326,76;
28.694,30 → 3.156,37; 33.538,33 → 3.689,21; 25.592,71 → 2.815,20; 8.346,70 → 918,13. Nove
das quatorze linhas do cronograma também não trazem bloco de dedução. A tela mostra esse
histórico ao lado da proposta.

O que esta camada NÃO faz
-------------------------
  · **não transmite.** Quem transmite é `nfse_emissao.emitir`, uma nota por clique;
  · não arredonda por conta própria o centavo do INSS. As notas do fisco mostram os dois
    comportamentos (3.689,2163 virou 3.689,21 por truncamento; 2.815,1981 virou 2.815,20
    por arredondamento) — porque `vRetCP` é **digitado** na DPS, não calculado pelo órgão.
    A proposta arredonda meio-para-cima e **marca** o centavo como coisa do dono;
  · não cria cliente, não cria contrato, não mexe na folha.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

#: Art. 31 da Lei 9.711/98 — cessão de mão de obra. Fonte: o texto que o próprio dono
#: escreve na descrição de cada nota e os 5 DANFSe da Patrimonial de 08/2026.
ALIQUOTA_INSS = Decimal("0.11")

_CNPJ_PATRIMONIAL = "66014833000110"
_CNPJ_ELETRONICA = "35710481000103"

#: Como o cronograma identifica a empresa: pelos dados bancários no corpo da descrição.
_BANCO_DA_EMPRESA = (
    ("7382527-7", _CNPJ_PATRIMONIAL, "BANCO CORA SCD 403 / ag. 0001 / c. 7382527-7"),
    ("37099007-2", _CNPJ_ELETRONICA, "BANCO INTER 077 / ag. 0001 / c. 37099007-2"),
)

#: Rótulo do cronograma → código de tributação nacional. Só vale quando não há precedente
#: do fisco para o tomador. `None` = o rótulo não decide sozinho (ver docstring).
_CODIGO_POR_ROTULO: dict[str, str | None] = {
    "agentes de portaria": "110201",
    "agentes de portaria e limpeza": None,  # duas naturezas numa nota: o fisco emitiu SEPARADAS
    "limpeza": "071002",
    "servicos gerais": "071002",
    "manutencao": "140101",
    "instalacao/manutencao": "140101",
    "instalacao/portaria remota": "140601",
}

_DDL = (
    "CREATE TABLE IF NOT EXISTS nfse_cronograma ("
    " id bigserial PRIMARY KEY,"
    " competencia varchar(7) NOT NULL,"
    " ordem integer NOT NULL,"
    " tomador_cnpj varchar(14) NOT NULL,"
    " tomador_nome text NOT NULL,"
    " valor_bruto numeric(15,2) NOT NULL,"
    " rotulo_servico text NOT NULL,"
    " descricao text NOT NULL,"
    " empresa_cnpj varchar(14),"
    " empresa_fonte text,"
    " estado varchar(16) NOT NULL DEFAULT 'proposta',"
    " nfse_id uuid,"
    " fonte text NOT NULL,"
    " criado_em timestamp NOT NULL DEFAULT now())",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_nfse_cronograma_linha ON nfse_cronograma (competencia, ordem)",
)

#: As 14 linhas de 09/2026, transcritas de `uploads/_entrada/NFs/Cronograma de Emissão de
#: Notas Conectamais 2026.ods`, aba «Conectamais». Valor e descrição são do dono, letra
#: por letra. O CNPJ do tomador é o que está no rótulo da coluna «Tomador/CNPJ».
_SEED_2026_09: tuple[tuple[int, str, str, str, str, str], ...] = (
    (
        1,
        "47405340000166",
        "Cond. Prime Arena",
        "29600.00",
        "Agentes de portaria e Limpeza",
        "Mão de obra terceirizada para agentes de portaria e limpeza. Período: 01/09/2026 a 30/09/2026. "
        "Valor bruto: R$ 29.600,00. DEDUÇÕES DA BASE DE CÁLCULO: R$ 2.684,00 QUANTIDADE DE FUNCIONÁRIOS NO "
        "CONTRATO: 08 Vale Alimentação 08/2026: R$ 1.804,00 Vale Transporte 08/2026: R$ 880,00 BASE DE "
        "CÁLCULO PARA RETENÇÃO DE INSS: R$ 26.916,00 Aplicada retenção do INSS (11%) conforme o Art. 31 da "
        "Lei n. 9.711/98. VALOR DA RETENÇÃO DE INSS (11%): R$ 2.960,76 Prazo: Até 10/10/2026.",
    ),
    (
        2,
        "47405340000166",
        "Cond. Prime Arena",
        "3879.60",
        "Manutenção",
        "REFERENTE A PRESTACAO DE SERVICOS DE MANUTENCAO DE PISCINA E JARDINAGEM NO MÊS DE SETEMBRO. "
        "Prazo: 10/10/2026. BANCO INTER: 077 AGÊNCIA: 0001 CONTA: 37099007-2 CHAVE PIX: CNPJ "
        "35.710.481/0001-03. Aplicada retenção do INSS (11%) conforme o Art. 31 da Lei n. 9.711/98.",
    ),
    (
        3,
        "24632786000128",
        "Res Laranjeiras Village",
        "42544.50",
        "Agentes de portaria",
        "Mão de obra terceirizada para agentes de portaria. Período: 01/09/2026 a 30/09/2026. Valor bruto: "
        "R$ 42.544,50. DEDUÇÕES DA BASE DE CÁLCULO: R$ 3.688,00 QUANTIDADE DE FUNCIONÁRIOS NO CONTRATO: 08 "
        "Vale Alimentação 08/2026: R$ 2.552,00 Vale Transporte 08/2026: R$ 1.136,00 BASE DE CÁLCULO PARA "
        "RETENÇÃO DE INSS: R$ 38.856,50 Aplicada retenção do INSS (11%) conforme o Art. 31 da Lei n. "
        "9.711/98. VALOR DA RETENÇÃO DE INSS (11%): R$ 4.274,21 Prazo: Até 10/10/2026. DADOS PARA PAGAMENTO: "
        "BANCO CORA SCD: 403 AGÊNCIA: 0001 CONTA: 7382527-7 CHAVE PIX: CNPJ 66.014.833/0001-10.",
    ),
    (
        4,
        "23147782000191",
        "Cond Ideal Flores da Cidade",
        "65842.42",
        "Agentes de portaria e Limpeza",
        "Mão de obra terceirizada para agentes de portaria e limpeza. Período: 01/09/2026 a 30/09/2026. "
        "Valor bruto: R$ 65.842,42. DEDUÇÕES DA BASE DE CÁLCULO: R$ 6.648,00 QUANTIDADE DE FUNCIONÁRIOS NO "
        "CONTRATO: 12 Vale Alimentação 08/2026: R$ 2.244,00 Vale Transporte 08/2026: R$ 2.160,00 BASE DE "
        "CÁLCULO PARA RETENÇÃO DE INSS: R$ 59.194,42 Aplicada retenção do INSS (11%) conforme o Art. 31 da "
        "Lei n. 9.711/98. VALOR DA RETENÇÃO DE INSS (11%): R$ 6.511,62 Prazo: Até 15/10/2026. DADOS PARA "
        "PAGAMENTO: BANCO CORA SCD: 403 AGÊNCIA: 0001 CONTA: 7382527-7 CHAVE PIX: CNPJ 66.014.833/0001-10.",
    ),
    (
        5,
        "52605708000170",
        "Cond. Mirante das Flores",
        "12061.50",
        "Limpeza",
        "REFERENTE A PRESTACAO DE SERVICOS DE LIMPEZA NO MES DE SETEMBRO. DADOS PARA PAGAMENTO: BANCO CORA "
        "SCD: 403 AGÊNCIA: 0001 CONTA: 7382527-7 CHAVE PIX: CNPJ 66.014.833/0001-10.",
    ),
    (
        6,
        "52605708000170",
        "Cond. Mirante das Flores",
        "28694.30",
        "Agentes de portaria",
        "REFERENTE A PRESTACAO DE SERVICOS DE PORTARIA NO MES DE SETEMBRO. DADOS PARA PAGAMENTO: BANCO CORA "
        "SCD: 403 AGÊNCIA: 0001 CONTA: 7382527-7 CHAVE PIX: CNPJ 66.014.833/0001-10.",
    ),
    (
        7,
        "13221953000121",
        "Cond. Res. Villa dos Passaros",
        "33538.33",
        "Agentes de Portaria",
        "REFERENTE AO FORNECIMENTO DO SERVIÇO DE AGENTE DE PORTARIA E AUXILIAR DE SERVICOS GERAIS NO MÊS DE "
        "SETEMBRO. DADOS PARA PAGAMENTO: BANCO CORA SCD: 403 AGÊNCIA: 0001 CONTA: 7382527-7 CHAVE PIX: CNPJ "
        "66.014.833/0001-10.",
    ),
    (
        8,
        "13221953000121",
        "Cond. Res. Villa dos Passaros",
        "3800.00",
        "Instalação/Manutenção",
        "REFERENTE AO CONTRATO DE MANUTENÇÃO DE CFTV/CERCA/PORTÕES/CANCELAS NO MÊS DE SETEMBRO. DADOS PARA "
        "PAGAMENTO: BANCO INTER: 077 AGÊNCIA: 0001 CONTA: 37099007-2 CHAVE PIX: CNPJ 35.710.481/0001-03",
    ),
    (
        9,
        "47405340000166",
        "Cond. Prime Arena",
        "1084.50",
        "Manutenção",
        "Referente a manutenção do motor de portão de entrada.",
    ),
    (
        10,
        "04911208000113",
        "Cond. do Edif. Michelangelo",
        "8346.70",
        "Serviços gerais",
        "REFERENTE AO FORNECIMENTO DE SERVICO GERAIS NO MÊS SETEMBRO. DADOS PARA PAGAMENTO: BANCO CORA SCD: "
        "403 AGÊNCIA: 0001 CONTA: 7382527-7 CHAVE PIX: CNPJ 66.014.833/0001-10.",
    ),
    (
        11,
        "02153384000108",
        "Cond. Villa Dei Fiori",
        "25592.71",
        "Agentes de Portaria",
        "REFERENTE AO FORNECIMENTO DO SERVIÇO DE AGENTE DE PORTARIA E AUXILIAR DE SERVICOS GERAIS NO MÊS DE "
        "SETEMBRO. DADOS PARA PAGAMENTO: BANCO CORA SCD: 403 AGÊNCIA: 0001 CONTA: 7382527-7 CHAVE PIX: CNPJ "
        "66.014.833/0001-10.",
    ),
    (
        12,
        "08063476000183",
        "Cond. Res. Green Hills",
        "500.00",
        "Instalação/Manutenção",
        "REFERENTE AO CONTRATO DE MANUTENÇÃO DE CFTV/CERCA/PORTÕES/CANCELAS NO MÊS DE SETEMBRO. BANCO INTER: "
        "077 AGÊNCIA: 0001 CONTA: 37099007-2 CHAVE PIX: CNPJ 35.710.481/0001-03",
    ),
    (
        13,
        "34857941000168",
        "Cond. Res. Parise Village",
        "2000.00",
        "Instalação/Manutenção",
        "REFERENTE AO CONTRATO DE MANUTENÇÃO DE CFTV/CERCA/PORTÕES/CANCELAS NO MÊS DE SETEMBRO. BANCO INTER: "
        "077 AGÊNCIA: 0001 CONTA: 37099007-2 CHAVE PIX: CNPJ 35.710.481/0001-03.",
    ),
    (
        14,
        "00736037000182",
        "Cond. Parq. Res. Gelain",
        "6000.00",
        "Instalação/Portaria Remota",
        "REFERENTE À PRESTAÇÃO DE SERVIÇOS DO CONTRATO DE SISTEMA DE SEGURANÇA ELETRÔNICA, RELATIVOS AO "
        "SERVIÇO DE PORTARIA REMOTA NO MÊS DE SETEMBRO. TOTAL DA NOTA FISCAL: R$ 6.000,00. DADOS PARA "
        "PAGAMENTO: BANCO INTER: 077 AGÊNCIA: 0001 CONTA: 37099007-2 CHAVE PIX: CNPJ 35.710.481/0001-03.",
    ),
)

_FONTE_SEED = (
    "uploads/_entrada/NFs/Cronograma de Emissão de Notas Conectamais 2026.ods, aba «Conectamais», "
    "linhas 3–16 — subido pelo dono em 24/09/2026."
)


def _sem_acento(s: str) -> str:
    tab = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ", "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC"
    )
    return s.translate(tab).strip().lower()


def empresa_do_cronograma(descricao: str) -> tuple[str | None, str]:
    """Qual CNPJ emite, lido dos dados bancários que o dono escreveu na descrição.

    Sem banco na descrição não há fonte — devolve `None` e a tela diz «sem fonte».
    Adivinhar aqui seria escolher o CNPJ de um documento fiscal no escuro.
    """
    for conta, cnpj, rotulo in _BANCO_DA_EMPRESA:
        if conta in (descricao or ""):
            return cnpj, f"dados bancários na descrição do cronograma: {rotulo}"
    return None, "sem fonte — a linha do cronograma não traz dados bancários"


def codigo_por_rotulo(rotulo: str) -> str | None:
    return _CODIGO_POR_ROTULO.get(_sem_acento(rotulo))


def inss_de(base: Decimal) -> Decimal:
    """11% da base, meio-para-cima, 2 casas. O centavo é decisão do dono — ver docstring."""
    return (base * ALIQUOTA_INSS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


#: `_ensure` roda o DDL UMA vez por processo E só quando falta alguma coisa.
#:
#: Medido em 24/09/2026 no sandbox: `ALTER TABLE … ADD COLUMN IF NOT EXISTS` pede
#: **AccessExclusiveLock mesmo quando a coluna já existe** — ele não é de graça. Dois
#: processos fazendo isso em tabelas diferentes, em ordens que se cruzam, deram
#: `DeadlockDetectedError`; e uma sessão `idle in transaction` de outro agente segurou a
#: fila por 11 minutos. Com 8 workers de celery subindo juntos depois de um deploy, isso
#: não é hipótese.
#:
#: Então: primeiro uma pergunta barata ao catálogo (`to_regclass` + `information_schema`,
#: que não pegam lock nenhum). Se o DDL já está aplicado, ele **não é pedido**. A flag de
#: processo evita repetir até a pergunta. Nada disso substitui a idempotência do SQL — ela
#: continua lá para quando o DDL de fato precisar rodar.
_ddl_aplicado = False

#: `lock_timeout` para o ALTER não ficar pendurado atrás de transação alheia: falhar em 5s
#: e tentar de novo no próximo acesso é melhor que travar uma tela.
_LOCK_TIMEOUT = "SET LOCAL lock_timeout = '5s'"


async def _ensure(db: AsyncSession) -> None:
    global _ddl_aplicado
    from modules.fiscal.services import nfse_parametros as par

    await par._ensure(db)
    if _ddl_aplicado:
        return
    if (await db.execute(sqltext("SELECT to_regclass('public.nfse_cronograma') IS NOT NULL"))).scalar():
        _ddl_aplicado = True
    else:
        await db.execute(sqltext(_LOCK_TIMEOUT))
        for sql in _DDL:
            await db.execute(sqltext(sql))
    for ordem, cnpj, nome, valor, rotulo, descricao in _SEED_2026_09:
        emp, emp_fonte = empresa_do_cronograma(descricao)
        await db.execute(
            sqltext(
                "INSERT INTO nfse_cronograma"
                " (competencia, ordem, tomador_cnpj, tomador_nome, valor_bruto, rotulo_servico,"
                "  descricao, empresa_cnpj, empresa_fonte, fonte)"
                " VALUES ('2026-09', :o, :c, :n, :v, :r, :d, :e, :ef, :f)"
                " ON CONFLICT (competencia, ordem) DO NOTHING"
            ),
            {
                "o": ordem,
                "c": cnpj,
                "n": nome,
                "v": valor,
                "r": rotulo,
                "d": descricao,
                "e": emp,
                "ef": emp_fonte,
                "f": _FONTE_SEED,
            },
        )
    _ddl_aplicado = True
    await db.commit()


# ---------------------------------------------------------------------------
# A fonte das linhas: CONTRATO ativo, não planilha transcrita
# ---------------------------------------------------------------------------


async def semear_de_contratos(db: AsyncSession, competencia: str) -> dict[str, Any]:
    """Cria a linha do cronograma de cada CONTRATO ativo e vigente na competência.

    ## Por que isto existe

    Até 27/09/2026 a única fonte do que virava nota era `_SEED_2026_09` — 14 linhas de
    Python transcritas à mão da planilha `.ods` do dono. `propor()` fazia um SELECT em
    `nfse_cronograma` e **nunca tocava em `contracts`**. As consequências, medidas:

      • **Só existia seed de setembro.** Em 01/10/2026 o cronograma estaria VAZIO e nada
        seria proposto — e é justamente em outubro que o faturamento passa 100% para cá.
      • **Contrato novo era invisível.** O Green Hills (CTR-2026-00019, R$ 22.100/mês,
        ativo desde 01/09) não tinha linha; a linha 12 do cronograma descrevia o contrato
        VELHO dele (R$ 500,00, da Eletrônica, hoje `terminated`).
      • **A planilha não sabe de que mês nem de que empresa é.** A coluna de data diz
        `XX/XX` em todas as linhas, o cabeçalho diz «Conectamais Eletrônica» e a lista
        mistura clientes das duas — a empresa era adivinhada lendo a descrição
        (`empresa_do_cronograma`), pelos dados bancários no texto.
      • **Ela carrega duas versões do mesmo valor.** As abas `Conectamais` e
        `Cópia_de_Conectamais` só diferem no Mirante limpeza: R$ 12.061,50 numa,
        R$ 13.561,50 na outra, sem dizer qual vale.

    A inversão: **o contrato passa a ser a fonte**; o cronograma continua existindo como a
    lista de EXCEÇÕES (valor diferente do contrato, empresa diferente, não faturar este
    mês), cada uma com motivo escrito. Era o contrário, e por isso um contrato novo
    simplesmente não aparecia.

    ## O que ele respeita

    `contracts.grace_period_days` — campo que existia preenchido (Green Hills, 90 dias) e
    que **nenhuma lógica de faturamento lia** em 26/09/2026. Contrato em carência não gera
    linha: gerar seria propor uma nota que o contrato proíbe.

    ## O que ele NÃO faz

    Não emite, não sobrescreve linha existente (`ON CONFLICT DO NOTHING`) e não apaga o que
    foi transcrito à mão. Uma linha do dono com valor combinado por fora continua valendo —
    a divergência entre ela e o contrato é o que `checar_cronograma_vs_contrato` acusa.
    """
    await _ensure(db)
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    primeiro = date(ano, mes, 1)
    ultimo = date(ano + mes // 12, mes % 12 + 1, 1) - timedelta(days=1)

    linhas = (
        (
            await db.execute(
                sqltext(r"""
            SELECT c.contract_number, c.monthly_value, c.start_date,
                   coalesce(c.grace_period_days, 0) AS carencia,
                   coalesce(c.name, 'Prestação de serviços') AS rotulo,
                   regexp_replace(coalesce(cl.document_number,''), '\D', '', 'g') AS tomador_cnpj,
                   coalesce(cl.name, '(sem nome)') AS tomador_nome,
                   regexp_replace(coalesce(e.cnpj,''), '\D', '', 'g') AS empresa_cnpj
              FROM contracts c
              JOIN clients cl ON cl.id = c.client_id
              JOIN empresas e ON e.id = c.empresa_id
             WHERE c.status = 'active'
               AND coalesce(c.monthly_value, 0) > 0
               AND c.start_date <= :ultimo
               AND (c.end_date IS NULL OR c.end_date >= :primeiro)
             ORDER BY c.monthly_value DESC
        """),
                {"primeiro": primeiro, "ultimo": ultimo},
            )
        )
        .mappings()
        .all()
    )

    proxima = (
        await db.execute(
            sqltext("SELECT coalesce(max(ordem), 0) FROM nfse_cronograma WHERE competencia = :c"),
            {"c": competencia},
        )
    ).scalar() or 0

    criadas, em_carencia, ja_tinha = 0, [], 0
    for r in linhas:
        fim_carencia = r["start_date"] + timedelta(days=int(r["carencia"]))
        if r["carencia"] and ultimo < fim_carencia:
            em_carencia.append(
                {
                    "contrato": r["contract_number"],
                    "tomador": r["tomador_nome"],
                    "valor": float(r["monthly_value"]),
                    "primeira_nota_a_partir_de": str(fim_carencia),
                }
            )
            continue
        existe = (
            await db.execute(
                sqltext(
                    "SELECT 1 FROM nfse_cronograma"
                    " WHERE competencia = :c AND tomador_cnpj = :t"
                    "   AND round(valor_bruto, 2) = round(CAST(:v AS numeric), 2)"
                ),
                {"c": competencia, "t": r["tomador_cnpj"], "v": r["monthly_value"]},
            )
        ).first()
        if existe:
            ja_tinha += 1
            continue
        proxima += 1
        await db.execute(
            sqltext(
                "INSERT INTO nfse_cronograma"
                " (competencia, ordem, tomador_cnpj, tomador_nome, valor_bruto, rotulo_servico,"
                "  descricao, empresa_cnpj, empresa_fonte, fonte)"
                " VALUES (:c, :o, :t, :n, :v, :r, :d, :e, :ef, :f)"
                " ON CONFLICT (competencia, ordem) DO NOTHING"
            ),
            {
                "c": competencia,
                "o": proxima,
                "t": r["tomador_cnpj"],
                "n": r["tomador_nome"],
                "v": r["monthly_value"],
                "r": r["rotulo"],
                # A descrição sai do rótulo do contrato; `propor()` a enriquece depois com
                # o bloco de INSS, VA e VT da folha (`montar_descricao`). O texto rico da
                # planilha não se perde: linha transcrita à mão não é sobrescrita.
                "d": f"{r['rotulo']}. Período: {primeiro:%d/%m/%Y} a {ultimo:%d/%m/%Y}.",
                "e": r["empresa_cnpj"],
                # A empresa vem do CONTRATO, não de adivinhar pelos dados bancários no
                # texto da descrição, que é o que `empresa_do_cronograma` fazia.
                "ef": f"contrato {r['contract_number']}",
                "f": "contrato",
            },
        )
        criadas += 1
    await db.commit()
    return {
        "competencia": competencia,
        "contratos_ativos": len(linhas),
        "linhas_criadas": criadas,
        "ja_existiam": ja_tinha,
        "em_carencia": em_carencia,
    }


# ---------------------------------------------------------------------------
# VA e VT da folha, por tomador e competência
# ---------------------------------------------------------------------------


async def beneficios_por_tomador(db: AsyncSession, competencia: str) -> dict[str, dict[str, Any]]:
    """VA e VT somados por CNPJ do tomador, na competência (AAAA-MM).

    O caminho é `folha_beneficio_conferencia → employee_alocacoes → condominios → clients`.
    A alocação é filtrada por **vigência na competência**, não por `ativo`: quem trocou de
    posto depois entraria no cliente errado se a régua fosse o estado de hoje.

    `vt` volta `None` quando a folha tem a linha de VT mas sem valor — que é o caso de
    sete dos oito condomínios em 08/2026. `None` NÃO é zero: zero afirmaria que não houve
    vale-transporte, e o que houve foi ausência de dado.
    """
    linhas = (
        (
            await db.execute(
                sqltext(
                    "SELECT regexp_replace(cl.document_number,'\\D','','g') AS cnpj,"
                    "  sum(f.total) FILTER (WHERE f.beneficio = 'VR') AS va,"
                    "  sum(f.total) FILTER (WHERE f.beneficio = 'VT') AS vt,"
                    "  count(*) FILTER (WHERE f.beneficio = 'VT' AND f.total IS NULL) AS vt_sem_valor,"
                    "  count(DISTINCT f.employee_id) AS pessoas"
                    " FROM folha_beneficio_conferencia f"
                    " JOIN employee_alocacoes a ON a.employee_id = f.employee_id"
                    "   AND a.data_inicio <= (date_trunc('month', f.competencia) + interval '1 month -1 day')::date"
                    "   AND (a.data_fim IS NULL OR a.data_fim >= date_trunc('month', f.competencia)::date)"
                    " JOIN condominios co ON co.id = a.condominio_id"
                    " JOIN clients cl ON cl.id = co.client_id"
                    " WHERE to_char(f.competencia,'YYYY-MM') = :comp"
                    " GROUP BY 1"
                ),
                {"comp": competencia},
            )
        )
        .mappings()
        .all()
    )
    return {r["cnpj"]: dict(r) for r in linhas}


async def precedente_do_tomador(db: AsyncSession, cnpj_tomador: str) -> dict[str, Any] | None:
    """A última nota que o FISCO registrou para este tomador: código, empresa e retenção.

    É o melhor árbitro que existe para «qual código usar» e «quanto reter» — melhor que o
    rótulo do cronograma e melhor que a folha, porque é o que de fato saiu.
    """
    r = (
        (
            await db.execute(
                sqltext(
                    "SELECT n.numero, n.competencia, n.codigo_servico, n.valor_servicos, n.inss_retido,"
                    "  regexp_replace(e.cnpj,'\\D','','g') AS empresa_cnpj, e.slug"
                    " FROM nfse_emitidas_nacional n JOIN empresas e ON e.id = n.empresa_id"
                    " WHERE n.tomador_cnpj = :c AND NOT coalesce(n.cancelada, false)"
                    " ORDER BY n.competencia DESC, n.numero::int DESC LIMIT 1"
                ),
                {"c": cnpj_tomador},
            )
        )
        .mappings()
        .first()
    )
    return dict(r) if r else None


async def propor(db: AsyncSession, competencia: str = "2026-09") -> list[dict[str, Any]]:
    """As notas da competência, prontas para o dono conferir e transmitir uma a uma.

    Nada aqui transmite. Cada dicionário devolvido é uma PROPOSTA, com a fonte de cada
    campo e, onde as fontes discordam, as duas versões lado a lado.
    """
    await _ensure(db)

    # O CONTRATO é a fonte. Antes disto, `propor` fazia um único SELECT em
    # `nfse_cronograma` e nunca tocava em `contracts`: a tabela vinha de 14 linhas de
    # Python transcritas à mão da planilha do dono, e **só existia seed de setembro/2026**.
    # Em 01/10 o cronograma estaria vazio e nada seria proposto — justamente o mês em que
    # o faturamento passa 100% para cá. E contrato novo era invisível: o Green Hills,
    # ativo desde 01/09, não tinha linha nenhuma.
    #
    # `semear_de_contratos` é idempotente e NÃO sobrescreve linha existente: o que o dono
    # transcreveu à mão continua valendo, e a divergência entre a linha e o contrato é o
    # que `checar_cronograma_vs_contrato` acusa em vez de resolver em silêncio.
    await semear_de_contratos(db, competencia)

    from modules.fiscal.services.nfse_parametros import nbs_de, parametros_de

    # Benefícios da competência ANTERIOR — é o que o dono usa na descrição («Vale
    # Alimentação 08/2026» numa nota de setembro) e é como o contrato é faturado.
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    anterior = f"{ano - 1 if mes == 1 else ano:04d}-{12 if mes == 1 else mes - 1:02d}"
    benef = await beneficios_por_tomador(db, anterior)

    linhas = (
        (
            await db.execute(
                sqltext("SELECT * FROM nfse_cronograma WHERE competencia = :c ORDER BY ordem"),
                {"c": competencia},
            )
        )
        .mappings()
        .all()
    )

    fora: list[dict[str, Any]] = []
    for ln in linhas:
        bruto = Decimal(str(ln["valor_bruto"]))
        b = benef.get(ln["tomador_cnpj"]) or {}
        va = Decimal(str(b["va"])) if b.get("va") is not None else None
        vt = Decimal(str(b["vt"])) if b.get("vt") is not None else None
        deducao = (va or Decimal(0)) + (vt or Decimal(0))
        prec = await precedente_do_tomador(db, ln["tomador_cnpj"])

        por_rotulo = codigo_por_rotulo(ln["rotulo_servico"])
        codigo = (prec or {}).get("codigo_servico") or por_rotulo
        fonte_codigo = (
            f"última nota do fisco para este tomador (nº {prec['numero']}, {prec['competencia']})"
            if prec and prec.get("codigo_servico")
            else (f"rótulo «{ln['rotulo_servico']}» do cronograma" if por_rotulo else "SEM FONTE")
        )

        empresa_cnpj = ln["empresa_cnpj"]
        empresa_fonte = ln["empresa_fonte"]
        if not empresa_cnpj and prec:
            empresa_cnpj = prec["empresa_cnpj"]
            empresa_fonte = f"sem banco na descrição — sugerido pela última nota do tomador ({prec['slug']})"
        par = await parametros_de(db, empresa_cnpj) if empresa_cnpj else None

        fora.append(
            {
                "id": ln["id"],
                "ordem": ln["ordem"],
                "competencia": competencia,
                "tomador_cnpj": ln["tomador_cnpj"],
                "tomador_nome": ln["tomador_nome"],
                "valor_bruto": float(bruto),
                "rotulo_servico": ln["rotulo_servico"],
                "descricao": ln["descricao"],
                "codigo_servico": codigo,
                "codigo_por_rotulo": por_rotulo,
                "codigo_fonte": fonte_codigo,
                "codigo_diverge": bool(por_rotulo and codigo and por_rotulo != codigo),
                "nbs": (await nbs_de(db, codigo)) if codigo else None,
                "empresa_cnpj": empresa_cnpj,
                "empresa_fonte": empresa_fonte,
                "regime": (par or {}).get("regime"),
                # ISS: nulo para o Simples. NUNCA 0% inventado.
                "iss_aliquota": (float(par["iss_aliquota"]) if par and par.get("iss_aliquota") is not None else None),
                "serie_dps": (par or {}).get("serie_dps"),
                # ── as três contas de INSS, lado a lado ──────────────────────────────
                "va_folha": float(va) if va is not None else None,
                "vt_folha": float(vt) if vt is not None else None,
                "vt_sem_valor_na_folha": int(b.get("vt_sem_valor") or 0),
                "pessoas_na_folha": int(b.get("pessoas") or 0),
                "competencia_beneficio": anterior,
                # A folha é REFERÊNCIA, nunca a fonte do número que vai na nota: ela
                # discorda da planilha do dono em todos os tomadores medidos e o VT está
                # sem valor em sete dos oito condomínios. Quem digita é quem assina.
                "cessao_de_mao_de_obra": cessao_de_mao_de_obra(par),
                "base_com_deducao": float(bruto - deducao),
                "inss_com_deducao": float(inss_de(bruto - deducao)),
                "base_sem_deducao": float(bruto),
                "inss_sem_deducao": float(inss_de(bruto)),
                "inss_aliquota": (
                    float(par["inss_aliquota"]) if par and par.get("inss_aliquota") is not None else None
                ),
                "precedente": (
                    {
                        "numero": prec["numero"],
                        "competencia": prec["competencia"],
                        "valor": float(prec["valor_servicos"] or 0),
                        "inss": float(prec["inss_retido"]) if prec.get("inss_retido") is not None else None,
                        "empresa": prec["slug"],
                    }
                    if prec
                    else None
                ),
                "estado": ln["estado"],
                "fonte": ln["fonte"],
            }
        )
    return fora


async def marcar_emitida(db: AsyncSession, linha_id: int, nfse_id: str | None) -> None:
    """Fecha a linha do cronograma depois que o dono transmitiu a nota dela."""
    await db.execute(
        sqltext("UPDATE nfse_cronograma SET estado = 'emitida', nfse_id = CAST(:n AS uuid) WHERE id = :i"),
        {"i": int(linha_id), "n": nfse_id},
    )
    await db.commit()


def so_digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


# ---------------------------------------------------------------------------
# A dedução de VA e VT antes dos 11% — regra do dono, 24/09/2026
# ---------------------------------------------------------------------------

#: «vamos deduzir vale-alimentação e vale-transporte antes de aplicar os 11% em todas as
#: notas que tiver cessão de mão de obra, isso é regra, vai nos possibilitar economizar»
#: «essa regra só vale para cessão de mão de obra que sempre terá nota fiscal de serviço
#: emitida pela conecta patrimonial»  — Jordan Jesus, 24/09/2026.
#:
#: **O gatilho é o EMITENTE, não palavra na descrição.** Classificar por texto erra: o
#: Gelain tem «Portaria Remota» no rótulo e NÃO é cessão — não há pessoa posta no cliente
#: — e é da Eletrônica. O CNPJ que assina resolve isso sem interpretar nada.
#: Em `nfse_parametros_empresa` isso é dado: a Patrimonial tem `inss_aliquota = 11` e a
#: Eletrônica tem `NULL`. Quem quiser mudar muda a linha, não o código.


def cessao_de_mao_de_obra(par: dict[str, Any] | None) -> bool:
    """A nota tem retenção do Art. 31? Responde o parâmetro do emitente, não a descrição."""
    return bool(par and par.get("inss_aliquota") is not None)


def bloco_inss(
    bruto: Decimal | float | str,
    par: dict[str, Any] | None,
    *,
    va: Decimal | float | str | None = None,
    vt: Decimal | float | str | None = None,
    competencia_beneficio: str = "",
    pessoas: int | None = None,
) -> dict[str, Any]:
    """O texto que VAI NA NOTA e os números por trás dele.

    **A dedução só se sustenta com VA e VT discriminados na própria nota.** Sem os dois
    valores e a base escritos no corpo, o fisco glosa a dedução e a economia vira autuação.
    Por isso o texto é montado aqui, junto com a conta — nunca um sem o outro.

    **VA/VT ausente NÃO vira zero silencioso.** A nota sai sem dedução, o texto diz
    «sem deduções informadas» e `aviso` volta preenchido para a tela falar em voz alta.
    O número não está no sistema de forma confiável (ver `beneficios_por_tomador` e o §7 do
    relatório da frente): quem digita é quem assina.
    """
    valor = Decimal(str(bruto))
    if not cessao_de_mao_de_obra(par):
        return {
            "aplica": False,
            "texto": "",
            "base": None,
            "inss": None,
            "aviso": None,
            "deducao": None,
        }

    aliq = Decimal(str(par["inss_aliquota"]))
    tem_va, tem_vt = va not in (None, ""), vt not in (None, "")
    d_va = Decimal(str(va)) if tem_va else Decimal(0)
    d_vt = Decimal(str(vt)) if tem_vt else Decimal(0)
    deducao = d_va + d_vt
    base = valor - deducao
    inss = (base * aliq / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    pct = f"{aliq.normalize():f}".rstrip(".")

    if deducao > 0:
        comp = f" {competencia_beneficio}" if competencia_beneficio else ""
        linhas = [
            f"DEDUÇÕES DA BASE DE CÁLCULO: {_reais(deducao)}",
        ]
        if pessoas:
            linhas.append(f"QUANTIDADE DE FUNCIONÁRIOS NO CONTRATO: {pessoas:02d}")
        if tem_va:
            linhas.append(f"Vale Alimentação{comp}: {_reais(d_va)}")
        if tem_vt:
            linhas.append(f"Vale Transporte{comp}: {_reais(d_vt)}")
        linhas.append(f"BASE DE CÁLCULO PARA RETENÇÃO DE INSS: {_reais(base)}")
        aviso = None
        if not (tem_va and tem_vt):
            falta = "vale-transporte" if tem_va else "vale-alimentação"
            aviso = (
                f"A nota vai deduzir só um dos dois benefícios — {falta} não foi informado. "
                "Se houve, a retenção está saindo maior do que precisava."
            )
    else:
        linhas = [f"BASE DE CÁLCULO PARA RETENÇÃO DE INSS: {_reais(base)} (sem deduções informadas)"]
        aviso = (
            "Esta nota é de cessão de mão de obra e vai sair SEM dedução de vale-alimentação e "
            "vale-transporte — os valores não foram informados. A retenção de INSS sai sobre o "
            "valor cheio, que é mais imposto do que o Art. 31 exige. O sistema não inventa esses "
            "números: informe VA e VT antes de transmitir."
        )
    linhas += [
        f"Aplicada retenção do INSS ({pct}%) conforme o Art. 31 da Lei n. 9.711/98.",
        f"VALOR DA RETENÇÃO DE INSS ({pct}%): {_reais(inss)}",
    ]
    return {
        "aplica": True,
        "texto": " ".join(linhas),
        "base": float(base),
        "inss": float(inss),
        "deducao": float(deducao),
        "va": float(d_va) if tem_va else None,
        "vt": float(d_vt) if tem_vt else None,
        "aviso": aviso,
    }


def _reais(v: Decimal | float) -> str:
    return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def montar_descricao(descricao_base: str, bloco: dict[str, Any]) -> str:
    """A descrição que vai na nota: o texto do serviço + o bloco do INSS, quando houver.

    Se o texto do dono JÁ traz o bloco (é o caso de 3 das 14 linhas do cronograma dele), o
    bloco calculado não é duplicado — mas a conta continua sendo conferida na tela, lado a
    lado com o que ele escreveu.
    """
    base = (descricao_base or "").strip()
    if not bloco.get("aplica") or not bloco.get("texto"):
        return base
    if "RETENÇÃO DE INSS" in base.upper() or "RETENCAO DE INSS" in base.upper():
        return base
    return f"{base} {bloco['texto']}".strip()
