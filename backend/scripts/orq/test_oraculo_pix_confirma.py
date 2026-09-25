"""Prova que o extrator de chave PIX lê o que a pessoa escreveu e NUNCA chuta o ambíguo.

Existe porque 11 dígitos é CPF **e** celular ao mesmo tempo. Chutar aqui manda salário para o
lugar errado com aparência de acerto — e o defeito só apareceria no dia do pagamento.
"""
import os
import sys

sys.path.insert(0, "/app")
from modules.integrations.connectors.whatsapp.pix_confirma import (  # noqa: E402
    chave_do_texto, confirmou_o_atual,
)

CASOS = [
    # (texto da pessoa, chave esperada, tipo esperado, por que importa)
    ("sim", None, None, "confirmação pura não traz chave"),
    ("Sim, é essa mesmo", None, None, "confirmação com enfeite"),
    ("isso, ta certo", None, None, "confirmação coloquial"),
    ("meu pix é o telefone 92 99254-2414", "+5592992542414", "telefone",
     "a PALAVRA 'telefone' desambigua os 11 dígitos"),
    ("é meu cpf 92992542414", "92992542414", "cpf", "a palavra 'cpf' desambigua os MESMOS dígitos"),
    ("92992542414", "92992542414", None,
     "⭐ 11 dígitos SEM a pessoa dizer o tipo = AMBÍGUO, tipo fica None"),
    ("+5592992542414", "+5592992542414", "telefone", "+55 é inequívoco"),
    ("manda pro meu email joao.silva@gmail.com", "joao.silva@gmail.com", "email", "e-mail"),
    ("Joao.Silva@GMAIL.com", "joao.silva@gmail.com", "email", "e-mail vira minúscula"),
    ("123e4567-e89b-12d3-a456-426614174000", "123e4567-e89b-12d3-a456-426614174000", "evp",
     "chave aleatória"),
    ("é o cnpj 68510976000148", "68510976000148", "cnpj", "CNPJ de PJ"),
    ("não sei qual é", None, None, "resposta sem chave não inventa chave"),
    ("bom dia", None, None, "saudação não é chave"),
    ("nubank 92984319426 celular", "+5592984319426", "telefone", "banco + 'celular'"),
]


def main() -> None:
    falhas = []
    for txt, k_esp, t_esp, por in CASOS:
        k, t = chave_do_texto(txt)
        if (k, t) != (k_esp, t_esp):
            falhas.append(f"{por}: {txt!r} -> ({k!r},{t!r}), esperava ({k_esp!r},{t_esp!r})")
        else:
            print(f"  ok  {txt[:38]:40} → {str(k):30} {str(t or 'AMBIGUO'):9} {por}")

    # Suspender 1: o ambíguo NUNCA sai com tipo. Se sair, `aplicar()` deixaria passar.
    _, t = chave_do_texto("92992542414")
    if t is not None:
        falhas.append("REGRESSÃO: 11 dígitos sem contexto ganhou tipo — aplicar() aceitaria")

    # Suspender 2: quem manda chave nova NÃO está confirmando a atual (senão a nova se perde).
    if confirmou_o_atual("sim, use o telefone 92 99254-2414"):
        falhas.append("REGRESSÃO: mensagem com chave nova foi lida como 'confirmou a atual'")

    # Suspender 3: a mesma cadeia de dígitos com rótulos opostos tem de dar resultados opostos.
    if chave_do_texto("telefone 92992542414") == chave_do_texto("cpf 92992542414"):
        falhas.append("REGRESSÃO: o rótulo deixou de desambiguar")

    falhas += _contrato_escritor_leitor()

    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"TEST pix_confirma FAIL ({len(falhas)} falha(s))")
        sys.exit(1)
    print(f"\nOK {len(CASOS)} casos + 3 travas + contrato escritor↔leitor")
    print("TEST pix_confirma PASS")


def _contrato_escritor_leitor() -> list[str]:
    """Afirma os DOIS lados ao mesmo tempo: quem grava e quem lê usam o mesmo nome de campo.

    Existe por causa de um defeito real de 25/09/2026 no terminal do fiscal: a tela entregava
    `icms_situacao` e o emissor lia `icms_cst`. Nomes parecidos, cada lado certo sozinho, e
    NENHUMA nota fiscal jamais saiu pela tela. Nenhum teste de unidade pega isso — só uma
    afirmação que olhe escritor e leitor juntos.

    Aqui o sintoma seria pior que recusa da SEFAZ: chave PIX aplicada a partir do campo errado
    é dinheiro no lugar errado.
    """
    import asyncio
    import re
    from pathlib import Path

    from sqlalchemy import text

    from core.database import async_session_factory

    ruins: list[str] = []
    CAMPOS = ("chave_informada", "tipo_informado")

    # 1) a coluna existe no banco com ESTE nome?
    async def _colunas() -> set[str]:
        async with async_session_factory() as db:
            rows = (await db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='pix_confirmacoes'"))).all()
            return {r[0] for r in rows}

    cols = asyncio.run(_colunas())
    for c in CAMPOS:
        if c not in cols:
            ruins.append(f"CONTRATO: `{c}` não existe em pix_confirmacoes — escritor e leitor "
                         f"apontam para coluna inexistente")
    if not ruins:
        print(f"  ok  contrato: {', '.join(CAMPOS)} existem na tabela")

    # 2) `aplicar()` lê por NOME, não por posição — r[1] virando `nome` é silencioso
    src = Path("/app/modules/integrations/connectors/whatsapp/pix_confirma.py").read_text()
    corpo = src[src.index("async def aplicar"):]
    corpo = corpo[:corpo.index("async def estado")] if "async def estado" in corpo else corpo
    # ⚠️ Só LINHAS DE CÓDIGO. Na 1ª versão desta régua ela reprovou o conserto: o comentário que
    # explica o perigo contém literalmente `r[1]`, e o caçador mediu o comentário, não o código.
    codigo = "\n".join(
        ln for ln in corpo.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#") and '"""' not in ln
    )
    if re.search(r"\br\[\d\]", codigo):
        ruins.append("REGRESSÃO: `aplicar()` voltou a ler por POSIÇÃO (r[n]). Reordenar o "
                     "SELECT faria pix_key_type receber o nome da pessoa, em silêncio")
    else:
        print("  ok  aplicar() lê por nome, não por posição")

    # 3) o que `pendentes_de_aprovacao` publica é o que `aplicar` consome
    pend = src[src.index("async def pendentes_de_aprovacao"):src.index("async def aplicar")]
    for c in CAMPOS:
        if c not in pend:
            ruins.append(f"CONTRATO: `pendentes_de_aprovacao` não publica `{c}`, que é o campo "
                         f"que `aplicar` consome — a tela de aprovação leria outro nome")
    if not any("pendentes" in r for r in ruins):
        print("  ok  pendentes_de_aprovacao publica os campos que aplicar consome")
    return ruins


if __name__ == "__main__":
    main()
