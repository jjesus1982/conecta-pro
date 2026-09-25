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

    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"TEST pix_confirma FAIL ({len(falhas)} falha(s))")
        sys.exit(1)
    print(f"\nOK {len(CASOS)} casos + 3 travas de regressão")
    print("TEST pix_confirma PASS")


if __name__ == "__main__":
    main()
