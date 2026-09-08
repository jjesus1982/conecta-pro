"""Controller para TimeSheet (Folha de Ponto)."""
# pylint: disable=unused-argument


from fastapi import APIRouter


router = APIRouter(
    prefix="/time-sheets",
    tags=["Ponto Eletrônico - Folha de Ponto"],
)


