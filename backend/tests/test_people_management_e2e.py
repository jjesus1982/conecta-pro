"""Testes E2E do módulo People Management.

Verifica imports, cálculos CLT e instanciação de skills.
"""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Ensure backend is in path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCLTCalculator:
    """Testes dos cálculos CLT com Decimal."""

    def test_import_clt_calculator(self):
        from modules.people_management.common.utils.clt_calculator import (
            SALARIO_MINIMO,
            TETO_INSS,
            calcular_13_proporcional,
            calcular_adicional_noturno,
            calcular_aviso_previo_dias,
            calcular_dsr_sobre_extras,
            calcular_ferias,
            calcular_fgts_mensal,
            calcular_hora_extra_50,
            calcular_hora_extra_100,
            calcular_hora_normal,
            calcular_insalubridade,
            calcular_inss,
            calcular_irrf,
            calcular_multa_fgts,
            calcular_periculosidade,
            calcular_rescisao,
            calcular_saldo_salario,
            calcular_vale_transporte_desconto,
        )

        assert Decimal("1518.00") == SALARIO_MINIMO
        assert Decimal("8157.41") == TETO_INSS

    def test_inss_salario_minimo(self):
        from modules.people_management.common.utils.clt_calculator import SALARIO_MINIMO, calcular_inss

        inss = calcular_inss(SALARIO_MINIMO)
        # 1518 * 7.5% = 113.85
        assert inss == Decimal("113.85")

    def test_inss_teto(self):
        from modules.people_management.common.utils.clt_calculator import calcular_inss

        inss = calcular_inss(Decimal("10000"))
        # Should be capped at ceiling contribution
        assert inss > Decimal("0")
        assert inss < Decimal("1000")  # Sanity check

    def test_irrf_isento(self):
        from modules.people_management.common.utils.clt_calculator import calcular_irrf

        irrf = calcular_irrf(Decimal("2000"))
        assert irrf == Decimal("0")

    def test_irrf_tributavel(self):
        from modules.people_management.common.utils.clt_calculator import calcular_irrf

        irrf = calcular_irrf(Decimal("5000"))
        assert irrf > Decimal("0")

    def test_hora_normal(self):
        from modules.people_management.common.utils.clt_calculator import calcular_hora_normal

        valor = calcular_hora_normal(Decimal("3000"))
        # 3000 / 220 = 13.636...
        assert valor == Decimal("13.64")

    def test_hora_extra_50(self):
        from modules.people_management.common.utils.clt_calculator import calcular_hora_extra_50

        valor = calcular_hora_extra_50(Decimal("10"), Decimal("10"))
        # 10 * 1.5 * 10 = 150
        assert valor == Decimal("150.00")

    def test_hora_extra_100(self):
        from modules.people_management.common.utils.clt_calculator import calcular_hora_extra_100

        valor = calcular_hora_extra_100(Decimal("10"), Decimal("5"))
        # 10 * 2.0 * 5 = 100
        assert valor == Decimal("100.00")

    def test_adicional_noturno(self):
        from modules.people_management.common.utils.clt_calculator import calcular_adicional_noturno

        valor = calcular_adicional_noturno(Decimal("10"), Decimal("8"))
        # 10 * 0.20 * 8 = 16
        assert valor == Decimal("16.00")

    def test_periculosidade(self):
        from modules.people_management.common.utils.clt_calculator import calcular_periculosidade

        valor = calcular_periculosidade(Decimal("3000"))
        assert valor == Decimal("900.00")

    def test_insalubridade(self):
        from modules.people_management.common.utils.clt_calculator import SALARIO_MINIMO, calcular_insalubridade

        minimo = calcular_insalubridade("minimo")
        medio = calcular_insalubridade("medio")
        maximo = calcular_insalubridade("maximo")
        assert minimo == (SALARIO_MINIMO * Decimal("0.10")).quantize(Decimal("0.01"))
        assert medio > minimo
        assert maximo > medio

    def test_ferias_completas(self):
        from modules.people_management.common.utils.clt_calculator import calcular_ferias

        result = calcular_ferias(Decimal("3000"))
        assert "valor_ferias" in result
        assert "terco_constitucional" in result
        assert "total_bruto" in result
        assert result["valor_ferias"] == Decimal("3000.00")
        assert result["terco_constitucional"] == Decimal("1000.00")
        assert result["total_bruto"] == Decimal("4000.00")

    def test_13_proporcional(self):
        from modules.people_management.common.utils.clt_calculator import calcular_13_proporcional

        valor = calcular_13_proporcional(Decimal("3000"), 6)
        assert valor == Decimal("1500.00")

    def test_aviso_previo_dias(self):
        from modules.people_management.common.utils.clt_calculator import calcular_aviso_previo_dias

        assert calcular_aviso_previo_dias(0) == 30
        assert calcular_aviso_previo_dias(1) == 33
        assert calcular_aviso_previo_dias(20) == 90  # Max cap
        assert calcular_aviso_previo_dias(30) == 90

    def test_fgts_mensal(self):
        from modules.people_management.common.utils.clt_calculator import calcular_fgts_mensal

        fgts = calcular_fgts_mensal(Decimal("3000"))
        assert fgts == Decimal("240.00")

    def test_multa_fgts(self):
        from modules.people_management.common.utils.clt_calculator import calcular_multa_fgts

        multa = calcular_multa_fgts(Decimal("10000"), "sem_justa_causa")
        assert multa == Decimal("4000.00")
        multa_acordo = calcular_multa_fgts(Decimal("10000"), "acordo")
        assert multa_acordo == Decimal("2000.00")
        multa_jc = calcular_multa_fgts(Decimal("10000"), "justa_causa")
        assert multa_jc == Decimal("0")

    def test_vale_transporte(self):
        from modules.people_management.common.utils.clt_calculator import calcular_vale_transporte_desconto

        vt = calcular_vale_transporte_desconto(Decimal("3000"))
        assert vt == Decimal("180.00")

    def test_saldo_salario(self):
        from modules.people_management.common.utils.clt_calculator import calcular_saldo_salario

        saldo = calcular_saldo_salario(Decimal("3000"), 15)
        assert saldo == Decimal("1500.00")

    def test_rescisao_involuntaria(self):
        from datetime import date

        from modules.people_management.common.utils.clt_calculator import calcular_rescisao

        result = calcular_rescisao(
            salario_base=Decimal("3000"),
            tipo_rescisao="involuntary",
            data_admissao=date(2024, 1, 1),
            data_demissao=date(2026, 1, 15),
            saldo_fgts=Decimal("5760"),
            ferias_vencidas_dias=30,
            dias_trabalhados_mes=15,
        )
        assert result["saldo_salario"] > 0
        assert result["aviso_previo_indenizado"] > 0
        assert result["multa_fgts"] > 0
        assert result["total_liquido"] > 0

    def test_rescisao_justa_causa(self):
        from datetime import date

        from modules.people_management.common.utils.clt_calculator import calcular_rescisao

        result = calcular_rescisao(
            salario_base=Decimal("3000"),
            tipo_rescisao="just_cause",
            data_admissao=date(2025, 1, 1),
            data_demissao=date(2026, 1, 15),
            dias_trabalhados_mes=15,
        )
        assert result["ferias_proporcionais"] == Decimal("0")
        assert result["decimo_terceiro_proporcional"] == Decimal("0")
        assert result["multa_fgts"] == Decimal("0")


class TestSkillsImport:
    """Testa que todas as 12 skills podem ser importadas."""

    def test_import_dp_skills(self):
        from modules.people_management.hr.skills import (
            BenefitsSkill,
            ComplianceSkill,
            DocumenterSkill,
            PayrollSkill,
        )

        assert PayrollSkill.SKILL_NAME == "payroll_master"
        assert ComplianceSkill.SKILL_NAME == "compliance_guardian"
        assert DocumenterSkill.SKILL_NAME == "smart_documenter"
        assert BenefitsSkill.SKILL_NAME == "benefits_optimizer"

    def test_import_rh_skills(self):
        from modules.people_management.human_resources.skills import (
            EvaluatorSkill,
            OnboarderSkill,
            PredictorSkill,
            RecruiterSkill,
            TrainerSkill,
        )

        assert RecruiterSkill.SKILL_NAME == "smart_recruiter"
        assert TrainerSkill.SKILL_NAME == "training_advisor"
        assert EvaluatorSkill.SKILL_NAME == "performance_evaluator"
        assert PredictorSkill.SKILL_NAME == "hr_predictor"
        assert OnboarderSkill.SKILL_NAME == "smart_onboarder"

    def test_import_ops_skills(self):
        from modules.people_management.operations.skills import PlannerSkill

        assert PlannerSkill.SKILL_NAME == "workforce_planner"

    def test_import_common_skills(self):
        from modules.people_management.common.skills import NotifierSkill

        assert NotifierSkill.SKILL_NAME == "smart_notifier"

    # test_import_orchestrator REMOVIDO 06/08: OrchestratorSkill era casca — 0 importador
    # vivo (so este teste, que apenas provava que a classe importa). Removido junto com
    # hr/skills/* na higiene F0. Ver docs/superpowers/plans/2026-08-06-dp-agentificacao.md


class TestServicesImport:
    """Testa que todos os services podem ser importados."""

    def test_import_payroll_service(self):
        from modules.people_management.hr.services.payroll_service import PayrollService

        assert hasattr(PayrollService, "calculate_employee_payroll")
        assert hasattr(PayrollService, "close_payroll")

    def test_import_termination_service(self):
        from modules.people_management.hr.services.termination_service import TerminationService

        assert hasattr(TerminationService, "calculate_severance")
        assert hasattr(TerminationService, "complete_termination")

    def test_import_vacation_service(self):
        from modules.people_management.hr.services.vacation_service import VacationService

        assert hasattr(VacationService, "calculate_vacation_balance")
        assert hasattr(VacationService, "approve_vacation")


class TestModelsImport:
    """Testa que todos os 14 models podem ser importados."""

    def test_import_dp_models(self):
        from modules.people_management.hr.models import (
            AdmissionProcess,
            EmployeeBenefit,
            EmploymentContract,
            TerminationProcess,
        )

        assert AdmissionProcess.__tablename__ == "admission_processes"
        assert EmployeeBenefit.__tablename__ == "employee_benefits"
        assert EmploymentContract.__tablename__ == "employment_contracts"
        assert TerminationProcess.__tablename__ == "termination_processes"

    def test_import_rh_models(self):
        from modules.people_management.human_resources.models import (
            CareerPlan,
            PerformanceReview,
            Training,
            TrainingCertificate,
            TrainingCourse,
            TrainingEnrollment,
        )

        assert TrainingCourse.__tablename__ == "training_courses"
        assert Training.__tablename__ == "trainings"
        assert TrainingEnrollment.__tablename__ == "training_enrollments"
        assert TrainingCertificate.__tablename__ == "training_certificates"
        assert PerformanceReview.__tablename__ == "performance_reviews"
        assert CareerPlan.__tablename__ == "career_plans"

    def test_import_portal_models(self):
        from modules.people_management.employee_portal.models import (
            PortalAccess,
            PortalDigitalSignature,
            PortalNotification,
            PortalPreference,
        )

        assert PortalAccess.__tablename__ == "portal_access_logs"
        assert PortalNotification.__tablename__ == "portal_notifications"
        assert PortalPreference.__tablename__ == "portal_preferences"
        assert PortalDigitalSignature.__tablename__ == "portal_digital_signatures"


class TestIntegrationModule:
    """Testa integracao full-duplex DP <-> RH <-> Operacoes."""

    def test_import_events(self):
        from modules.people_management.integration.events import (
            check_mandatory_training,
            on_admission_completed,
            on_candidate_approved,
            on_document_signed,
            on_occurrence_registered,
            on_shift_closed,
            on_termination_initiated,
            on_vacation_approved,
        )

        assert callable(on_shift_closed)
        assert callable(on_occurrence_registered)
        assert callable(on_vacation_approved)
        assert callable(on_candidate_approved)
        assert callable(check_mandatory_training)
        assert callable(on_document_signed)
        assert callable(on_termination_initiated)
        assert callable(on_admission_completed)

    def test_import_services(self):
        from modules.people_management.integration.services import (
            overtime_bank_integration,
            payroll_integration,
            scale_integration,
            time_tracking_integration,
        )

        assert hasattr(time_tracking_integration, "register_from_operations")
        assert hasattr(overtime_bank_integration, "credit")
        assert hasattr(overtime_bank_integration, "debit")
        assert hasattr(payroll_integration, "collect_shift_data")
        assert hasattr(payroll_integration, "collect_benefits_data")
        assert hasattr(scale_integration, "check_availability")

    def test_import_aggregator(self):
        from modules.people_management.integration.aggregator import router

        routes = [r.path for r in router.routes]
        assert "/integration/ops-to-dp/shift-closed" in routes
        assert "/integration/dp-to-ops/vacation-approved" in routes
        assert "/integration/rh-to-dp/candidate-approved" in routes
        assert "/integration/dp-to-ops/termination-notify" in routes
        assert "/integration/dp-to-rh/admission-completed" in routes
        assert "/integration/status" in routes

    def test_integration_flow_count(self):
        from modules.people_management.integration.aggregator import router

        # 10 POST endpoints + 1 GET status = 11 routes
        post_routes = [r for r in router.routes if hasattr(r, "methods") and "POST" in r.methods]
        assert len(post_routes) >= 10


class TestPortalAuth:
    """Testa modulo de autenticacao JWT do portal."""

    def test_import_auth(self):
        from modules.people_management.employee_portal.auth import (
            PORTAL_AUDIENCE,
            CurrentEmployeeId,
            get_portal_employee_id,
        )

        assert callable(get_portal_employee_id)
        assert PORTAL_AUDIENCE == "employee_portal"
        assert CurrentEmployeeId is not None

    def test_portal_controllers_use_auth(self):
        """Verifica que controllers nao tem mais TODO de JWT."""
        import inspect

        from modules.people_management.employee_portal.controllers.my_data_controller import get_my_data

        sig = inspect.signature(get_my_data)
        params = list(sig.parameters.keys())
        assert "employee_id" in params

    def test_portal_payslips_use_auth(self):
        import inspect

        from modules.people_management.employee_portal.controllers.my_payslips_controller import get_my_payslips

        sig = inspect.signature(get_my_payslips)
        params = list(sig.parameters.keys())
        assert "employee_id" in params

    def test_portal_vacations_controller(self):
        import inspect

        from modules.people_management.employee_portal.controllers.my_vacations_controller import get_vacation_balance

        sig = inspect.signature(get_vacation_balance)
        assert "employee_id" in list(sig.parameters.keys())

    def test_portal_trainings_controller(self):
        import inspect

        from modules.people_management.employee_portal.controllers.my_trainings_controller import get_my_enrollments

        sig = inspect.signature(get_my_enrollments)
        assert "employee_id" in list(sig.parameters.keys())

    def test_portal_notifications_controller(self):
        import inspect

        from modules.people_management.employee_portal.controllers.my_notifications_controller import (
            get_my_notifications,
        )

        sig = inspect.signature(get_my_notifications)
        assert "employee_id" in list(sig.parameters.keys())

    def test_portal_aggregator_routes(self):
        from modules.people_management.employee_portal.aggregator import router

        routes = [r.path for r in router.routes]
        assert any("/my-vacations" in r for r in routes)
        assert any("/my-trainings" in r for r in routes)
        assert any("/my-notifications" in r for r in routes)


class TestGAP1EmployeeDP:
    """GAP 1: EmployeeDP model com 50+ campos trabalhistas."""

    def test_import_employee_dp(self):
        from modules.people_management.hr.models.employee_dp import EmployeeDP, GrauInsalubridade, JornadaType

        assert EmployeeDP.__tablename__ == "employee_dp"
        assert JornadaType.PADRAO_44H == "44h_semanais"
        assert GrauInsalubridade.NENHUM == "nenhum"

    def test_employee_dp_has_50_plus_fields(self):
        from modules.people_management.hr.models.employee_dp import EmployeeDP

        columns = [c.name for c in EmployeeDP.__table__.columns]
        assert len(columns) >= 50, f"EmployeeDP tem {len(columns)} campos, esperado >= 50"

    def test_employee_dp_key_fields(self):
        from modules.people_management.hr.models.employee_dp import EmployeeDP

        columns = {c.name for c in EmployeeDP.__table__.columns}
        required = {
            "employee_id",
            "ctps_numero",
            "ctps_serie",
            "pis_pasep",
            "salario_base",
            "jornada_tipo",
            "adicional_periculosidade",
            "grau_insalubridade",
            "vale_transporte",
            "banco_codigo",
            "sindicato_nome",
            "matricula_esocial",
            "optante_fgts",
            "dependentes",
            "data_admissao",
        }
        assert required.issubset(columns), f"Campos faltando: {required - columns}"

    def test_employee_dp_from_models_init(self):
        from modules.people_management.hr.models import EmployeeDP

        assert EmployeeDP.__tablename__ == "employee_dp"


class TestGAP2PayrollExport:
    """GAP 2: Exportação Domínio Sistemas + PDF contracheque."""

    def test_import_payroll_export(self):
        from modules.people_management.hr.services.payroll_export_service import PayrollExportService

        assert hasattr(PayrollExportService, "export_dominio")
        assert hasattr(PayrollExportService, "gerar_contracheque_pdf")
        assert hasattr(PayrollExportService, "gerar_contracheques_batch")

    def test_export_dominio_format(self):
        from modules.people_management.hr.services.payroll_export_service import PayrollExportService

        sample = [
            {
                "employee_name": "JOAO SILVA",
                "cpf": "12345678900",
                "cargo": "VIGILANTE",
                "salario_base": 3000,
                "total_proventos": 3500,
                "total_descontos": 500,
                "salario_liquido": 3000,
                "fgts_8_pct": 280,
                "base_inss": 3500,
                "base_irrf": 3000,
                "proventos": [{"codigo": "001", "descricao": "Salário Base", "ref": "30d", "valor": 3000}],
                "descontos": [{"codigo": "201", "descricao": "INSS", "ref": "", "valor": 500}],
            }
        ]
        output = PayrollExportService.export_dominio(sample, "03/2026")
        assert "DOMINIO|FOLHA|03/2026" in output
        assert "F|" in output
        assert "P|" in output
        assert "D|" in output
        assert "T|" in output

    def test_gerar_contracheque_pdf(self):
        from modules.people_management.hr.services.payroll_export_service import PayrollExportService

        sample = {
            "employee_name": "JOAO SILVA",
            "cargo": "VIGILANTE",
            "reference": "03/2026",
            "salario_base": 3000,
            "total_proventos": 3500,
            "total_descontos": 500,
            "salario_liquido": 3000,
            "fgts_8_pct": 280,
            "base_inss": 3500,
            "base_irrf": 3000,
            "proventos": [{"codigo": "001", "descricao": "Salário Base", "ref": "30d", "valor": 3000}],
            "descontos": [{"codigo": "201", "descricao": "INSS", "ref": "", "valor": 500}],
        }
        pdf = PayrollExportService.gerar_contracheque_pdf(sample)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 1000
        assert pdf[:5] == b"%PDF-"

    def test_from_services_init(self):
        from modules.people_management.hr.services import PayrollExportService

        assert callable(PayrollExportService.export_dominio)


class TestGAP3ESocial:
    """GAP 3: Geração XML eSocial (S-2200, S-2299)."""

    def test_import_esocial(self):
        from modules.people_management.hr.services.esocial_service import ESocialEventService

        assert hasattr(ESocialEventService, "gerar_s2200")
        assert hasattr(ESocialEventService, "gerar_s2299")
        assert hasattr(ESocialEventService, "validar_xml")

    def test_gerar_s2200(self):
        from modules.people_management.hr.services.esocial_service import ESocialEventService

        xml = ESocialEventService.gerar_s2200(
            empregador_cnpj="35710481000103",
            empregador_razao="Conecta Mais Patrimonial",
            trabalhador={"cpf": "12345678900", "nome": "Joao Silva", "data_nascimento": "1990-01-01"},
            contrato={"data_admissao": "2026-03-01", "salario": 3000, "matricula": "000001"},
        )
        assert "<?xml" in xml
        assert "eSocial" in xml
        assert "evtAdmissao" in xml
        assert "12345678900" in xml

    def test_gerar_s2299(self):
        from datetime import date

        from modules.people_management.hr.services.esocial_service import ESocialEventService

        xml = ESocialEventService.gerar_s2299(
            empregador_cnpj="35710481000103",
            trabalhador_cpf="12345678900",
            matricula="000001",
            data_desligamento=date(2026, 3, 15),
        )
        assert "<?xml" in xml
        assert "evtDeslig" in xml
        assert "2026-03-15" in xml

    def test_validar_xml(self):
        from modules.people_management.hr.services.esocial_service import ESocialEventService

        xml = ESocialEventService.gerar_s2200(
            empregador_cnpj="35710481000103",
            empregador_razao="Test",
            trabalhador={"cpf": "12345678900", "nome": "Test"},
            contrato={"data_admissao": "2026-01-01", "salario": 1518, "matricula": "001"},
        )
        result = ESocialEventService.validar_xml(xml)
        assert result["valid"] is True
        assert result["errors"] == []

    def test_from_services_init(self):
        from modules.people_management.hr.services import ESocialEventService

        assert callable(ESocialEventService.gerar_s2200)


class TestGAP4ResumeParser:
    """GAP 4: Parser de currículos (PDF/DOCX + IA)."""

    def test_import_resume_parser(self):
        from modules.people_management.human_resources.services.resume_parser_service import ResumeParserService

        assert hasattr(ResumeParserService, "extract_text_pdf")
        assert hasattr(ResumeParserService, "extract_text_docx")
        assert hasattr(ResumeParserService, "analyze_with_claude")
        assert hasattr(ResumeParserService, "parse_resume")

    def test_fallback_regex_parse(self):
        from modules.people_management.human_resources.services.resume_parser_service import ResumeParserService

        text = """João Silva
joao@email.com
(92) 99999-1234

Habilidades:
Python, FastAPI, SQL, Docker

Idiomas:
Português - Nativo
Inglês - Avançado
"""
        result = ResumeParserService._fallback_regex_parse(text)
        assert result["dados_pessoais"]["email"] == "joao@email.com"
        assert "(92) 99999-1234" in result["dados_pessoais"]["telefone"]
        assert result["_source"] == "regex_fallback"
        assert len(result["habilidades"]) >= 3

    def test_extract_text_txt(self):
        from modules.people_management.human_resources.services.resume_parser_service import ResumeParserService

        text = ResumeParserService.extract_text(b"Hello World", "test.txt")
        assert text == "Hello World"

    def test_from_services_init(self):
        from modules.people_management.human_resources.services import ResumeParserService

        assert callable(ResumeParserService.parse_resume)


class TestGAP5Evaluation360:
    """GAP 5: Avaliação 360° com 5 tipos de avaliador."""

    def test_import_evaluation_360(self):
        from modules.people_management.human_resources.services.evaluation_360_service import (
            DEFAULT_WEIGHTS,
            Evaluation360Service,
            EvaluationStatus,
            EvaluatorType,
        )

        assert len(EvaluatorType) == 5
        assert set(EvaluatorType) == {"self", "manager", "peer", "subordinate", "client"}
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.01

    def test_full_cycle(self):
        from datetime import date

        from modules.people_management.human_resources.services.evaluation_360_service import (
            EVALUATION_DIMENSIONS,
            Evaluation360Service,
            EvaluatorType,
        )

        svc = Evaluation360Service()
        cycle = svc.create_cycle("emp1", "João Silva", date(2026, 1, 1), date(2026, 3, 31))
        assert cycle.status.value == "draft"

        svc.start_collecting(cycle.id)
        assert cycle.status.value == "collecting"

        # Submit 5 types
        dim_ids = [d["id"] for d in EVALUATION_DIMENSIONS]
        for etype in EvaluatorType:
            scores = dict.fromkeys(dim_ids, 8.0)
            svc.submit_response(cycle.id, f"eval_{etype}", etype, f"Avaliador {etype}", scores)

        assert len(cycle.responses) == 5

        result = svc.calculate_final_score(cycle.id)
        assert result["final_score"] > 0
        assert result["classification"] in ["Excepcional", "Acima da Expectativa", "Atende Expectativa"]
        assert result["total_responses"] == 5
        assert len(result["by_evaluator_type"]) == 5

    def test_weighted_scoring(self):
        from datetime import date

        from modules.people_management.human_resources.services.evaluation_360_service import (
            EVALUATION_DIMENSIONS,
            Evaluation360Service,
            EvaluatorType,
        )

        svc = Evaluation360Service()
        cycle = svc.create_cycle("emp2", "Maria Santos", date(2026, 1, 1), date(2026, 3, 31))
        svc.start_collecting(cycle.id)

        dim_ids = [d["id"] for d in EVALUATION_DIMENSIONS]

        # Manager gives 10, self gives 2 — manager weight is higher
        svc.submit_response(cycle.id, "mgr1", EvaluatorType.MANAGER, "Gestor", dict.fromkeys(dim_ids, 10))
        svc.submit_response(cycle.id, "self1", EvaluatorType.SELF, "Auto", dict.fromkeys(dim_ids, 2))

        result = svc.calculate_final_score(cycle.id)
        # Manager weight 0.35/(0.35+0.10)=0.778, self 0.222 → ~8.22
        assert result["final_score"] > 7  # Closer to manager's score

    def test_from_services_init(self):
        from modules.people_management.human_resources.services import Evaluation360Service

        assert callable(Evaluation360Service)


class TestGAP6ScaleOptimizer:
    """GAP 6: Otimizador de Escalas (Húngaro + Greedy)."""

    def test_import_optimizer(self):
        from modules.people_management.operations.services.scale_optimizer_service import (
            HAS_SCIPY,
            Employee,
            Post,
            ScaleOptimizerService,
        )

        assert hasattr(ScaleOptimizerService, "optimize")
        assert hasattr(ScaleOptimizerService, "optimize_month")
        assert HAS_SCIPY is True, "scipy deve estar disponível"

    def test_optimize_basic(self):
        from datetime import date

        from modules.people_management.operations.services.scale_optimizer_service import (
            Employee as OptEmployee,
        )
        from modules.people_management.operations.services.scale_optimizer_service import (
            Post,
            ScaleOptimizerService,
        )

        svc = ScaleOptimizerService()
        employees = [
            OptEmployee(id="v1", name="Vigilante 1", qualifications=["armed"], cost_per_hour=20, score=8),
            OptEmployee(id="v2", name="Vigilante 2", qualifications=["armed"], cost_per_hour=18, score=7),
            OptEmployee(id="v3", name="Vigilante 3", qualifications=[], cost_per_hour=15, score=6),
        ]
        posts = [
            Post(id="p1", name="Posto A", required_qualifications=["armed"], shift_hours=12, requires_armed=True),
            Post(id="p2", name="Posto B", required_qualifications=[], shift_hours=12),
        ]
        result = svc.optimize(date(2026, 3, 15), employees, posts)
        assert len(result["assignments"]) == 2
        assert result["stats"]["method"] in ("hungarian", "greedy")
        # Posto A deve ter vigilante armado
        armed_post = next(a for a in result["assignments"] if a["post_id"] == "p1")
        assert armed_post["employee_id"] in ("v1", "v2")  # Apenas armados

    def test_greedy_fallback(self):
        from datetime import date

        from modules.people_management.operations.services.scale_optimizer_service import (
            Employee as OptEmployee,
        )
        from modules.people_management.operations.services.scale_optimizer_service import (
            Post,
            ScaleOptimizerService,
        )

        employees = [OptEmployee(id="v1", name="V1", cost_per_hour=20, score=8)]
        posts = [Post(id="p1", name="P1", shift_hours=12)]
        result = ScaleOptimizerService._solve_greedy(employees, posts, [[20 * 12]], date(2026, 3, 15))
        assert len(result) == 1

    def test_from_services_init(self):
        from modules.people_management.operations.services import ScaleOptimizerService

        assert callable(ScaleOptimizerService)
