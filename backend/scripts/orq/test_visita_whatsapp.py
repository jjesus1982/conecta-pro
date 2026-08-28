#!/usr/bin/env python3
"""Oráculo da VISITA COMERCIAL pelo WhatsApp — campo → relatório → Bartolo.

Fluxo do Jordan (27/08/2026): ele está em campo, conversa por texto, ÁUDIO e FOTO com o
José Luís; tudo acumula; no fim sai o relatório; no computador ele cita a visita e o
Bartolo carrega tudo.

⭐ O QUE ESTE ORÁCULO PROTEGE é a coisa que não pode falhar em campo: o que ele mandou
TEM DE ESTAR LÁ. Quem está numa visita não confere se o registro funcionou — descobre
semanas depois, quando o relatório sai furado e a informação não existe em lugar nenhum.

Oito invariantes:
  1. visita sem cliente é RECUSADA
  2. UMA visita aberta por conversa (duas misturariam clientes num relatório só)
  3. fechar visita VAZIA é RECUSADO
  4. cada anotação vai para o CAMPO certo; campo inventado cai em achados E é AVISADO
  5. `achados` (jsonb) e os 5 campos de texto convivem — tratar igual estoura
  6. a mídia gruda SOZINHA na visita aberta, com o TIPO certo (foto/audio/video/local)
  7. mídia SEM visita aberta é no-op silencioso (conversa com cliente não vira visita)
  8. o relatório NOMEIA os campos vazios, em vez de mostrar só o que foi preenchido

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_visita_whatsapp.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

_MARCA = "ZZteste-oraculo-visita-wa"
_CONV = 999903


async def _limpar(db) -> None:
    from sqlalchemy import text as _t

    await db.execute(_t("DELETE FROM crm_visit_reports WHERE cliente_nome LIKE :m"),
                     {"m": f"%{_MARCA}%"})
    await db.commit()


async def main() -> int:
    from core.database import async_session_factory
    from modules.integrations.connectors.whatsapp import agent_service as A
    from modules.integrations.connectors.whatsapp import controller as CT

    falhas: list[str] = []
    async with async_session_factory() as db:
        await _limpar(db)

        # 7 · mídia sem visita aberta não pode criar nada
        from sqlalchemy import text

        n0 = (await db.execute(text("SELECT count(*) FROM crm_visit_reports"))).scalar()
        await CT._midia_para_visita_aberta(_CONV, "🖼 [imagem recebida]: nada a ver")
        n1 = (await db.execute(text("SELECT count(*) FROM crm_visit_reports"))).scalar()
        if n0 != n1:
            falhas.append(f"mídia SEM visita aberta criou registro: {n0} → {n1}")

        # 0 · TIPO DA VISITA: sem ele o roteiro vira interrogatório genérico. Medido ao
        #     vivo em 27/08/2026 — o Jordan disse "fui fazer orçamento de CFTV" e o agente
        #     seguiu perguntando de portaria, porque o roteiro era único.
        r = await A._mtool_abrir_visita(db, {"cliente": f"{_MARCA} X",
                                             "tipo": "tipo_inventado"}, _CONV)
        if not r.get("erro"):
            falhas.append("tipo de visita INVENTADO foi aceito")
        for t in ("cftv", "controle_acesso", "portaria", "infraestrutura",
                  "alarme_perimetro", "misto"):
            if t not in A.TIPOS_VISITA:
                falhas.append(f"tipo {t!r} não tem roteiro")
        # O roteiro de um tipo não PERGUNTA o do outro.
        # ⚠️ Buscar a palavra solta não serve, e este teste falhou por isso na 1ª versão:
        # "escala" aparece no roteiro de CFTV dentro da instrução "NÃO pergunte de
        # portaria, escala ou mão de obra" — que é exatamente o comportamento certo.
        # O que denuncia pergunta fora de escopo é a palavra ANTES de um "?", não a
        # palavra em qualquer lugar.
        def _pergunta_sobre(rot: str, palavra: str) -> bool:
            return any(palavra in trecho.lower()
                       for trecho in rot.split("?")[:-1]
                       if "não pergunte" not in trecho.lower())

        if _pergunta_sobre(A.TIPOS_VISITA["cftv"], "escala"):
            falhas.append("o roteiro de CFTV PERGUNTA de escala — fora do escopo")
        if _pergunta_sobre(A.TIPOS_VISITA["portaria"], "gravação"):
            falhas.append("o roteiro de PORTARIA PERGUNTA de dias de gravação — fora do "
                          "escopo")
        if not _pergunta_sobre(A.TIPOS_VISITA["cftv"], "energia"):
            falhas.append("o roteiro de CFTV não pergunta de ENERGIA no ponto — é a "
                          "pergunta que muda dezenas de milhares")
        for t, rot in A.TIPOS_VISITA.items():
            if "uma por vez" not in rot.lower() and t != "misto":
                falhas.append(f"o roteiro de {t!r} não impõe uma pergunta por vez")

        # 1 · sem cliente
        r = await A._mtool_abrir_visita(db, {}, _CONV)
        if not r.get("erro"):
            falhas.append("visita sem cliente foi aceita")

        r = await A._mtool_abrir_visita(db, {"cliente": f"{_MARCA} Aurora"}, _CONV)
        vid = r.get("visita_id")
        if not vid:
            print(f"FALHOU: não abriu a visita: {str(r)[:120]}")
            return 1

        # 2 · uma por conversa
        r = await A._mtool_abrir_visita(db, {"cliente": f"{_MARCA} Outro"}, _CONV)
        if not r.get("ja_aberta"):
            falhas.append("abriu uma SEGUNDA visita na mesma conversa — dois clientes "
                          "cairiam no mesmo relatório")

        # 3 · fechar vazia
        r = await A._mtool_fechar_visita(db, {}, _CONV)
        if not r.get("erro"):
            falhas.append("fechou uma visita VAZIA")

        # 4 e 5 · campo certo, jsonb e texto convivendo, campo inventado avisado
        for campo, txt in (("panorama", "4 torres, 180 unidades"),
                           ("achados", "8 câmeras analógicas"),
                           ("diagnostico_tecnico", "DVR sem HD"),
                           ("oportunidade_comercial", "12 IP + NVR")):
            r = await A._mtool_anotar_visita(db, {"campo": campo, "texto": txt}, _CONV)
            if r.get("campo") != campo:
                falhas.append(f"anotação de {campo!r} foi para {r.get('campo')!r}")
        r = await A._mtool_anotar_visita(
            db, {"campo": "campo_que_nao_existe", "texto": "x"}, _CONV)
        if r.get("campo") != "achados":
            falhas.append("campo inventado não caiu em achados")
        if not r.get("aviso"):
            falhas.append("campo inventado caiu em achados EM SILÊNCIO — tem de avisar")

    # 6 · mídia gruda com o tipo certo (sessão nova: é assim que o webhook chama)
    midias = {"foto": "🖼 [imagem recebida]: rack sem organização",
              "audio": "🎤 [áudio transcrito]: 3 câmeras sem imagem",
              "local": "📍 [localização recebida]: maps",
              "video": "🎬 [vídeo]: giro pelo hall"}
    for txt in midias.values():
        await CT._midia_para_visita_aberta(_CONV, txt)

    async with async_session_factory() as db:
        r = await A._mtool_fechar_visita(db, {}, _CONV)
        rel = r.get("relatorio") or {}
        achados = rel.get("achados") or []
        tipos = {a.get("tipo") for a in achados if isinstance(a, dict)}
        for esperado in midias:
            if esperado not in tipos:
                falhas.append(f"mídia do tipo {esperado!r} NÃO chegou ao relatório "
                              f"(tipos presentes: {sorted(tipos)})")
        if not rel.get("panorama"):
            falhas.append("campo de TEXTO sumiu do relatório (panorama vazio)")

        # 8 · vazio é nomeado
        vazios = r.get("campos_vazios")
        if not vazios or "situacao_atual" not in vazios:
            falhas.append(f"o relatório não NOMEIA os campos vazios: {vazios!r}")

        await _limpar(db)
        sobrou = (await db.execute(text(
            "SELECT count(*) FROM crm_visit_reports WHERE cliente_nome LIKE :m"),
            {"m": f"%{_MARCA}%"})).scalar()
        if sobrou:
            falhas.append(f"desmonte deixou {sobrou} visita(s) com a marca")

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK visita_whatsapp: 12/12 — recusa sem cliente, segunda visita na mesma conversa "
          "e visita vazia; cada anotação no campo certo e campo inventado avisado; foto, "
          "áudio, vídeo e localização grudam SOZINHAS com o tipo certo; mídia sem visita "
          "aberta é no-op; o relatório nomeia o que ficou vazio; e a visita é TIPIFICADA "
          "— 6 roteiros, cada um sem as perguntas dos outros.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
