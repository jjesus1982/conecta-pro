"""Oráculo — foto obrigatória da ronda é tirada NA HORA, sobe JUNTO com o checkpoint e o servidor
carimba a chegada (frente 6, 12/09/2026).

Pré-mortem 6.3: o par "POST /checkpoints" + "POST /checkpoints/{id}/fotos" em requisições
separadas gera checkpoint sem foto e foto órfã — o mesmo par que quebrou a assinatura do kit.
Pré-mortem 6.4: o EXIF é editável; a única hora que vale é a do servidor, com a do aparelho
gravada ao lado para auditoria.

Estado medido no nascimento (staging, 12/09 23h): a tabela `inspection_checkpoints` não tinha
como DIZER que uma foto era obrigatória (sem coluna), a API concluiu a ronda `da422b9e…` com um
checkpoint `foto_evidencia` de `photos = []`, e não existia chave idempotente nenhuma — a
retentativa do celular sem sinal duplicaria o checkpoint.

Cinco afirmações — a REGRA, não a fotografia do banco:

  1. O esquema consegue expressar a regra: colunas `foto_obrigatoria`, `hora_aparelho`,
     `hora_servidor`, `device_id`, `chave_idempotente` (ÚNICA), `origem_offline`.
  2. Nenhuma ronda CONCLUÍDA tem checkpoint de foto obrigatória sem imagem capturada na hora —
     e nenhum checkpoint `pendente_foto` dentro de ronda concluída.
  3. Nenhuma imagem órfã: todo arquivo em disco pertence a um checkpoint que o referencia, e toda
     referência no banco tem arquivo em disco.
  4. Toda foto tem hora do servidor (`hora_servidor`; `enviada_em` nas legadas, que também era
     o servidor escrevendo). Se o checkpoint veio offline, tem `hora_aparelho`.
  5. A regra "quando a foto é obrigatória" mora em UMA função do serviço
     (`foto_e_obrigatoria`) e afirma que `foto_evidencia` sempre exige foto.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

COLUNAS = ("foto_obrigatoria", "hora_aparelho", "hora_servidor", "device_id",
           "chave_idempotente", "origem_offline")

#: Quando a coluna ainda não existe, a regra mínima que já valia pelo NOME do tipo.
OBRIG_SEM_COLUNA = "c.checkpoint_type = 'foto_evidencia'"
OBRIG_COM_COLUNA = ("(coalesce(c.foto_obrigatoria,false) OR c.checkpoint_type = 'foto_evidencia' "
                    "OR c.status = 'pendente_foto')")

#: Foto que vale como prova: capturada na hora (câmera, não galeria).
TEM_FOTO_NA_HORA = """EXISTS (
  SELECT 1 FROM jsonb_array_elements(coalesce(c.photos,'[]'::jsonb)) f
  WHERE coalesce((f->>'capturada_na_hora')::boolean, false))"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    falhas: list[str] = []
    gen = get_db()
    db = await gen.__anext__()

    # 1) esquema
    cols = {r[0] for r in (await db.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='inspection_checkpoints'"
    ))).fetchall()}
    faltam = [c for c in COLUNAS if c not in cols]
    for c in faltam:
        falhas.append(f"coluna inspection_checkpoints.{c} não existe — o banco não sabe dizer isso")
    tem_unique = (await db.execute(text(
        "SELECT 1 FROM pg_indexes WHERE tablename='inspection_checkpoints' "
        "AND indexdef ILIKE '%UNIQUE%' AND indexdef ILIKE '%chave_idempotente%'"))).first()
    if not tem_unique:
        falhas.append("não há índice ÚNICO em chave_idempotente — a retentativa offline duplica checkpoint")
    obrig = OBRIG_SEM_COLUNA if faltam else OBRIG_COM_COLUNA

    # 2) ronda concluída com obrigatória sem foto na hora
    sem_foto = (await db.execute(text(f"""
        SELECT r.code, c.id::text, c.checkpoint_type, c.status
        FROM inspection_checkpoints c
        JOIN inspection_rounds r ON r.id = c.inspection_round_id
        WHERE r.status = 'concluida' AND r.is_active AND c.is_active
          AND {obrig} AND NOT {TEM_FOTO_NA_HORA}
        ORDER BY r.code"""))).fetchall()
    for code, cid, tipo, st in sem_foto:
        falhas.append(f"ronda {code} CONCLUÍDA com checkpoint {cid[:8]} ({tipo}, {st}) de foto "
                      f"obrigatória sem imagem capturada na hora")

    # 3) órfãs — disco × banco, nas duas direções
    # mesmo diretório que o controller (produção: /app/uploads; staging: UPLOADS_DIR=/tmp/uploads)
    fotos_dir = Path(os.environ.get("UPLOADS_DIR", "/app/uploads")) / "rondas"
    ref = (await db.execute(text("""
        SELECT c.inspection_round_id::text, c.id::text, f->>'arquivo'
        FROM inspection_checkpoints c, jsonb_array_elements(coalesce(c.photos,'[]'::jsonb)) f
        WHERE f->>'arquivo' IS NOT NULL"""))).fetchall()
    no_banco = {(r, c, a) for r, c, a in ref}
    no_disco: set[tuple[str, str, str]] = set()
    if fotos_dir.is_dir():
        for p in fotos_dir.glob("*/*/*"):
            if p.is_file():
                no_disco.add((p.parent.parent.name, p.parent.name, p.name))
    for r, c, a in sorted(no_disco - no_banco):
        falhas.append(f"imagem órfã em disco: rondas/{r[:8]}…/{c[:8]}…/{a} sem checkpoint que a referencie")
    for _r, c, a in sorted(no_banco - no_disco):
        falhas.append(f"checkpoint {c[:8]} referencia {a} e o arquivo não existe em disco")

    # 4) carimbo do servidor em toda foto; hora do aparelho quando veio offline
    sel_offline = "coalesce(c.origem_offline,false)" if "origem_offline" in cols else "false"
    sel_hora_ap = "c.hora_aparelho" if "hora_aparelho" in cols else "NULL"
    carimbos = (await db.execute(text(f"""
        SELECT c.id::text, f->>'arquivo', f->>'hora_servidor', f->>'enviada_em', f->>'hora_aparelho',
               {sel_offline}, {sel_hora_ap}
        FROM inspection_checkpoints c, jsonb_array_elements(coalesce(c.photos,'[]'::jsonb)) f"""))).fetchall()
    for cid, arq, h_srv, legado, h_ap, offline, cp_h_ap in carimbos:
        if not (h_srv or legado):
            falhas.append(f"foto {arq} do checkpoint {cid[:8]} sem hora do servidor")
        if offline and not (h_ap or cp_h_ap):
            falhas.append(f"foto {arq} do checkpoint {cid[:8]} veio offline e não tem hora do aparelho")

    # 5) chave duplicada
    dup = []
    if "chave_idempotente" in cols:
        dup = (await db.execute(text("""
            SELECT chave_idempotente, count(*) FROM inspection_checkpoints
            WHERE chave_idempotente IS NOT NULL GROUP BY 1 HAVING count(*) > 1"""))).fetchall()
    for chave, n in dup:
        falhas.append(f"chave idempotente {chave} repetida {n}x — a retentativa duplicou")

    # 6) a regra mora no serviço, e foto_evidencia sempre exige foto
    try:
        from modules.operacional.inspection_rounds.services.inspection_round_service import (
            foto_e_obrigatoria,
        )
        if not foto_e_obrigatoria("foto_evidencia", False):
            falhas.append("foto_e_obrigatoria('foto_evidencia') devolve False — o tipo diz FOTO e não exige foto")
        if not foto_e_obrigatoria("verificacao_posto", True):
            falhas.append("foto_e_obrigatoria ignora o flag foto_obrigatoria do cliente")
        if foto_e_obrigatoria("observacao_geral", False):
            falhas.append("foto_e_obrigatoria exige foto de observação geral — travaria ronda sem motivo")
    except ImportError:
        falhas.append("o serviço não tem foto_e_obrigatoria — a regra de foto obrigatória não existe no código")

    print(f"colunas faltando: {len(faltam)} · concluídas sem foto na hora: {len(sem_foto)} · "
          f"fotos no banco: {len(no_banco)} · em disco: {len(no_disco)} · chaves duplicadas: {len(dup)}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na ronda com foto")
    print("OK ronda com foto: esquema expressa a regra, nenhuma concluída sem imagem na hora, "
          "nenhuma órfã, toda foto carimbada pelo servidor, nenhuma chave repetida")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
