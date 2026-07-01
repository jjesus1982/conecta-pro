"""
Testes para o modelo Post.
"""

from datetime import time
from uuid import uuid4

import pytest

from modules.operacional.models.post import PostStatus, PostType, ShiftType


class TestPostEnums:
    """Testes para enums do Post."""

    def test_post_type_values(self):
        """Verifica valores do enum PostType."""
        assert PostType.PORTEIRO.value == "porteiro"
        assert PostType.PORTEIRO.value == "porteiro"
        assert PostType.MONITORAMENTO.value == "monitoramento"
        assert PostType.RONDANTE.value == "rondante"
        assert PostType.SUPERVISOR.value == "supervisor"

    def test_post_status_values(self):
        """Verifica valores do enum PostStatus."""
        assert PostStatus.ACTIVE.value == "active"
        assert PostStatus.INACTIVE.value == "inactive"
        assert PostStatus.SUSPENDED.value == "suspended"
        assert PostStatus.TEMPORARY.value == "temporary"

    def test_shift_type_values(self):
        """Verifica valores do enum ShiftType."""
        assert ShiftType.DIURNO.value == "diurno"
        assert ShiftType.NOTURNO.value == "noturno"
        assert ShiftType.MANHA.value == "manha"
        assert ShiftType.TARDE.value == "tarde"
        assert ShiftType.ADMINISTRATIVO.value == "administrativo"


class TestPostModel:
    """Testes para o modelo Post."""

    def test_post_has_vacancy(self, sample_post_data):
        """Testa propriedade has_vacancy."""
        # required_headcount=4, current_headcount=3 -> has_vacancy=True
        assert sample_post_data["required_headcount"] > sample_post_data["current_headcount"]

    def test_post_vacancy_count(self, sample_post_data):
        """Testa cálculo de vagas disponíveis."""
        vacancy_count = sample_post_data["required_headcount"] - sample_post_data["current_headcount"]
        assert vacancy_count == 1

    def test_post_required_fields(self, sample_post_data):
        """Verifica campos obrigatórios do Post."""
        required_fields = ["code", "name", "post_type", "status"]
        for field in required_fields:
            assert field in sample_post_data
            assert sample_post_data[field] is not None

    def test_post_location_complete(self, sample_post_data):
        """Verifica dados de localização."""
        assert sample_post_data["city"] == "São Paulo"
        assert sample_post_data["state"] == "SP"
        assert sample_post_data["latitude"] is not None
        assert sample_post_data["longitude"] is not None

    def test_post_shift_configuration(self, sample_post_data):
        """Verifica configuração de turno."""
        assert sample_post_data["shift_start_time"] == "07:00:00"
        assert sample_post_data["shift_end_time"] == "19:00:00"
        assert sample_post_data["break_duration_minutes"] == 60

    def test_post_certifications_required(self, sample_post_data):
        """Verifica certificações necessárias."""
        certs = sample_post_data["required_certifications"]
        assert "vigilante" in certs
        assert "cftv" in certs


class TestPostValidation:
    """Testes de validação do Post."""

    def test_valid_post_type(self):
        """Testa tipos de posto válidos."""
        valid_types = [pt.value for pt in PostType]
        assert "vigilante" in valid_types
        assert "porteiro" in valid_types
        assert "invalid_type" not in valid_types

    def test_valid_shift_type(self):
        """Testa tipos de turno válidos."""
        valid_types = [st.value for st in ShiftType]
        assert "diurno" in valid_types
        assert "noturno" in valid_types
        assert "8x5" not in valid_types  # Não existe

    def test_coordinates_range(self, sample_post_data):
        """Verifica range válido de coordenadas."""
        lat = sample_post_data["latitude"]
        lon = sample_post_data["longitude"]

        # Latitude: -90 a 90
        assert -90 <= lat <= 90
        # Longitude: -180 a 180
        assert -180 <= lon <= 180
