"""
Alias routes para compatibilidade frontend PT-BR.

Implementam endpoints espelhados nos paths PT-BR
que executam as mesmas queries dos endpoints EN.
"""


from fastapi import APIRouter


banco_horas_alias = APIRouter(
    prefix="/banco-horas",
    tags=["Operacional - Banco Horas"],
)
ocorrencias_alias = APIRouter(
    prefix="/ocorrencias",
    tags=["Operacional - Ocorrencias"],
)
ferias_alias = APIRouter(
    prefix="/ferias",
    tags=["Operacional - Ferias"],
)
scale_templates_alias = APIRouter(
    prefix="/scale-templates",
    tags=["Operacional - Scale Templates"],
)


