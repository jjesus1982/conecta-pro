"""A conferência de kits não apaga por ignorância, e não deduz condomínio.

🔴 29/09/2026. A Pyetra reclamou de kit com documento de outro condomínio («salvei o Kit do
Mirante e veio informação do Fiori»). Medido: o EULER FELIPE tinha documento em **TRÊS kits** —
Laranjeiras (onde trabalhou), Mirante e Prime Arena. Dois clientes recebiam a folha de pagamento
de um estranho: vazamento de dado pessoal, não desorganização.

Até então a única forma de consertar era script no terminal, e ela não usa terminal.

## O que este oráculo trava

1. **⭐ Quem está apenas SEM RESOLUÇÃO não é removido.** «Sei que essa pessoa é de outro
   condomínio» e «não sei onde ela trabalhou» produziam a mesma linha e consequências opostas —
   a segunda apagaria o vínculo por ignorância NOSSA. Achado pelo teste de ida-e-volta, não pela
   leitura: com a resolução da KELLY removida, o plano dizia «1 vínculo a remover» sobre uma
   pessoa com 49 batidas no mês.

2. **Ensaio é o padrão.** Ato destrutivo nunca é o caminho de menos digitação.

3. **Condomínio que não existiu na competência é RECUSADO.** O Green Hills abriu em 01/09/2026:
   aceitar «Green Hills» como resposta para agosto criaria um kit de um mês que não houve.
   «Condomínio que existe» não basta — precisa ter existido NAQUELE mês.

4. **A regra tem UMA fonte.** `kit_roster_service` serve a tela E o script. A regra mudou três
   vezes em 28/09 (alocação → escala → posto da batida), cada vez por uma correção do Jordan;
   duas cópias teriam divergido na primeira.

⚠️ READ-ONLY: chama o planejador em modo de leitura e afirma a REGRA. Não insere, não remove,
não nomeia pessoa nem condomínio.
"""

import ast
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from core.database.session import get_sync_db  # noqa: E402
from modules.people_management.ged.services import kit_roster_service as krs  # noqa: E402

_ACOES = "/app/modules/operacional/controllers/redesign_builders/documentos.py"


def main() -> None:
    with open(_ACOES, encoding="utf-8") as fh:
        src = fh.read()
    arvore = ast.parse(src)

    # 1 — as duas rotas existem. Sem elas a Pyetra volta a depender de terminal.
    for rota in ("/action/kits-conferir", "/action/kit-definir-condominio"):
        assert f'"{rota}"' in src, (
            f"a rota {rota} desapareceu — conferir kit e resolver condomínio voltam a ser "
            "privilégio de quem tem terminal, e a Pyetra não tem"
        )

    # 2 — ENSAIO é o padrão, no builder E na ação. Ato destrutivo não é o caminho curto.
    assert '"value": "ensaio"' in src, (
        "a tela deixou de vir com «ensaio» selecionado — abrir e clicar passaria a APAGAR"
    )
    fn = next(
        (n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef) and n.name == "rd_kits_conferir"),
        None,
    )
    assert fn is not None, "rd_kits_conferir desapareceu"
    corpo = ast.unparse(fn)
    assert 'or \'ensaio\'' in corpo or 'or "ensaio"' in corpo, (
        "a ação perdeu o default «ensaio»: quem chamar a rota sem dizer a ação passaria a remover"
    )
    # ⭐ A GARANTIA, NÃO O LUGAR. A primeira versão desta asserção exigia trilha e backup no
    # corpo da AÇÃO — e ficou vermelha quando o refactor de 29/09 moveu o ato destrutivo para o
    # serviço, que é onde ele deve estar (a ação e o script do terminal compartilham o mesmo
    # DELETE agora). Oráculo que fixa ONDE o código mora reprova refactor correto.
    #
    # O que importa afirmar: (a) a ação DELEGA em vez de ter DELETE próprio, e (b) quem executa
    # o ato tem backup, trilha e leitura posterior.
    assert "DELETE FROM ged_kit_documents" not in src, (
        "voltou a existir um DELETE na camada de tela. O ato destrutivo tem UM dono — duas "
        "cópias de um DELETE divergem na primeira correção, e a que fica atrás apaga errado"
    )
    assert "aplicar_reconciliacao" in corpo, (
        "a ação não delega mais ao serviço: ou perdeu a capacidade de aplicar, ou voltou a ter "
        "regra própria"
    )

    # 3 — a ação de definir RECUSA condomínio fora da competência.
    fn2 = next(
        (n for n in ast.walk(arvore)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "rd_kit_definir_condominio"),
        None,
    )
    assert fn2 is not None, "rd_kit_definir_condominio desapareceu"
    corpo2 = ast.unparse(fn2)
    assert "condominios_conhecidos" in corpo2 and "não teve ninguém batendo ponto" in corpo2, (
        "a ação aceita qualquer condomínio de novo. O Green Hills abriu em 01/09: aceitá-lo "
        "como resposta de agosto inventa um kit de um mês que não houve"
    )
    assert "ON CONFLICT" in corpo2, (
        "perdeu o ON CONFLICT: reenviar a mesma pessoa duplicaria decisão em vez de corrigir, "
        "e errar e refazer é normal"
    )

    # 4 — ⭐ A REGRA QUE PROTEGE O DOCUMENTO: pendente não é removível.
    with open(krs.__file__.replace(".pyc", ".py"), encoding="utf-8") as fh:
        srv = fh.read()
    for marca, porque in (
        ("CREATE TABLE IF NOT EXISTS", "backup antes de remover"),
        ("gp_audit_logs", "trilha do ato"),
        ("não se confirmou na leitura", "prova por leitura posterior"),
        ("ABORTADO antes de remover", "aborto quando o backup vem menor que o alvo"),
    ):
        assert marca in srv, (
            f"o serviço perdeu {porque} — remoção de vínculo de documento trabalhista sem isso "
            "não acontece nesta casa"
        )
    assert 'ln["tipo"] = "pendente"' in srv and 'ln["employee_id"] = None' in srv, (
        "quem está apenas SEM RESOLUÇÃO voltou a entrar no lote de remoção. O sistema apagaria "
        "vínculo de documento por NÃO SABER onde a pessoa trabalhou — ignorância nossa virando "
        "ato sobre o documento dela"
    )
    assert '"tipo") == "remover"' in srv, (
        "o contador `a_remover` voltou a contar por «employee_id nulo»: três situações "
        "diferentes no mesmo balde, e a mensagem prometia remoção que não haveria"
    )

    # 5 — comportamento real contra o banco, em LEITURA.
    with get_sync_db() as db:
        plano = krs.plano_reconciliacao(db, date(2026, 8, 1))
        r = plano["resumo"]
        pend = {x["employee_id"] for x in plano["sem_condominio"]}
        removiveis = {x["employee_id"] for x in plano["linhas"] if x.get("tipo") == "remover"}
        assert not (pend & removiveis), (
            f"{len(pend & removiveis)} pessoa(s) estão ao mesmo tempo «sem condomínio» e no lote "
            "de remoção — é a contradição exata que o teste de ida-e-volta pegou"
        )
        # A lista de condomínios oferecida é a da COMPETÊNCIA, não a tabela inteira.
        conds = krs.condominios_conhecidos(db, date(2026, 8, 1))
        assert conds, "nenhum condomínio conhecido em 08/2026 — o roster não está achando ninguém"
        assert not any("GREEN" in krs.canon(c) for c in conds), (
            "um condomínio que abriu em setembro aparece como opção de AGOSTO — a lista voltou a "
            "sair de `condominios` em vez de quem bateu ponto no mês"
        )

    print(f"OK as 2 rotas existem · ensaio é o padrão no builder e na ação")
    print("OK a tela DELEGA: nenhum DELETE na camada de tela, o ato tem um dono")
    print("OK o serviço tem backup, trilha, aborto e leitura posterior")
    print(f"OK definir recusa condomínio fora da competência · ON CONFLICT corrige em vez de duplicar")
    print(f"OK pendente NÃO é removível ({len(pend)} pendente(s), {len(removiveis)} removível(is), 0 em comum)")
    print(f"OK {len(conds)} condomínio(s) na competência, nenhum que só existe depois dela")
    print(f"OK plano: {r['kits']} kit(s) · {r['pessoas_no_roster']} pessoa(s) · "
          f"{r['a_remover']} a remover · {r['kits_sem_roster']} sem roster")
    print("TEST oraculo_kits_conferir_tela PASS")


if __name__ == "__main__":
    main()
