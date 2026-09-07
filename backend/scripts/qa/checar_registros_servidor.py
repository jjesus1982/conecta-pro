#!/usr/bin/env python3
"""Os REGISTROS do servidor estão cheios — no processo que serve, não no que testa?

Lei da casa (missão de 06/09/2026): *a dívida daqui quase nunca é código faltando — é código
DESLIGADO*. Os executores de aprovação nunca eram carregados pelo servidor: o módulo que os
registra só era importado pelos ORÁCULOS. Testes 8/8 verdes sobre capacidade morta,
aprovações travadas 3 dias. `test_executores_no_servidor` fechou aquele caso; esta trava
fecha a FAMÍLIA: todo registro que o servidor monta em memória.

    rotas montadas · tools do orquestrador · executores de rascunho · tools do agente de
    WhatsApp (dono E não-dono — os dois valores, a diferença é o controle) · regras
    proativas · beat do Celery · builders do redesign

Regra de medição: `import main_production` PRIMEIRO. O que este arquivo importa depois é
só para LER o registro — nunca o módulo que o preenche, senão o teste cria o mundo que quer
ver (foi assim que 8/8 passou verde).

Memória: a última contagem fica em `system_configs` (chave `qa.registros_servidor`). Reprova
quando um registro está VAZIO ou ENCOLHEU desde a última medição — capacidade que some
calada é exatamente o que ninguém vê. Crescer atualiza sozinho; encolher de propósito
(apagou tools) exige `--aceitar`.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_registros_servidor.py [--aceitar]
"""
from __future__ import annotations

import json
import sys

CHAVE = "qa.registros_servidor"


def _contar() -> dict[str, int]:
    sys.path.insert(0, "/app")
    import main_production  # noqa: F401,PLC0415 — PRIMEIRO, sempre
    from main_production import app  # noqa: PLC0415

    n: dict[str, int] = {"rotas": len(app.routes)}
    from modules.ai.conversation.services.orquestrador import tool_registry as TR  # noqa: PLC0415
    n["tools_orquestrador"] = len(getattr(TR, "_REGISTRY", {}) or {})
    from modules.ai.conversation.services.orquestrador.acoes import rascunho as R  # noqa: PLC0415
    # Os executores são registrados por uma GUARDA no caminho da aprovação (conserto de
    # 31/08: o servidor não importa `tools_acao_crm` no startup). Medir sem chamar a guarda
    # dava 0 e era falso alarme (06/09). O que se mede é: a guarda, neste processo, enche?
    R._garantir_executores()
    n["executores_rascunho"] = len(getattr(R, "EXECUTORES", {}) or {})
    from modules.integrations.connectors.whatsapp import agent_service as A  # noqa: PLC0415
    n["tools_whatsapp_dono"] = len(A._tools_ativas(owner=True))
    n["tools_whatsapp_publico"] = len(A._tools_ativas(owner=False))
    from modules.notifications.proativo import regras  # noqa: PLC0415
    n["regras_proativas"] = len(regras.REGISTRY)
    from celery_app import app as celery  # noqa: PLC0415
    n["beats"] = len(celery.conf.beat_schedule or {})
    from modules.operacional.controllers import redesign_data_controller as RD  # noqa: PLC0415
    n["builders_redesign"] = len(RD.BUILDERS)
    return n


def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database.session import SyncSessionLocal  # noqa: PLC0415

    agora = _contar()
    with SyncSessionLocal() as db:
        bruto = db.execute(text("SELECT valor FROM system_configs WHERE chave = :c"), {"c": CHAVE}).scalar()
        antes = json.loads(bruto) if bruto else {}
        ruins = []
        for k, v in agora.items():
            a = antes.get(k)
            if v == 0:
                ruins.append(f"{k}: VAZIO")
                print(f"  x {k}: 0  VAZIO no processo do servidor")
            elif a is not None and v < a and "--aceitar" not in sys.argv:
                ruins.append(f"{k}: {a} -> {v}")
                print(f"  x {k}: {a} -> {v}  ENCOLHEU")
            else:
                print(f"  {k}: {v}" + (f"  (era {a})" if a is not None and a != v else ""))
        # o controle: dono ≠ público, senão o parâmetro não faz nada
        if agora["tools_whatsapp_dono"] == agora["tools_whatsapp_publico"]:
            ruins.append("tools_whatsapp: dono == público")
            print("  x tools do WhatsApp: dono == público — o papel não muda nada")
        if not ruins or "--aceitar" in sys.argv:
            db.execute(text("""
                INSERT INTO system_configs (id, chave, valor, descricao, grupo)
                VALUES (gen_random_uuid(), :c, :v, 'Última contagem dos registros do servidor (checar_registros_servidor)', 'qa')
                ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, updated_at = NOW()"""),
                {"c": CHAVE, "v": json.dumps(agora)})
            db.commit()
    print(f"\nTOTAL: {len(ruins)} registro(s) vazio(s) ou encolhido(s)")
    return 1 if ruins else 0


if __name__ == "__main__":
    raise SystemExit(main())
