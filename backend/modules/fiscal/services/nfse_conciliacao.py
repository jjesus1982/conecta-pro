"""DGX AA4 — conciliação da NFS-e com o fisco: a rotina que fecha o furo das 37 notas.

O furo, medido em 24/09/2026 (produção, só leitura)
---------------------------------------------------
A régua certa é a **numeração por CNPJ**, que é consecutiva por emitente:

    conecta_eletronica   nº   2 a 123 · temos 89 · FALTAM 33
    conecta_patrimonial  nº   3 a  32 · temos 26 · FALTAM  4

**37 notas emitidas no fisco sem uma linha aqui.** Medir pelo NSU do ADN acusaria 419 e
seria mentira: o NSU carrega todo tipo de documento (nota recebida como tomador, evento,
cancelamento), não só nota emitida.

Um número ausente ainda pode ser legítimo — nota cancelada, número pulado. **Quem diz é
o fisco, não a aritmética.** Por isso esta rotina pergunta, e grava também a resposta
«não existe»: sem esse registro ela reconsultaria o mesmo número para sempre.

Por que a varredura é de DPS e não de NFS-e
-------------------------------------------
O fisco responde por duas chaves, e só uma delas é construtível:

  · **chave da NFS-e (50 dígitos)** — carrega um código numérico de 8 dígitos sorteado
    por ele. Medido nos DANFSe do dono: a nota 29 termina `…260896878833` e a 116
    `…260894006421 00`, sem qualquer relação com o número da nota. **Não dá para montar.**
  · **chave da DPS (42 dígitos)** = cMun + tpInsc + CNPJ + série + nDPS. **Dá.**

Toda NFS-e nasceu de uma DPS. Então a varredura anda pelos números de DPS, e cada
resposta preenche (ou descarta) um número da sequência de NFS-e.

Por que as 37 escaparam da sincronia que já existia
---------------------------------------------------
`financial/services/nfse_nacional_sync_service.sincronizar()` varre o ADN por NSU
(`gedeon/services/nfse_nacional_adn.distribuir`), recomeçando do NSU 0 todo dia às
04:30 e fazendo recarga limpa escopada por empresa. Duas coisas medidas no código:
o checkpoint `fiscal_nsu_checkpoint` é **escrito e nunca lido**, e o laço para no
primeiro lote com menos de 50 documentos (`if len(lote) < 50: break`) — o que não é
a mesma coisa que «acabaram os documentos». Esta frente **não mexe nessa rotina**:
conciliar por DPS é um segundo caminho, independente, que não depende de adivinhar
a causa.

O DELETE daquela sincronia é escopado em `fonte='adn_nacional'`. As linhas que esta
rotina grava levam `fonte='conciliacao_fisco'` e **sobrevivem** à recarga noturna —
assim como a linha que o dono autorizou gravar à mão (`danfse_pdf_do_dono_20260924`),
que esta rotina sobrescreve com a resposta do fisco quando conseguir.

O que esta rotina NÃO faz
-------------------------
  · **não emite nada.** É só GET. Conciliar a produção exige ler a produção, e ler não
    cria documento fiscal. A trava de produção da Z7 continua inteira no caminho que
    emite (`emitir_dps`), que esta rotina nunca chama;
  · não apaga nem reescreve as 27 linhas de `nfses` que dizem «autorizada» sem nunca
    terem sido transmitidas (Z7 §8.1) — elas são de outra frente e de outra tabela;
  · não cancela nada. Nota que o fisco devolver como cancelada é gravada como cancelada,
    e o cancelamento continua sendo feito lá.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Margem de números de DPS a varrer acima do maior já observado. O maior nº de DPS
#: conhecido é o PISO, não o teto: o dono pode ter emitido depois da última medição.
MARGEM_DPS = 12

_DDL = (
    # Um livro-razão só. `tipo` separa as duas unidades que a conciliação manipula:
    #   'dps'  → número de DPS, consultável no fisco (chave construtível);
    #   'nfse' → número da NFS-e ausente na sequência — o diagnóstico. Não é consultável
    #            direto; fecha por cobertura, quando a varredura de DPS terminar.
    "CREATE TABLE IF NOT EXISTS nfse_conciliacao ("
    " prestador_cnpj varchar(14) NOT NULL,"
    " ambiente varchar(16) NOT NULL,"
    " tipo varchar(6) NOT NULL,"
    " serie varchar(5) NOT NULL DEFAULT '',"
    " numero integer NOT NULL,"
    " estado varchar(16) NOT NULL DEFAULT 'pendente',"
    " chave_acesso varchar(60),"
    " numero_nfse varchar(20),"
    " http_status integer,"
    " mensagem text,"
    " tentativas integer NOT NULL DEFAULT 0,"
    " conferido_em timestamp,"
    " criado_em timestamp NOT NULL DEFAULT now(),"
    " PRIMARY KEY (prestador_cnpj, ambiente, tipo, serie, numero))",
    "CREATE INDEX IF NOT EXISTS ix_nfse_conciliacao_estado ON nfse_conciliacao (estado, tipo)",
    # O maior nº de DPS que o fisco já mostrou, por CNPJ. É MEDIÇÃO, não contador: o
    # contador vivo é `nfse_numeracao` e ele só nasce quando for emitir de verdade.
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS ultimo_dps_observado integer",
    "ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS ultimo_dps_fonte text",
    # A coluna que o orquestrador criou em produção em 24/09; aqui para o sandbox ter a
    # mesma forma. `ADD COLUMN IF NOT EXISTS` em produção é no-op.
    "ALTER TABLE nfse_emitidas_nacional ADD COLUMN IF NOT EXISTS observacao_interna TEXT",
)

#: Maior número de DPS observado nos DANFSe que o dono subiu. Piso, nunca teto.
#: Eletrônica: DPS 102 (NFS-e 116), 114 (119), 118 (120) e **125** (NFS-e 121, 09/2026).
#: Patrimonial: DPS 59 (NFS-e 27), 63 (28), 67 (29), 71 (30) e **75** (NFS-e 31).
_PISO_DPS: dict[str, tuple[int, str]] = {
    "35710481000103": (125, "DANFSe nº 121 de 17/09/2026 — «NÚMERO DA DPS 125, SÉRIE DA DPS 70000»."),
    "66014833000110": (75, "DANFSe nº 31 de 26/08/2026 — «NÚMERO DA DPS 75, SÉRIE DA DPS 70000»."),
}


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
    if (
        await db.execute(
            sqltext(
                "SELECT to_regclass('public.nfse_conciliacao') IS NOT NULL AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'nfse_emitidas_nacional' AND column_name = 'observacao_interna')"
            )
        )
    ).scalar():
        _ddl_aplicado = True
    else:
        await db.execute(sqltext(_LOCK_TIMEOUT))
        for sql in _DDL:
            await db.execute(sqltext(sql))
    for cnpj, (piso, fonte) in _PISO_DPS.items():
        # GREATEST: uma medição maior nunca é rebaixada por este seed.
        await db.execute(
            sqltext(
                "UPDATE nfse_parametros_empresa"
                " SET ultimo_dps_observado = GREATEST(COALESCE(ultimo_dps_observado, 0), :p),"
                "     ultimo_dps_fonte = COALESCE(ultimo_dps_fonte, :f)"
                " WHERE prestador_cnpj = :c"
            ),
            {"c": cnpj, "p": piso, "f": fonte},
        )
    _ddl_aplicado = True
    await db.commit()


# ---------------------------------------------------------------------------
# A régua: o furo, medido por numeração de NFS-e por CNPJ
# ---------------------------------------------------------------------------


async def medir_furo(db: AsyncSession) -> list[dict[str, Any]]:
    """Por CNPJ: faixa emitida, quantas temos e QUAIS números faltam.

    A faixa é `min..max` do que já está em `nfse_emitidas_nacional`. Nota emitida
    **acima** do maior conhecido não aparece aqui — ninguém sabe que ela existe até a
    varredura de DPS a encontrar. Por isso a varredura vai além do maior número visto.
    """
    linhas = (
        (
            await db.execute(
                sqltext(
                    "WITH b AS ("
                    "  SELECT e.id, e.slug, regexp_replace(e.cnpj,'\\D','','g') AS cnpj,"
                    "         min(n.numero::int) lo, max(n.numero::int) hi, count(*) qtd,"
                    "         coalesce(sum(n.valor_servicos),0) total"
                    "    FROM empresas e JOIN nfse_emitidas_nacional n ON n.empresa_id = e.id"
                    "   WHERE n.numero ~ '^[0-9]+$' GROUP BY 1,2,3)"
                    " SELECT b.slug, b.cnpj, b.lo, b.hi, b.qtd, b.total,"
                    "  (SELECT coalesce(array_agg(g.n ORDER BY g.n), '{}') FROM generate_series(b.lo,b.hi) g(n)"
                    "    WHERE NOT EXISTS (SELECT 1 FROM nfse_emitidas_nacional x"
                    "                       WHERE x.empresa_id = b.id AND x.numero::int = g.n)) AS faltam"
                    " FROM b ORDER BY b.slug"
                )
            )
        )
        .mappings()
        .all()
    )
    return [dict(x) for x in linhas]


async def _ambiente_de(db: AsyncSession, cnpj: str) -> str:
    v = (
        await db.execute(
            sqltext(
                "SELECT coalesce(nfse_ambiente,'homologacao') FROM empresas"
                " WHERE regexp_replace(cnpj,'\\D','','g') = :c"
            ),
            {"c": cnpj},
        )
    ).first()
    return str(v[0]) if v else "homologacao"


# ---------------------------------------------------------------------------
# Semeadura das pendências
# ---------------------------------------------------------------------------


async def semear(db: AsyncSession) -> dict[str, Any]:
    """Cria a pendência de cada número ausente e de cada DPS a varrer. Idempotente.

    `ON CONFLICT DO NOTHING`: rodar de novo não apaga o que já foi conferido, e um
    número que reapareceu como ausente (porque a recarga noturna do ADN o removeu)
    reentra como pendente.
    """
    await _ensure(db)
    from modules.fiscal.services.nfse_parametros import serie_de

    novos_nfse = novos_dps = 0
    for emp in await medir_furo(db):
        cnpj, amb = emp["cnpj"], await _ambiente_de(db, emp["cnpj"])
        serie = await serie_de(db, cnpj)
        for n in emp["faltam"] or []:
            r = await db.execute(
                sqltext(
                    "INSERT INTO nfse_conciliacao (prestador_cnpj, ambiente, tipo, serie, numero, mensagem)"
                    " VALUES (:c, :a, 'nfse', '', :n, :m) ON CONFLICT DO NOTHING"
                ),
                {
                    "c": cnpj,
                    "a": amb,
                    "n": int(n),
                    "m": f"Ausente na sequência {emp['lo']}–{emp['hi']} do CNPJ {cnpj}.",
                },
            )
            novos_nfse += r.rowcount or 0
        teto = await _teto_dps(db, cnpj, emp["hi"])
        for s in await _series_em_uso(db, cnpj, amb, serie):
            for d in range(1, teto + 1):
                r = await db.execute(
                    sqltext(
                        "INSERT INTO nfse_conciliacao (prestador_cnpj, ambiente, tipo, serie, numero)"
                        " VALUES (:c, :a, 'dps', :s, :n) ON CONFLICT DO NOTHING"
                    ),
                    {"c": cnpj, "a": amb, "s": s, "n": d},
                )
                novos_dps += r.rowcount or 0
    await db.commit()
    return {"pendencias_nfse_novas": novos_nfse, "pendencias_dps_novas": novos_dps}


async def _series_em_uso(db: AsyncSession, cnpj: str, ambiente: str, serie_parametro: str) -> list[str]:
    """A série do parâmetro MAIS toda série que este CNPJ já usou neste ambiente.

    Varrer só a série parametrizada deixaria de fora nota emitida numa série antiga — e é
    exatamente esse o caso desta casa: as notas do portal são série 70000 e a frente Z7
    emitiu em homologação na série 900. Uma nota autorizada pelo fisco numa série que o
    parâmetro não conhece é invisível para a conciliação, que é o defeito que ela existe
    para consertar.
    """
    vistas = [
        str(r[0])
        for r in (
            await db.execute(
                sqltext(
                    "SELECT DISTINCT serie_rps FROM nfses"
                    " WHERE prestador_cnpj = :c AND ambiente = :a AND serie_rps IS NOT NULL"
                ),
                {"c": cnpj, "a": ambiente},
            )
        ).all()
    ]
    return sorted({serie_parametro, *vistas})


async def _teto_dps(db: AsyncSession, cnpj: str, maior_nfse: int | None) -> int:
    """Até onde varrer números de DPS. Piso observado + margem, nunca abaixo da NFS-e máxima.

    Uma DPS pode ser recusada e não virar nota, então o nº de DPS anda mais rápido que o
    da NFS-e — nas notas do dono, 75 DPS para 31 NFS-e. Varrer só até o nº da última nota
    deixaria buraco.
    """
    v = (
        await db.execute(
            sqltext("SELECT coalesce(ultimo_dps_observado, 0) FROM nfse_parametros_empresa WHERE prestador_cnpj = :c"),
            {"c": cnpj},
        )
    ).first()
    return max(int(v[0]) if v else 0, int(maior_nfse or 0)) + MARGEM_DPS


# ---------------------------------------------------------------------------
# A conciliação
# ---------------------------------------------------------------------------


def _num(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except Exception:  # noqa: BLE001
        return None


def _competencia(xml: str) -> str | None:
    m = re.search(r"<dCompet>(\d{4})-(\d{2})", xml or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _tag(xml: str, nome: str) -> str | None:
    m = re.search(rf"<(?:\w+:)?{nome}>([^<]+)</(?:\w+:)?{nome}>", xml or "")
    return m.group(1) if m else None


async def conciliar(
    db: AsyncSession, *, empresa_cnpj: str | None = None, limite: int = 25, quem: str = "sistema"
) -> dict[str, Any]:
    """Consulta o fisco sobre `limite` DPS pendentes e grava o que ele responder.

    Devolve o que foi recuperado, o que o fisco disse não existir, e o dinheiro que
    apareceu. Um `limite` pequeno é de propósito: o ADN/sefin limita requisições por
    segundo e a rotina roda agendada — atravessar a fila devagar é melhor que levar 429.
    """
    await _ensure(db)
    from modules.government_integrations.services.nfse_nacional_service import get_nfse_nacional_service

    p: dict[str, Any] = {"lim": int(limite)}
    filtro = ""
    if empresa_cnpj:
        filtro = " AND prestador_cnpj = :c"
        p["c"] = re.sub(r"\D", "", empresa_cnpj)
    pendentes = (
        (
            await db.execute(
                sqltext(
                    "SELECT prestador_cnpj, ambiente, serie, numero, tentativas FROM nfse_conciliacao"
                    " WHERE tipo = 'dps' AND estado IN ('pendente','erro')"
                    + filtro
                    + " ORDER BY tentativas, numero LIMIT :lim"
                ),
                p,
            )
        )
        .mappings()
        .all()
    )

    slugs = await _slug_por_cnpj(db)
    achadas: list[dict[str, Any]] = []
    n_inexistente = n_erro = 0
    dinheiro = 0.0

    for pend in pendentes:
        cnpj = pend["prestador_cnpj"]
        slug = slugs.get(cnpj)
        if not slug:
            await _marcar(db, pend, "erro", mensagem=f"CNPJ {cnpj} não tem empresa ativa no ERP.")
            n_erro += 1
            continue
        try:
            svc = get_nfse_nacional_service(slug)
            r = svc.consultar_por_dps(pend["serie"], pend["numero"])
        except Exception as e:  # noqa: BLE001 — senha do certificado nunca entra aqui
            await _marcar(db, pend, "erro", mensagem=f"{type(e).__name__}: {e}")
            n_erro += 1
            continue

        estado = str(r.get("status") or "")
        if estado == "encontrada" and r.get("chave_acesso"):
            gravada = await _gravar_nota(db, cnpj=cnpj, resultado=r, quem=quem)
            await _marcar(
                db,
                pend,
                "encontrada",
                chave=r.get("chave_acesso"),
                numero_nfse=gravada.get("numero"),
                http=r.get("http_status"),
                mensagem=f"NFS-e {gravada.get('numero') or '?'} recuperada do fisco.",
            )
            achadas.append(gravada)
            dinheiro += float(gravada.get("valor") or 0)
            await _subir_piso(db, cnpj, int(pend["numero"]))
        elif estado == "inexistente":
            # A informação que faltava: o fisco NEGANDO o número — e negando com o código
            # DELE (`E2404`, «Não foi gerada uma NFS-e com o identificador de DPS
            # informado»). Sem isso a rotina reconsultaria para sempre.
            #
            # Um 404 SEM esse código nunca chega aqui: `_get` o classifica como
            # `caminho_invalido` e ele cai no ramo de erro abaixo. A diferença não é
            # detalhe — em 24/09/2026 o endpoint estava escrito errado
            # (`/nfse/DPS/{chave}`, que não é rota) e devolvia 404 de HTML para TUDO.
            # Lido como «não existe», isso fecharia as 37 notas ausentes com a tela verde
            # e o dinheiro perdido. O código de erro do fisco é o que separa os dois.
            await _marcar(
                db,
                pend,
                "inexistente",
                http=r.get("http_status"),
                mensagem=(
                    f"O fisco respondeu {r.get('codigo_erro') or 'não encontrado'}: "
                    f"{r.get('descricao_erro') or 'não existe NFS-e para esta DPS'} "
                    "(cancelada, pulada ou nunca emitida)."
                ),
            )
            n_inexistente += 1
        else:
            await _marcar(
                db,
                pend,
                "erro",
                http=r.get("http_status"),
                mensagem=f"{estado}: {str(r.get('erro') or r.get('response') or '')[:400]}",
            )
            n_erro += 1

    fechados = await _fechar_ausentes(db)
    await db.commit()
    return {
        "consultadas": len(pendentes),
        "recuperadas": len(achadas),
        "dinheiro_recuperado": round(dinheiro, 2),
        "fisco_disse_que_nao_existe": n_inexistente,
        "erros": n_erro,
        "numeros_de_nfse_fechados": fechados,
        "notas": achadas,
    }


async def _slug_por_cnpj(db: AsyncSession) -> dict[str, str]:
    linhas = (
        await db.execute(sqltext("SELECT regexp_replace(cnpj,'\\D','','g'), slug FROM empresas WHERE status = 'ativa'"))
    ).all()
    return {r[0]: r[1] for r in linhas}


async def _marcar(
    db: AsyncSession,
    pend: Any,
    estado: str,
    *,
    chave: str | None = None,
    numero_nfse: str | None = None,
    http: int | None = None,
    mensagem: str | None = None,
) -> None:
    await db.execute(
        sqltext(
            "UPDATE nfse_conciliacao SET estado = :e, chave_acesso = :ch, numero_nfse = :nn,"
            " http_status = :h, mensagem = :m, tentativas = tentativas + 1, conferido_em = now()"
            " WHERE prestador_cnpj = :c AND ambiente = :a AND tipo = 'dps' AND serie = :s AND numero = :n"
        ),
        {
            "e": estado,
            "ch": chave,
            "nn": str(numero_nfse) if numero_nfse else None,
            "h": int(http) if http is not None else None,
            "m": (mensagem or "")[:2000],
            "c": pend["prestador_cnpj"],
            "a": pend["ambiente"],
            "s": pend["serie"],
            "n": pend["numero"],
        },
    )


async def _subir_piso(db: AsyncSession, cnpj: str, numero_dps: int) -> None:
    """O maior nº de DPS que o fisco confirmou. Só sobe."""
    await db.execute(
        sqltext(
            "UPDATE nfse_parametros_empresa"
            " SET ultimo_dps_observado = GREATEST(COALESCE(ultimo_dps_observado,0), :n),"
            "     ultimo_dps_fonte = CASE WHEN COALESCE(ultimo_dps_observado,0) < :n"
            "       THEN 'conciliação com o fisco em ' || to_char(now(),'DD/MM/YYYY')"
            "       ELSE ultimo_dps_fonte END"
            " WHERE prestador_cnpj = :c"
        ),
        {"c": cnpj, "n": int(numero_dps)},
    )


async def _gravar_nota(db: AsyncSession, *, cnpj: str, resultado: dict[str, Any], quem: str) -> dict[str, Any]:
    """Grava (ou sobrescreve) a nota em `nfse_emitidas_nacional` com o que o FISCO devolveu.

    `ON CONFLICT (chave_acesso) DO UPDATE` de propósito: a linha da NFS-e 29 que o dono
    autorizou gravar à mão a partir do PDF (`fonte='danfse_pdf_do_dono_20260924'`) tem de
    ceder lugar à resposta do órgão — que é a fonte melhor.

    ISS: grava o que veio. Vazio NÃO vira zero. A Patrimonial é do Simples e o fisco não
    devolve ISS para ela — a coluna fica nula, como manda a Z7 §3.
    """
    xml = str(resultado.get("xml_nfse") or "")
    aliq = _num(resultado.get("aliquota_iss_fisco"))
    dados = {
        "chave": str(resultado.get("chave_acesso")),
        "numero": resultado.get("numero_nfse") or _tag(xml, "nNFSe"),
        "competencia": _competencia(xml),
        "data_emissao": _quando(resultado.get("data_processamento") or _tag(xml, "dhProc")),
        "tomador_cnpj": _tomador(xml)[0],
        "tomador_nome": _tomador(xml)[1],
        "valor": _num(resultado.get("valor_liquido_fisco")) or _num(_tag(xml, "vServ")),
        "iss_valor": _num(resultado.get("valor_iss_fisco")),
        # None, não 0.0 — ver docstring.
        "iss_aliquota": (aliq / 100) if aliq is not None else None,
        "valor_liquido": _num(resultado.get("valor_liquido_fisco")),
        "inss": _num(_tag(xml, "vRetCP")),
        "codigo_servico": _tag(xml, "cTribNac"),
        "descricao": (_tag(xml, "xDescServ") or "")[:2000] or None,
        "cancelada": bool(_tag(xml, "situacao") == "2") or "<e105101>" in xml,
        "cnpj": cnpj,
        "obs": (
            f"Recuperada da conciliação com o fisco em {datetime.now():%d/%m/%Y %H:%M} por {quem} "
            f"(DPS série {resultado.get('serie')} nº {resultado.get('numero_dps')}, "
            f"GET {resultado.get('operacao')}). Sobrescreve qualquer origem anterior."
        ),
    }
    await db.execute(
        sqltext(
            "INSERT INTO nfse_emitidas_nacional"
            " (chave_acesso, numero, competencia, data_emissao, tomador_cnpj, tomador_nome,"
            "  valor_servicos, iss_valor, iss_aliquota, valor_liquido, inss_retido,"
            "  codigo_servico, descricao, fonte, empresa_id, cancelada, observacao_interna)"
            " SELECT :chave, :numero, :competencia, :data_emissao, :tomador_cnpj, :tomador_nome,"
            "        :valor, :iss_valor, :iss_aliquota, :valor_liquido, :inss,"
            "        :codigo_servico, :descricao, 'conciliacao_fisco', e.id, :cancelada, :obs"
            "   FROM empresas e WHERE regexp_replace(e.cnpj,'\\D','','g') = :cnpj"
            " ON CONFLICT (chave_acesso) DO UPDATE SET"
            "   numero = EXCLUDED.numero, competencia = COALESCE(EXCLUDED.competencia, nfse_emitidas_nacional.competencia),"
            "   data_emissao = COALESCE(EXCLUDED.data_emissao, nfse_emitidas_nacional.data_emissao),"
            "   tomador_cnpj = COALESCE(EXCLUDED.tomador_cnpj, nfse_emitidas_nacional.tomador_cnpj),"
            "   tomador_nome = COALESCE(EXCLUDED.tomador_nome, nfse_emitidas_nacional.tomador_nome),"
            "   valor_servicos = COALESCE(EXCLUDED.valor_servicos, nfse_emitidas_nacional.valor_servicos),"
            "   iss_valor = EXCLUDED.iss_valor, iss_aliquota = EXCLUDED.iss_aliquota,"
            "   valor_liquido = COALESCE(EXCLUDED.valor_liquido, nfse_emitidas_nacional.valor_liquido),"
            "   inss_retido = COALESCE(EXCLUDED.inss_retido, nfse_emitidas_nacional.inss_retido),"
            "   codigo_servico = COALESCE(EXCLUDED.codigo_servico, nfse_emitidas_nacional.codigo_servico),"
            "   descricao = COALESCE(EXCLUDED.descricao, nfse_emitidas_nacional.descricao),"
            "   fonte = 'conciliacao_fisco', cancelada = EXCLUDED.cancelada,"
            "   observacao_interna = EXCLUDED.observacao_interna"
        ),
        dados,
    )
    return dados


def _quando(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)[:19])
    except Exception:  # noqa: BLE001
        return None


def _bloco(xml: str, nome: str) -> str:
    """O conteúdo de `<nome>…</nome>`, ou vazio."""
    m = re.search(rf"<(?:\w+:)?{nome}\b[^>]*>(.*?)</(?:\w+:)?{nome}>", xml or "", re.S)
    return m.group(1) if m else ""


def _tomador(xml: str) -> tuple[str | None, str | None]:
    """Documento e nome do tomador, lidos DENTRO de `<toma>`.

    Medido em 24/09/2026 no `<NFSe>` que o fisco assina: o documento aparece três vezes —
    `<emit>`, `<prest>` e `<toma>` — e o primeiro `<xNome>` do XML é o do PRESTADOR. Pegar
    «o segundo CNPJ» ou «o primeiro xNome» grava o emitente no lugar do cliente, que foi o
    que a primeira versão desta função fez na prova viva.
    """
    toma = _bloco(xml, "toma")
    if not toma:
        return None, None
    doc = re.search(r"<(?:\w+:)?(?:CNPJ|CPF|NIF)>([0-9A-Za-z]{5,20})</", toma)
    nome = re.search(r"<(?:\w+:)?xNome>([^<]+)</", toma)
    return (doc.group(1) if doc else None), (nome.group(1) if nome else None)


async def _fechar_ausentes(db: AsyncSession) -> int:
    """Fecha os números de NFS-e que a varredura resolveu.

    Duas maneiras de fechar, as duas com o fisco como fonte:
      · **recuperada** — apareceu linha em `nfse_emitidas_nacional` para aquele número;
      · **inexistente** — a varredura de DPS do CNPJ terminou (nenhuma pendente sobrou)
        e nenhuma delas produziu aquele número. O fisco negou, um a um, todas as DPS que
        poderiam tê-lo gerado.

    Nunca fecha por dedução aritmética: enquanto houver DPS pendente ou em erro, o número
    continua `pendente` — «ausente e ainda não conferido» é o estado honesto.
    """
    r1 = await db.execute(
        sqltext(
            "UPDATE nfse_conciliacao c SET estado = 'recuperada', conferido_em = now(),"
            " mensagem = 'Número presente em nfse_emitidas_nacional.'"
            " WHERE c.tipo = 'nfse' AND c.estado <> 'recuperada'"
            "   AND EXISTS (SELECT 1 FROM nfse_emitidas_nacional n JOIN empresas e ON e.id = n.empresa_id"
            "                WHERE regexp_replace(e.cnpj,'\\D','','g') = c.prestador_cnpj"
            "                  AND n.numero ~ '^[0-9]+$' AND n.numero::int = c.numero)"
        )
    )
    r2 = await db.execute(
        sqltext(
            "UPDATE nfse_conciliacao c SET estado = 'inexistente', conferido_em = now(),"
            " mensagem = 'Varredura de DPS do CNPJ concluída e o fisco negou todas — este número não existe lá.'"
            " WHERE c.tipo = 'nfse' AND c.estado = 'pendente'"
            "   AND NOT EXISTS (SELECT 1 FROM nfse_conciliacao d WHERE d.tipo = 'dps'"
            "                    AND d.prestador_cnpj = c.prestador_cnpj"
            "                    AND d.estado IN ('pendente','erro'))"
            "   AND EXISTS (SELECT 1 FROM nfse_conciliacao d WHERE d.tipo = 'dps'"
            "                AND d.prestador_cnpj = c.prestador_cnpj)"
        )
    )
    return (r1.rowcount or 0) + (r2.rowcount or 0)


# ---------------------------------------------------------------------------
# Numeração de produção: nasce certa ou não nasce
# ---------------------------------------------------------------------------


async def piso_de_numeracao(db: AsyncSession, cnpj: str) -> int:
    """O último número de DPS que o fisco confirmou para este CNPJ.

    É o piso do contador. Emitir a partir do 1 numa série que o fisco já usou devolve
    `E0141` («essa série+número já existe») número a número — foi o que a Z7 mediu na
    série 900. Com o piso certo, a primeira emissão de produção pega o número seguinte.
    """
    v = (
        await db.execute(
            sqltext("SELECT coalesce(ultimo_dps_observado, 0) FROM nfse_parametros_empresa WHERE prestador_cnpj = :c"),
            {"c": re.sub(r"\D", "", cnpj)},
        )
    ).first()
    return int(v[0]) if v else 0


async def resumo(db: AsyncSession) -> dict[str, Any]:
    """O placar da conciliação, para a tela e para o oráculo."""
    await _ensure(db)
    linhas = (
        (
            await db.execute(
                sqltext(
                    "SELECT prestador_cnpj, tipo, estado, count(*) qtd FROM nfse_conciliacao"
                    " GROUP BY 1,2,3 ORDER BY 1,2,3"
                )
            )
        )
        .mappings()
        .all()
    )
    return {"linhas": [dict(x) for x in linhas], "furo": await medir_furo(db)}
