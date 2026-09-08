"""Controller para TimeEntry (Registros de Ponto)."""
# pylint: disable=unused-argument


from fastapi import APIRouter


router = APIRouter(
    prefix="/time-entries",
    tags=["Ponto Eletrônico - Registros"],
)


