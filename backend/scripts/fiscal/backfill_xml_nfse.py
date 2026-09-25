#!/usr/bin/env python3
"""Busca no portal nacional (ADN) o XML assinado das NFS-e já emitidas, e guarda.

## Por que isto existe

`nfse_emitidas_nacional` guarda **12 campos** da nota. O DANFSe v2.0 tem blocos que só existem
no XML assinado: endereço do prestador e do tomador, número e série da DPS, código da NBS,
tributação municipal, federal e IBS/CBS. Sem o XML, o documento que vai ao condomínio **sai
pela metade** — medido em 25/09/2026: 123 notas na tabela, **zero** com XML.

Reusa `_buscar_xml_nfse` do `fiscal_controller` — a MESMA função que a rota do DANFSe chama.
Não há segunda implementação: se a rota mudar, este script muda junto. (Lição de 25/09: todo
modo em lote tem de ser o caminho real repetido, nunca uma cópia da lógica.)

## As três paredes

1. **PACIENTE.** São ~114 chamadas a um serviço da Receita. `--intervalo` (padrão 3s) entre
   cada uma. Disparar 114 requisições seguidas a órgão público é pedir bloqueio, e o bloqueio
   atingiria a EMISSÃO, que é o que não pode parar.
2. **RETOMÁVEL.** Só busca quem está sem XML. Morreu no meio? Roda de novo e continua.
3. **HONESTO.** Conta sucesso, «ADN respondeu sem XML» e erro separadamente. Um resumo que
   diz «114 processadas» sem dizer quantas trouxeram XML é o tipo de número que parece
   medida e não é.

Leitura pura: `GET /nfse/{chave}` não emite, não cancela, não altera nada no fisco.

Uso:
    python3 backend/scripts/fiscal/backfill_xml_nfse.py            # conferência, nada busca
    python3 backend/scripts/fiscal/backfill_xml_nfse.py --aplicar [--limite 10] [--intervalo 3]

Linha canônica: `TOTAL: <n> NFS-e com XML guardado`.
"""

from __future__ import annotations

import asyncio
import sys
import time

sys.path.insert(0, "/app")


def _sem_resposta(det: dict) -> bool:
    """O fisco NÃO respondeu — diferente de responder «não tenho».

    Medido em 25/09/2026: a nº 105 voltou `http_502` e a nº 120 voltou vazia num lote e com
    7.601 caracteres quando perguntada de novo. O ADN devolve 5xx intermitente sob carga.
    Chamar isso de «o fisco respondeu sem XML» é reportar ausência de dado onde houve
    ausência de RESPOSTA — e foi o que já quase me fez concluir que as notas não existiam.

    Só é «o fisco não tem» quando ele respondeu de verdade e não veio XML.
    """
    st = str(det.get("status") or "").lower()
    if det.get("motivo"):
        return True
    return st.startswith(("erro", "timeout", "http_5", "http_4")) or not st


def _arg(nome: str, padrao: float) -> float:
    for i, a in enumerate(sys.argv):
        if a == nome and i + 1 < len(sys.argv):
            try:
                return float(sys.argv[i + 1])
            except ValueError:
                return padrao
    return padrao


async def main() -> int:
    aplicar = "--aplicar" in sys.argv
    limite = int(_arg("--limite", 0))
    intervalo = _arg("--intervalo", 3.0)
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415

        from modules.financial.controllers.fiscal_controller import _buscar_xml_nfse  # noqa: PLC0415
    except ModuleNotFoundError as e:
        print(f"RECUSO: roda DENTRO do container ({e})")
        return 2

    ok = vazio = erro = rede = 0
    por_empresa: dict[str, list[int]] = {}
    async with async_session_factory() as db:
        q = (
            "SELECT n.chave_acesso, n.numero, coalesce(n.ambiente,'?') amb,"
            "       coalesce(e.certificado_a1_path,'') cert,"
            "       coalesce(e.razao_social,'(sem empresa)') emp"
            "  FROM nfse_emitidas_nacional n"
            "  LEFT JOIN empresas e ON e.id = n.empresa_id"
            " WHERE coalesce(n.xml_nfse,'') = '' AND coalesce(n.chave_acesso,'') <> ''"
            "   AND coalesce(n.cancelada, false) = false"
            # HOMOLOGAÇÃO fora: o ADN de produção não conhece nota do ambiente de produção
            # restrita. Buscar as 8 gastaria 8 chamadas a órgão público para receber 8
            # «sem XML» — e 8 falsos negativos num relatório que existe para ser confiável.
            "   AND coalesce(n.ambiente,'') = 'producao'"
            # ⚠️ `numero` é TEXTO: `ORDER BY numero DESC` é lexicográfico e põe «99» antes de
            # «121». Não muda o resultado de uma varredura completa, mas embaralha a ordem e
            # fez a minha leitura parcial concluir que «notas de junho em diante não voltam» —
            # quando o lote simplesmente ainda não tinha chegado nelas.
            " ORDER BY regexp_replace(coalesce(n.numero::text,'0'),'\\D','','g')::bigint DESC"
        )
        faltam = (await db.execute(text(q))).mappings().all()
        total_tab = (await db.execute(text("SELECT count(*) FROM nfse_emitidas_nacional"))).scalar()
        com_xml = (
            await db.execute(text("SELECT count(*) FROM nfse_emitidas_nacional WHERE coalesce(xml_nfse,'') <> ''"))
        ).scalar()
        print(f"tabela: {total_tab} NFS-e · {com_xml} já com XML · {len(faltam)} sem XML e não canceladas")
        if not aplicar:
            print("\n(conferência — nada foi buscado. Use --aplicar)")
            print(f"\nTOTAL: 0 NFS-e com XML guardado")
            return 0

        alvos = faltam[: int(limite)] if limite else faltam
        print(f"buscando {len(alvos)} · intervalo {intervalo}s · ~{len(alvos)*intervalo/60:.0f} min\n")
        for i, r in enumerate(alvos, 1):
            chave = r["chave_acesso"]
            det: dict = {}
            emp = r["emp"][:24]
            try:
                xml = await _buscar_xml_nfse(db, chave, r["cert"] or None, det)
                # Uma 2ª chance quando o fisco NÃO respondeu (5xx intermitente). Não repete
                # quando ele respondeu «não tenho» — aí insistir só gasta chamada.
                if not xml and _sem_resposta(det):
                    time.sleep(intervalo)
                    det = {}
                    xml = await _buscar_xml_nfse(db, chave, r["cert"] or None, det)
            except Exception as e:  # noqa: BLE001 — uma nota ruim não para o lote
                erro += 1
                print(f"  [{i}/{len(alvos)}] nº {r['numero']}: ERRO {type(e).__name__}: {str(e)[:70]}")
            else:
                if xml:
                    ok += 1
                    print(f"  [{i}/{len(alvos)}] nº {r['numero']}: OK {len(xml)} chars")
                elif _sem_resposta(det):
                    # NÃO é «o fisco não tem»: é «não consegui perguntar». Somar os dois num
                    # número só foi o que quase me fez relatar «o ADN não tem as notas da
                    # Patrimonial» quando o certificado dela é que abria com a senha errada.
                    rede += 1
                    por_empresa.setdefault(emp, []).append(i)
                    print(f"  [{i}/{len(alvos)}] nº {r['numero']}: FALHA DE ACESSO"
                          f" ({det.get('status') or det.get('motivo')}) · {emp}")
                else:
                    vazio += 1
                    print(f"  [{i}/{len(alvos)}] nº {r['numero']}: o fisco respondeu SEM xml ({emp})")
            if i < len(alvos):
                time.sleep(intervalo)

    print(f"\n  trouxeram XML                 : {ok}")
    print(f"  o fisco respondeu SEM xml     : {vazio}")
    print(f"  FALHA DE ACESSO (nao perguntei): {rede}")
    print(f"  erro inesperado               : {erro}")
    for emp, idxs in por_empresa.items():
        print(f"     falha de acesso concentrada em «{emp}»: {len(idxs)} nota(s)")
    print(f"\nTOTAL: {ok} NFS-e com XML guardado")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
