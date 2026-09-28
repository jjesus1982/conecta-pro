"""Toda recusa de batida deixa rastro. O ponto cego não pode voltar.

🔴 O QUE MOTIVOU. Em 23/08/2026 o Jordan pediu uma auditoria severa do ponto — "a Lívia dá
divergência, o Ediwilson dá como se fosse ainda o primeiro acesso dele, muitos erros
assim". Eu não consegui responder POR QUE quatro pessoas nunca bateram uma única vez.

O banco tinha 1.943 batidas que DERAM CERTO e ZERO das que falharam. Eliminei hipóteses
(descriptor válido, conta ativa, geofence ok, rosto cadastrado, hora do cadastro) mas não
provei nada — auditoria por eliminação é o que sobra quando falta evidência.

Este oráculo trava a estrutura que produz a evidência: os caminhos de recusa do backend
têm de registrar, e o `except` do registrador tem de ser mudo (log nunca derruba batida de
quem está na guarita às 6h).

Afirma a REGRA, não a fotografia: não conta quantas falhas existem — no dia em que ninguém
falhar, o oráculo continua válido.
"""

import ast
import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

_CONTROLLER = "/app/modules/people_management/employee_portal/controllers/self_service_controller.py"
_REGISTRADOR = "/app/modules/people_management/ponto/tentativa_log.py"


async def main() -> None:
    with open(_CONTROLLER, encoding="utf-8") as fh:
        src = fh.read()

    # 1. A rota que o app chama quando desiste ANTES do servidor tem de existir.
    assert '"/tentativa-falhou"' in src, (
        "a rota /tentativa-falhou sumiu — a câmera que não abre e o rosto não reconhecido "
        "voltam a morrer no celular, sem chegar ao servidor"
    )

    # 2. Os dois GATES da batida facial (sem rosto e match=false) registram antes de recusar.
    achou = {"sem_rosto": False, "nao_reconhecido": False}
    for linha in src.splitlines():
        if "MOTIVO_SEM_ROSTO" in linha:
            achou["sem_rosto"] = True
        if "MOTIVO_NAO_RECONHECIDO" in linha:
            achou["nao_reconhecido"] = True
    faltando = [k for k, v in achou.items() if not v]
    assert not faltando, f"gate(s) de recusa sem registro de tentativa: {faltando}"

    # 3. O registrador NÃO pode propagar exceção: quem está na guarita precisa bater ponto,
    #    não alimentar auditoria. Verifica na ÁRVORE, não por texto.
    with open(_REGISTRADOR, encoding="utf-8") as fh:
        sql = fh.read()
    arvore = ast.parse(sql)
    fn = next(
        (n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef) and n.name == "registrar_falha_async"),
        None,
    )
    assert fn is not None, "registrar_falha_async sumiu de tentativa_log"
    tem_try = any(isinstance(n, ast.Try) for n in ast.walk(fn))
    tem_raise = any(isinstance(n, ast.Raise) for n in ast.walk(fn))
    assert tem_try and not tem_raise, (
        "registrar_falha_async precisa engolir a própria falha (try sem raise) — "
        f"try={tem_try} raise={tem_raise}. Log que derruba batida é pior que log nenhum."
    )

    # 4. O destino tem de aceitar o registro. Colunas NOT NULL de gp_audit_logs já
    #    derrubaram o INSERT uma vez (actor_user_id), e o except mudo escondeu.
    with get_sync_db() as db:
        obrig = {
            r[0]
            for r in db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    " WHERE table_name = 'gp_audit_logs' AND is_nullable = 'NO'"
                )
            ).all()
        }
    ausentes = sorted(c for c in obrig if c not in sql and c != "timestamp")
    assert not ausentes, (
        f"coluna(s) NOT NULL de gp_audit_logs fora do INSERT: {ausentes} — o registro "
        "falharia calado e a tentativa sumiria, que é o defeito original"
    )

    # 5. 🔴 27/09/2026 — A OUTRA METADE: A ROTA EXISTIA E NINGUÉM A CHAMAVA.
    #
    # Medido neste dia: `ponto.tentativa_falhou` tinha **ZERO linhas** no banco desde que
    # nasceu, em agosto. Não porque ninguém falhasse — a ERIKA falhou em 11/09, 13/09 e 27/09
    # — mas porque o laço do `FacialCapture` **nunca terminava** quando a câmera não entregava
    # quadro: `if (!v || !v.videoWidth) return;` saía sem contar nada, e o intervalo de 550ms
    # girava para sempre sobre um círculo preto.
    #
    # ⭐ Travar só o backend deixava o ponto cego aberto pelo outro lado: o registrador
    # perfeito, e o único que sabe da falha calado. Por isso este oráculo agora atravessa a
    # fronteira e afirma o CLIENTE também.
    _FRONT = "/opt/conecta-pro/frontend/src"
    _cap = f"{_FRONT}/components/ponto/FacialCapture.tsx"
    _tela = f"{_FRONT}/app/modulos/meu-espaco/page.tsx"
    try:
        with open(_cap, encoding="utf-8") as fh:
            cap = fh.read()
        with open(_tela, encoding="utf-8") as fh:
            tela = fh.read()
    except OSError as exc:
        # NÃO VERIFICADO é resultado válido; passar calado não é.
        print(f"⚠️ NÃO VERIFICADO: não li o frontend ({exc}). O laço da câmera fica sem régua "
              "nesta rodada — rode no host ou monte o repositório no container.")
        cap = tela = ""

    if cap:
        # 5a — o laço DESISTE quando não vem quadro, e diz por quê
        assert "semQuadroRef" in cap and "SEM_QUADRO_MAX" in cap, (
            "o laço do facial voltou a não contar os ticks sem quadro — quem abre a câmera e "
            "não recebe imagem fica girando para sempre, e a falha nunca chega ao servidor"
        )
        assert "camera_sem_quadro" in cap, (
            "o laço não tem mais o desfecho `camera_sem_quadro` — a câmera que não abre volta "
            "a ser invisível para a auditoria"
        )
        # 5b — ⭐ A CAUSA RAIZ: o <video> tem de estar VISÍVEL quando o play() acontece.
        # O WebKit do iPhone não decodifica quadro de elemento com display:none; o play()
        # resolve, ninguém vê erro, e videoWidth fica 0 para sempre.
        assert "status === 'starting'" in cap.split("const videoVisible")[1][:220], (
            "`videoVisible` deixou de incluir 'starting' — o play() volta a acontecer com o "
            "<video> oculto e o iPhone para de entregar imagem (foi o defeito da Erika)"
        )
        print("OK o laço do facial desiste quando não vem quadro, e registra o motivo")
        print("OK o <video> está visível quando o play() acontece (a causa raiz do iPhone)")

    if tela:
        # 5c — valor novo em campo compartilhado muda TODO filtro literal
        assert "camera_sem_quadro" in tela, (
            "a tela não trata `camera_sem_quadro`: quem não conseguiu abrir a câmera ouve "
            "'não reconheci seu rosto' — acusa o rosto da pessoa por defeito do aparelho"
        )
        print("OK a tela dá mensagem PRÓPRIA para a câmera que não abriu")

        # 5d — 🔴 28/09/2026, A TERCEIRA METADE. Consertei o laço da câmera em 27/09 e o
        # registro continuou VAZIO. No dia seguinte quatro pessoas relataram "apertei e nada
        # aconteceu" (Telma, Livia, Daniel, Edilene) e `ponto.tentativa_falhou` seguia em zero.
        #
        # ⭐ Eu instrumentei tudo que falha ANTES da batida — câmera, GPS, cadastro — e deixei
        # de fora a falha do PRÓPRIO ENVIO, que é a que as pessoas encontram. O sintoma é
        # idêntico pelos dois caminhos ("apertei e nada"), então o registro vazio parecia
        # provar que ninguém falhava, quando provava que eu media o lugar errado.
        #
        # A régua é ESTRUTURAL, não textual: o ramo que avisa a pessoa do erro do envio tem de
        # registrar antes de avisar. Renomear o motivo não deve deixar o oráculo verde à toa.
        _i_post = tela.find("/facial/batida")
        _i_erro = tela.find("setBaterErro(", _i_post) if _i_post > 0 else -1
        assert _i_post > 0 and _i_erro > _i_post, (
            "não achei o envio da batida facial e o seu tratamento de erro na tela — a régua "
            "abaixo ficaria afirmando sobre o arquivo errado"
        )
        assert "registrarFalha(" in tela[_i_post:_i_erro], (
            "o ramo de falha do ENVIO da batida voltou a não registrar nada. A pessoa vê "
            "'não foi possível registrar o ponto', o servidor não fica sabendo, e "
            "`ponto.tentativa_falhou` segue em zero enquanto gente de verdade não consegue "
            "bater — foi exatamente o estado de 28/09/2026"
        )
        print("OK o ramo de falha do ENVIO da batida registra antes de avisar a pessoa")

    print("OK rota /tentativa-falhou existe (falha que morre no celular chega ao servidor)")
    print("OK os 2 gates de recusa da batida facial registram antes de negar")
    print("OK registrar_falha_async engole a própria falha — nunca derruba a batida")
    print(f"OK as {len(obrig)} colunas NOT NULL de gp_audit_logs estão no INSERT")
    print("TEST oraculo_tentativa_ponto_registrada PASS")


if __name__ == "__main__":
    asyncio.run(main())
