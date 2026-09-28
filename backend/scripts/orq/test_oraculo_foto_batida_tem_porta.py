"""A foto da batida tem PORTA — e a porta tem parede.

🔴 MEDIDO EM 28/09/2026. A Pyetra pediu, sobre a rotina dela no Sólides: *"ver as fotos que
foram tiradas para registro de ponto"*. Fui olhar e achei o padrão de sempre desta casa: a
captura funcionava, o armazenamento funcionava, e **não havia porta**.

Medido no dia:
  · **985 arquivos, 39 MB** em `/app/uploads/ponto` (bind mount `./uploads`, sobrevive a deploy)
  · **909 batidas** com `foto_capturada_url` preenchida, desde 14/09
  · e a URL devolvia **404**, no backend (`localhost:8080`) e no público (`erp.conectamais.pro`)

Nenhum `StaticFiles` montado, nenhuma rota devolvendo imagem. ⭐ **A prova biométrica existia e
não chegava a ninguém** — o mesmo padrão de `substitutions` com zero linhas e da fila `ged` sem
consumidor. A dívida quase nunca é código faltando; é código sem porta.

## O que este oráculo trava

1. **A rota existe** e está montada no router de DP.
2. **Ela é gateada.** Foto de rosto de colaborador é dado biométrico: sem a parede de DP isso
   vira diretório aberto. Um `StaticFiles` em `/uploads` seria pior ainda — expõe o diretório
   inteiro a quem enumerar, sem sessão e sem rastro de quem olhou.
3. **O caminho resolve de verdade.** Não basta a rota existir: `foto_capturada_url` tem de virar
   arquivo em disco. Esta é a parte que 404 silencioso esconderia.

⚠️ Afirma a REGRA, não a fotografia: não fixa `punch_id`, nome de pessoa nem quantidade de
fotos. Uma casa sem nenhuma foto no dia é resultado válido e não reprova.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

ROTA = "/ponto/batida/{punch_id}/foto"
#: Prefixo real: o router de ponto é montado sob `/api/v1/people-management/ponto`.
#: ⚠️ Eu primeiro pendurei esta rota no router do REDESIGN e ela ficou em
#: `/api/v1/redesign/ponto/batida/...` — endereço que a tela não chama. A tela
#: (`gestao_de_pessoas.py:577`) pede `/api/v1/people-management/ponto/batida/{id}/foto`.
PREFIXO_ESPERADO = "/api/v1/people-management"


async def main() -> None:
    from modules.people_management.ponto.controllers import punch_controller as pc

    # 1 — a rota existe NO ROUTER CERTO
    caminhos = [r.path for r in pc.router.routes if hasattr(r, "path")]
    assert ROTA in caminhos, f"a porta da foto sumiu do router de ponto ({ROTA})"

    # 2 — e ela está no ENDEREÇO que a tela chama. Rota certa em prefixo errado é 404 igual.
    from main_production import app
    alvo = f"{PREFIXO_ESPERADO}{ROTA}"
    assert any(getattr(x, "path", "") == alvo for x in app.routes), (
        f"a foto não está em {alvo} — a tela chama esse endereço e recebe 404")

    # 3 — e exige sessão. Foto de rosto sem autenticação é vazamento de dado biométrico.
    # ⚠️ Confere o PARÂMETRO, não o texto da anotação: `CurrentActiveUser` é um `Annotated` e
    # `str(signature)` o imprime resolvido, então casar por nome de tipo reprova código correto.
    import inspect
    assert "current_user" in inspect.signature(pc.get_foto_batida).parameters, (
        "a rota da foto perdeu a exigência de sessão — foto de rosto sem autenticação é "
        "vazamento de dado biométrico")

    # 4 — e o caminho resolve mesmo. 404 por arquivo ausente é indistinguível de 404 por rota
    #     ausente para quem está do outro lado da tela; por isso a checagem é de DISCO.
    from modules.people_management.hr.services.cracha_pdf import foto_path

    async with async_session_factory() as db:
        linhas = (await db.execute(text(
            "SELECT punch_id::text, foto_capturada_url FROM gp_clock_punches "
            " WHERE coalesce(foto_capturada_url,'') <> '' "
            " ORDER BY punch_timestamp DESC LIMIT 20"))).all()

        if not linhas:
            print("OK nenhuma batida com foto no banco — nada a resolver (resultado válido)")
            print("TEST oraculo_foto_batida_tem_porta PASS")
            return

        quebradas = [u for _, u in linhas if not foto_path(u)]
        assert not quebradas, (
            f"{len(quebradas)} de {len(linhas)} foto(s) recentes têm URL no banco e NÃO existem "
            f"em disco — ex.: {quebradas[0]}")

        total, com_foto = (await db.execute(text(
            "SELECT count(*), count(foto_capturada_url) FROM gp_clock_punches "
            " WHERE punch_timestamp >= (now() AT TIME ZONE 'America/Manaus')::date - 30"))).first()

        print(f"OK porta montada e gateada · {len(linhas)} foto(s) recentes conferidas em disco · "
              f"{com_foto} de {total} batida(s) dos últimos 30 dias têm foto")

    print("TEST oraculo_foto_batida_tem_porta PASS")


if __name__ == "__main__":
    asyncio.run(main())
