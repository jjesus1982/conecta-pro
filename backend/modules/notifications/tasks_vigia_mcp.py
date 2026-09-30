"""Alarme de DERIVA entre a imagem do conector MCP no ar e a fonte no git.

O problema que isto fecha: em 30/09/2026 os containers do MCP rodavam uma imagem de 19/09
enquanto `mcp-server/` já tinha onze dias de commits, e a parede de testes estava vermelha
desde as 15:05 daquele dia. Nada media isso. Nem CI (a branch de trabalho não casa com os
globs de `.github/workflows/ci.yml`, e havia 2178 commits sem push), nem o compose, nem o
healthcheck — um container pode estar `healthy` servindo código de duas semanas atrás.

**São duas perguntas diferentes e esta responde a segunda.** "O build passa?" é uma; "o que
está NO AR é o que está no git?" é outra, e era a que ninguém podia responder. Um alerta só
da primeira diria "o build está quebrado" enquanto produção seguia feliz com código antigo,
e quem lesse concluiria que o problema era teórico.

**Mora no Celery de propósito**, igual ao vigia dos oráculos: quem vigia não pode depender
do mesmo mecanismo que vigia. A MEDIÇÃO é cron do host (`scripts/mcp_deriva_imagem.sh`),
porque o label da imagem só existe onde o docker está e o backend não tem socket; o
ALARME é beat do Celery. Um cron quebrado não silencia os dois — e a ausência da batida é
alarme por si, pela mesma razão que fez os 59 oráculos apodrecerem: silêncio que significa
"tudo igual" e "ninguém conferiu" ao mesmo tempo não significa nada.

Imagem sem o label (`ausente`) ou com `desconhecido` conta como DERIVA, não como igual:
imagem sem procedência é exatamente o caso que se quer pegar.

Só LÊ. Quem grava a batida é `scripts/mcp_deriva_imagem.sh`, por psql — o script é novo e
o backend é baked, então um arquivo novo aqui só existiria no container depois de um rebuild
do ERP inteiro, que é o ciclo de deploy que esta medição existe para vigiar.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from celery import shared_task
from sqlalchemy import text

logger = logging.getLogger(__name__)

_CHAVE = "mcp.deriva_imagem"

#: A medição é diária + folga para um deploy ter adiado a rodada, igual ao vigia dos oráculos.
_TOLERANCIA = timedelta(hours=30)

#: Procedência que não prova nada. Tratada como deriva de propósito.
_SEM_PROCEDENCIA = {"", "ausente", "desconhecido", None}


def _tocar(db, titulo: str, corpo: str, chave_idem: str, extra_campos: dict) -> int:
    """Um aviso por dia no sino dos admins, mesma mecânica de task_falha."""
    from modules.notifications.task_falha import _SQL_DESTINATARIOS, _SQL_SINO

    extra = json.dumps(
        {
            "idempotency_key": chave_idem,
            "origem": "vigia_mcp",
            "familia": "sistema",
            "severidade": "critico",
            **extra_campos,
        }
    )
    destinatarios = [r[0] for r in db.execute(text(_SQL_DESTINATARIOS)).fetchall()]
    for uid in destinatarios:
        db.execute(text(_SQL_SINO), {"uid": uid, "title": titulo, "body": corpo, "extra": extra})
    db.commit()
    return len(destinatarios)


@shared_task(name="orq.checar_deriva_mcp")
def checar_deriva_mcp() -> dict:
    """Toca o sino se a imagem no ar não é a do git, ou se ninguém mediu. Silencioso se igual."""
    from core.database.session import SyncSessionLocal

    agora = datetime.now(UTC)
    dia = agora.strftime("%Y-%m-%d")

    with SyncSessionLocal() as db:
        bruto = db.execute(text("SELECT valor FROM system_configs WHERE chave = :c"), {"c": _CHAVE}).scalar()
        medicao = None
        if bruto:
            try:
                medicao = json.loads(bruto)
                datetime.fromisoformat(medicao["em"])
            except Exception as exc:  # noqa: BLE001 — batida ilegível conta como ausência
                logger.warning("[vigia-mcp] batida ilegível (%s) — tratando como ausente", exc)
                medicao = None

        # 1. Ninguém mediu.
        if medicao is None or agora - datetime.fromisoformat(medicao["em"]) > _TOLERANCIA:
            quando = (
                "nunca registrou uma medição"
                if medicao is None
                else f"a última foi há {round((agora - datetime.fromisoformat(medicao['em'])).total_seconds() / 3600, 1)}h"
            )
            corpo = (
                f"A deriva de imagem do conector MCP deveria ser medida todo dia, e {quando}.\n\n"
                f"Isto NÃO quer dizer que a imagem está velha — quer dizer que ninguém está "
                f"mais conferindo. Enquanto a medição não rodar, `healthy` no compose não "
                f"prova que o código no ar é o do git: em 30/09/2026 eram onze dias de "
                f"diferença, com a parede de testes vermelha, e todos os containers "
                f"`healthy`.\n\n"
                f"Onde olhar: `crontab -l | grep mcp_deriva`, e se o conecta-pro-backend "
                f"está de pé.\nRodar à mão: /opt/conecta-pro/scripts/mcp_deriva_imagem.sh"
            )
            n = _tocar(
                db,
                "Ninguém está conferindo a imagem do MCP",
                corpo,
                f"mcp_deriva_ausente:{dia}",
                {"motivo": "medicao_ausente"},
            )
            logger.warning("[vigia-mcp] medição ausente — sino tocado para %s", n)
            return {"ok": False, "motivo": "medicao_ausente", "avisados": n}

        # 2. A parede de testes está vermelha. Antes da deriva de propósito: imagem velha
        #    com build verde é uma coisa, e build quebrado é outra — quem for assar precisa
        #    saber que NÃO PODE antes de saber que está atrasado.
        if medicao.get("parede") == "vermelha":
            corpo = (
                f"A parede de testes de `mcp-server/` está VERMELHA no commit "
                f"{(medicao.get('sha_git') or '?')[:8]}.\n\n"
                f"{medicao.get('parede_erro') or '(sem detalhe registrado)'}\n\n"
                f"Enquanto ela estiver assim, `mcp_deriva_imagem.sh --build` vai falhar e "
                f"nada novo sobe. Em 30/09/2026 ela ficou vermelha por onze dias sem "
                f"ninguém saber, porque nenhuma CI builda este diretório e a branch de "
                f"trabalho não casa com os globs de .github/workflows/ci.yml.\n\n"
                f"Reproduzir: git archive HEAD:mcp-server | docker build -"
            )
            n = _tocar(
                db,
                "A parede de testes do MCP está vermelha",
                corpo,
                f"mcp_parede_vermelha:{dia}",
                {"motivo": "parede_vermelha", "sha_git": medicao.get("sha_git")},
            )
            logger.warning("[vigia-mcp] parede vermelha — sino tocado para %s", n)
            return {"ok": False, "motivo": "parede_vermelha", "avisados": n}

        # 3. Mediu e derivou.
        sha_git = medicao.get("sha_git") or "?"
        containers = medicao.get("containers") or {}
        atrasados = {c: s for c, s in containers.items() if s in _SEM_PROCEDENCIA or s != sha_git}
        if not atrasados:
            logger.info("[vigia-mcp] %s container(es) na imagem de %s — nada a fazer", len(containers), sha_git[:8])
            return {"ok": True, "sha_git": sha_git, "containers": len(containers)}

        linhas = "\n".join(
            f"  • {c}: {'SEM o label de procedência' if s in _SEM_PROCEDENCIA else s[:8]}"
            for c, s in sorted(atrasados.items())
        )
        corpo = (
            f"O código do conector MCP no ar NÃO é o que está no git.\n\n"
            f"git (último commit em mcp-server/): {sha_git[:8]}\n{linhas}\n\n"
            f"Container `healthy` com imagem velha é o caso que passou em silêncio por onze "
            f"dias em setembro/2026: a parede de testes estava vermelha, ninguém rebuildava, "
            f"e o healthcheck seguia verde porque o processo respondia.\n\n"
            f"Assar e subir: /opt/conecta-pro/scripts/mcp_deriva_imagem.sh --build\n"
            f"depois recriar um container por vez, conferindo entre cada um."
        )
        n = _tocar(
            db,
            "A imagem do MCP no ar está atrás do git",
            corpo,
            f"mcp_deriva:{dia}",
            {"motivo": "deriva", "sha_git": sha_git, "atrasados": sorted(atrasados)},
        )
        logger.warning("[vigia-mcp] deriva em %s container(es) — sino tocado para %s", len(atrasados), n)
        return {"ok": False, "motivo": "deriva", "atrasados": sorted(atrasados), "avisados": n}
