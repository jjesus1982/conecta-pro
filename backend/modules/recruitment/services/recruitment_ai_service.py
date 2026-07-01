"""Serviço de IA para Recrutamento."""

import logging
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from modules.recruitment.models.candidate import Candidate
from modules.recruitment.models.candidate_skill import CandidateSkill, SkillLevel
from modules.recruitment.models.job_position import JobPosition

logger = logging.getLogger(__name__)


class RecruitmentAIService:
    """Serviço de IA para recrutamento e seleção."""

    # Pesos para cálculo de matching
    WEIGHTS = {
        "skills_match": 0.35,
        "experience_match": 0.25,
        "education_match": 0.15,
        "salary_match": 0.10,
        "location_match": 0.10,
        "availability_match": 0.05,
    }

    # Mapeamento de níveis de skill para scores
    SKILL_LEVEL_SCORES = {
        SkillLevel.BASICO: 0.25,
        SkillLevel.INTERMEDIARIO: 0.50,
        SkillLevel.AVANCADO: 0.75,
        SkillLevel.EXPERT: 1.0,
    }

    def __init__(self):
        """Inicializa o serviço de IA."""
        self.stop_words = {
            "de",
            "da",
            "do",
            "em",
            "para",
            "com",
            "por",
            "uma",
            "um",
            "os",
            "as",
            "no",
            "na",
            "ao",
            "aos",
            "das",
            "dos",
            "que",
            "e",
            "ou",
            "se",
            "mais",
            "também",
            "como",
            "ser",
            "ter",
        }

    async def calculate_matching_score(
        self,
        candidate: Candidate,
        position: JobPosition,
        candidate_skills: list[CandidateSkill] = None,
    ) -> dict[str, Any]:
        """
        Calcula score de matching entre candidato e vaga.

        Returns:
            Dict com scores detalhados e score final
        """
        scores = {
            "skills_match": 0.0,
            "experience_match": 0.0,
            "education_match": 0.0,
            "salary_match": 0.0,
            "location_match": 0.0,
            "availability_match": 0.0,
        }
        details = {}

        # 1. Match de Skills (35%)
        skills_result = await self._calculate_skills_match(candidate, position, candidate_skills)
        scores["skills_match"] = skills_result["score"]
        details["skills"] = skills_result

        # 2. Match de Experiência (25%)
        experience_result = await self._calculate_experience_match(candidate, position)
        scores["experience_match"] = experience_result["score"]
        details["experience"] = experience_result

        # 3. Match de Educação (15%)
        education_result = await self._calculate_education_match(candidate, position)
        scores["education_match"] = education_result["score"]
        details["education"] = education_result

        # 4. Match de Salário (10%)
        salary_result = self._calculate_salary_match(candidate, position)
        scores["salary_match"] = salary_result["score"]
        details["salary"] = salary_result

        # 5. Match de Localização (10%)
        location_result = self._calculate_location_match(candidate, position)
        scores["location_match"] = location_result["score"]
        details["location"] = location_result

        # 6. Match de Disponibilidade (5%)
        availability_result = self._calculate_availability_match(candidate, position)
        scores["availability_match"] = availability_result["score"]
        details["availability"] = availability_result

        # Calcula score final ponderado
        final_score = sum(score * self.WEIGHTS[key] for key, score in scores.items())

        return {
            "final_score": round(final_score * 100, 1),
            "scores": {k: round(v * 100, 1) for k, v in scores.items()},
            "details": details,
            "recommendation": self._get_recommendation(final_score),
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def _calculate_skills_match(  # pylint: disable=too-many-locals,too-many-branches
        self,
        candidate: Candidate,
        position: JobPosition,
        candidate_skills: list[CandidateSkill] = None,
    ) -> dict[str, Any]:
        """Calcula match de habilidades."""
        required_skills = {s.lower() for s in (position.required_skills or [])}
        desired_skills = {s.lower() for s in (position.desired_skills or [])}

        if not required_skills and not desired_skills:
            return {"score": 0.5, "matched": [], "missing": [], "bonus": []}

        # Extrai skills do candidato
        candidate_skill_names = set()
        skill_levels = {}

        if candidate_skills:
            for skill in candidate_skills:
                name = skill.name.lower()
                candidate_skill_names.add(name)
                skill_levels[name] = self.SKILL_LEVEL_SCORES.get(skill.level, 0.5)

        # Adiciona tags do candidato
        if candidate.tags:
            for tag in candidate.tags:
                candidate_skill_names.add(tag.lower())

        # Calcula matches
        matched_required = []
        missing_required = []
        matched_desired = []

        for skill in required_skills:
            match = self._find_skill_match(skill, candidate_skill_names)
            if match:
                level_score = skill_levels.get(match, 0.5)
                matched_required.append(
                    {
                        "skill": skill,
                        "matched_with": match,
                        "level_score": level_score,
                    }
                )
            else:
                missing_required.append(skill)

        for skill in desired_skills:
            if skill not in required_skills:
                match = self._find_skill_match(skill, candidate_skill_names)
                if match:
                    matched_desired.append(
                        {
                            "skill": skill,
                            "matched_with": match,
                        }
                    )

        # Calcula score
        if required_skills:
            required_score = len(matched_required) / len(required_skills)
            # Ajusta pelo nível de proficiência
            if matched_required:
                avg_level = sum(m["level_score"] for m in matched_required) / len(matched_required)
                required_score *= 0.5 + 0.5 * avg_level
        else:
            required_score = 0.5

        # Bônus por skills desejadas
        if desired_skills:
            desired_bonus = (len(matched_desired) / len(desired_skills)) * 0.2
        else:
            desired_bonus = 0

        final_score = min(1.0, required_score + desired_bonus)

        return {
            "score": final_score,
            "matched_required": matched_required,
            "missing_required": missing_required,
            "matched_desired": matched_desired,
            "required_coverage": (len(matched_required) / len(required_skills) * 100 if required_skills else 100),
        }

    def _find_skill_match(self, skill: str, candidate_skills: set) -> str | None:
        """Encontra match de skill usando similaridade."""
        skill_lower = skill.lower()

        # Match exato
        if skill_lower in candidate_skills:
            return skill_lower

        # Match parcial
        for cs in candidate_skills:
            # Verifica se uma contém a outra
            if skill_lower in cs or cs in skill_lower:
                return cs
            # Similaridade de strings
            ratio = SequenceMatcher(None, skill_lower, cs).ratio()
            if ratio >= 0.8:
                return cs

        return None

    async def _calculate_experience_match(
        self,
        candidate: Candidate,
        position: JobPosition,
    ) -> dict[str, Any]:
        """Calcula match de experiência."""
        required_years = getattr(position, "min_experience_years", None) or 0
        candidate_years = getattr(candidate, "years_experience", 0) or 0  # [Recrutamento] Candidate nao tem essa coluna -> AttributeError 500

        if required_years == 0:
            return {"score": 0.8, "required": 0, "candidate": candidate_years}

        if candidate_years >= required_years:
            # Score base de 100% se atende requisito mínimo
            score = 1.0
            # Bônus pequeno por experiência extra (até 10%)
            extra_years = candidate_years - required_years
            bonus = min(0.1, extra_years * 0.02)
            score = min(1.0, score + bonus)
        else:
            # Penalização proporcional
            ratio = candidate_years / required_years
            score = ratio * 0.8  # Máximo 80% se não atende

        return {
            "score": score,
            "required_years": required_years,
            "candidate_years": candidate_years,
            "meets_requirement": candidate_years >= required_years,
        }

    async def _calculate_education_match(
        self,
        candidate: Candidate,
        position: JobPosition,
    ) -> dict[str, Any]:
        """Calcula match de educação."""
        # Mapeia níveis de educação para scores
        education_levels = {
            "fundamental": 1,
            "medio": 2,
            "tecnico": 3,
            "tecnólogo": 4,
            "graduacao": 5,
            "pos_graduacao": 6,
            "mba": 7,
            "mestrado": 8,
            "doutorado": 9,
        }

        required_level = position.education_level
        if not required_level:
            return {"score": 0.7, "required": None, "candidate": None}

        required_value = education_levels.get(required_level.value, 5)

        # Verifica nível do candidato via tags ou headline
        candidate_value = 5  # Default: graduação

        headline_lower = (candidate.headline or "").lower()
        if "doutor" in headline_lower or "phd" in headline_lower:
            candidate_value = 9
        elif "mestr" in headline_lower:
            candidate_value = 8
        elif "mba" in headline_lower:
            candidate_value = 7
        elif "pós" in headline_lower or "especiali" in headline_lower:
            candidate_value = 6
        elif "graduad" in headline_lower or "bacharel" in headline_lower:
            candidate_value = 5
        elif "técnic" in headline_lower:
            candidate_value = 3

        if candidate_value >= required_value:
            score = 1.0
        else:
            score = candidate_value / required_value * 0.8

        return {
            "score": score,
            "required_level": required_level.value if required_level else None,
            "estimated_candidate_level": candidate_value,
            "meets_requirement": candidate_value >= required_value,
        }

    def _calculate_salary_match(  # pylint: disable=too-many-branches,too-many-return-statements
        self,
        candidate: Candidate,
        position: JobPosition,
    ) -> dict[str, Any]:
        """Calcula compatibilidade salarial."""
        candidate_expectation = candidate.salary_expectation
        position_min = position.salary_min
        position_max = position.salary_max

        if not candidate_expectation:
            return {"score": 0.7, "candidate": None, "range": None}

        if not position_min and not position_max:
            return {"score": 0.7, "candidate": candidate_expectation, "range": None}

        # Calcula compatibilidade
        if position_min and position_max:
            if position_min <= candidate_expectation <= position_max:
                # Dentro da faixa
                score = 1.0
            elif candidate_expectation < position_min:
                # Abaixo da faixa (candidato aceita menos)
                ratio = candidate_expectation / position_min
                score = 0.7 + (ratio * 0.3)  # 70-100%
            else:
                # Acima da faixa
                over = candidate_expectation - position_max
                tolerance = position_max * 0.2  # 20% de tolerância
                if over <= tolerance:
                    score = 1.0 - (over / tolerance * 0.3)
                else:
                    score = max(0.3, 0.7 - (over / position_max))
        elif position_max:
            if candidate_expectation <= position_max:
                score = 1.0
            else:
                over = candidate_expectation - position_max
                score = max(0.3, 1.0 - (over / position_max))
        else:  # position_min only
            if candidate_expectation >= position_min:
                score = 1.0
            else:
                score = candidate_expectation / position_min

        return {
            "score": score,
            "candidate_expectation": candidate_expectation,
            "position_min": position_min,
            "position_max": position_max,
            "compatible": score >= 0.7,
        }

    def _calculate_location_match(  # pylint: disable=too-many-return-statements
        self,
        candidate: Candidate,
        position: JobPosition,
    ) -> dict[str, Any]:
        """Calcula compatibilidade de localização."""
        # Trabalho remoto é sempre compatível
        if position.work_model and position.work_model.value == "remoto":
            return {"score": 1.0, "reason": "Vaga remota"}

        candidate_city = (candidate.city or "").lower()
        candidate_state = (candidate.state or "").upper()
        position_city = (position.city or "").lower()
        position_state = (position.state or "").upper()

        if not position_city and not position_state:
            return {"score": 0.8, "reason": "Localização não especificada"}

        # Mesmo cidade
        if candidate_city and position_city:
            if candidate_city == position_city:
                return {"score": 1.0, "reason": "Mesma cidade"}
            # Cidades similares (região metropolitana)
            if SequenceMatcher(None, candidate_city, position_city).ratio() > 0.8:
                return {"score": 0.9, "reason": "Cidades similares"}

        # Mesmo estado
        if candidate_state and position_state:
            if candidate_state == position_state:
                return {"score": 0.7, "reason": "Mesmo estado"}

        # Disponibilidade para mudança
        if candidate.available_for_relocation:
            return {"score": 0.6, "reason": "Disponível para mudança"}

        return {"score": 0.3, "reason": "Localização incompatível"}

    def _calculate_availability_match(  # pylint: disable=too-many-return-statements
        self,
        candidate: Candidate,
        position: JobPosition,
    ) -> dict[str, Any]:
        """Calcula compatibilidade de disponibilidade."""
        if position.is_urgent and not candidate.available_immediately:
            return {
                "score": 0.5,
                "urgent_position": True,
                "candidate_available": False,
            }

        if candidate.available_immediately:
            return {
                "score": 1.0,
                "urgent_position": position.is_urgent,
                "candidate_available": True,
            }

        # Verifica período de aviso
        notice_period = candidate.notice_period_days or 0
        if notice_period <= 15:
            score = 0.9
        elif notice_period <= 30:
            score = 0.8
        elif notice_period <= 60:
            score = 0.6
        else:
            score = 0.4

        return {
            "score": score,
            "notice_period_days": notice_period,
            "urgent_position": position.is_urgent,
        }

    def _get_recommendation(self, score: float) -> dict[str, Any]:
        """Gera recomendação baseada no score."""
        if score >= 0.85:
            return {
                "level": "excelente",
                "action": "Priorizar contato",
                "description": "Candidato altamente qualificado para a vaga",
            }
        elif score >= 0.70:
            return {
                "level": "bom",
                "action": "Considerar para entrevista",
                "description": "Candidato atende a maioria dos requisitos",
            }
        elif score >= 0.55:
            return {
                "level": "moderado",
                "action": "Avaliar criteriosamente",
                "description": "Candidato atende requisitos parcialmente",
            }
        elif score >= 0.40:
            return {
                "level": "baixo",
                "action": "Manter em banco de talentos",
                "description": "Candidato não atende requisitos principais",
            }
        else:
            return {
                "level": "incompatível",
                "action": "Não prosseguir",
                "description": "Perfil incompatível com a vaga",
            }

    async def rank_candidates(
        self,
        candidates: list[tuple[Candidate, list[CandidateSkill]]],
        position: JobPosition,
    ) -> list[dict[str, Any]]:
        """
        Rankeia lista de candidatos para uma vaga.

        Returns:
            Lista ordenada por score com detalhes
        """
        rankings = []

        for candidate, skills in candidates:
            result = await self.calculate_matching_score(candidate, position, skills)
            rankings.append(
                {
                    "candidate_id": str(candidate.id),
                    "candidate_name": candidate.name,
                    "final_score": result["final_score"],
                    "recommendation": result["recommendation"]["level"],
                    "scores": result["scores"],
                }
            )

        # Ordena por score decrescente
        rankings.sort(key=lambda x: x["final_score"], reverse=True)

        # Adiciona posição no ranking
        for i, item in enumerate(rankings, 1):
            item["rank"] = i

        return rankings

    async def parse_resume(  # pylint: disable=too-many-branches,too-many-locals
        self, resume_text: str
    ) -> dict[str, Any]:
        """
        Extrai informações do currículo.

        Returns:
            Dict com dados extraídos
        """
        if not resume_text:
            return {}

        text = resume_text.lower()
        result = {
            "skills": [],
            "experience_years": None,
            "education_level": None,
            "languages": [],
            "certifications": [],
            "contact": {},
        }

        # Extrai skills comuns
        common_skills = [
            "python",
            "javascript",
            "java",
            "react",
            "angular",
            "vue",
            "node",
            "sql",
            "postgresql",
            "mysql",
            "mongodb",
            "redis",
            "docker",
            "kubernetes",
            "aws",
            "azure",
            "gcp",
            "linux",
            "git",
            "agile",
            "scrum",
            "excel",
            "power bi",
            "tableau",
            "machine learning",
            "deep learning",
            "data science",
            "fastapi",
            "django",
            "flask",
            "spring",
            "typescript",
        ]

        for skill in common_skills:
            if skill in text:
                result["skills"].append(skill)

        # Extrai experiência
        exp_patterns = [
            r"(\d+)\s*anos?\s*de\s*experiência",
            r"(\d+)\s*years?\s*of\s*experience",
            r"experiência\s*de\s*(\d+)\s*anos?",
        ]
        for pattern in exp_patterns:
            match = re.search(pattern, text)
            if match:
                result["experience_years"] = int(match.group(1))
                break

        # Extrai educação
        if "doutorado" in text or "phd" in text:
            result["education_level"] = "doutorado"
        elif "mestrado" in text or "master" in text:
            result["education_level"] = "mestrado"
        elif "mba" in text:
            result["education_level"] = "mba"
        elif "pós-graduação" in text or "especialização" in text:
            result["education_level"] = "pos_graduacao"
        elif "graduação" in text or "bacharelado" in text or "licenciatura" in text:
            result["education_level"] = "graduacao"
        elif "técnico" in text or "tecnólogo" in text:
            result["education_level"] = "tecnico"

        # Extrai idiomas
        languages = {
            "inglês": ["inglês", "english", "fluente em inglês"],
            "espanhol": ["espanhol", "spanish", "español"],
            "francês": ["francês", "french", "français"],
            "alemão": ["alemão", "german", "deutsch"],
        }
        for lang, patterns in languages.items():
            for pattern in patterns:
                if pattern in text:
                    result["languages"].append(lang)
                    break

        # Extrai email
        email_pattern = r"[\w\.-]+@[\w\.-]+\.\w+"
        email_match = re.search(email_pattern, resume_text)
        if email_match:
            result["contact"]["email"] = email_match.group()

        # Extrai telefone
        phone_pattern = r"\(?\d{2}\)?\s*\d{4,5}[-\s]?\d{4}"
        phone_match = re.search(phone_pattern, resume_text)
        if phone_match:
            result["contact"]["phone"] = phone_match.group()

        return result

    async def suggest_positions(
        self,
        candidate: Candidate,
        positions: list[JobPosition],
        candidate_skills: list[CandidateSkill] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Sugere vagas compatíveis para um candidato.

        Returns:
            Lista de vagas sugeridas com scores
        """
        suggestions = []

        for position in positions:
            result = await self.calculate_matching_score(candidate, position, candidate_skills)

            if result["final_score"] >= 40:  # Mínimo 40% de compatibilidade
                suggestions.append(
                    {
                        "position_id": str(position.id),
                        "position_title": position.title,
                        "position_code": position.code,
                        "department": position.department.value,
                        "matching_score": result["final_score"],
                        "recommendation": result["recommendation"]["level"],
                        "key_matches": self._get_key_matches(result),
                        "gaps": self._get_gaps(result),
                    }
                )

        # Ordena por score
        suggestions.sort(key=lambda x: x["matching_score"], reverse=True)

        return suggestions[:limit]

    def _get_key_matches(self, result: dict) -> list[str]:
        """Extrai principais pontos de match."""
        matches = []
        details = result.get("details", {})

        if details.get("skills", {}).get("score", 0) >= 0.7:
            matches.append("Skills compatíveis")

        if details.get("experience", {}).get("meets_requirement"):
            matches.append("Experiência adequada")

        if details.get("education", {}).get("meets_requirement"):
            matches.append("Formação adequada")

        if details.get("salary", {}).get("compatible"):
            matches.append("Expectativa salarial compatível")

        if details.get("location", {}).get("score", 0) >= 0.8:
            matches.append("Localização compatível")

        return matches

    def _get_gaps(self, result: dict) -> list[str]:
        """Identifica gaps do candidato."""
        gaps = []
        details = result.get("details", {})

        skills_detail = details.get("skills", {})
        if skills_detail.get("missing_required"):
            missing = skills_detail["missing_required"][:3]
            gaps.append(f"Skills faltantes: {', '.join(missing)}")

        if not details.get("experience", {}).get("meets_requirement"):
            exp = details.get("experience", {})
            required = exp.get("required_years", 0)
            current = exp.get("candidate_years", 0)
            gaps.append(f"Experiência: {current}/{required} anos")

        if not details.get("salary", {}).get("compatible"):
            gaps.append("Expectativa salarial acima da faixa")

        if details.get("location", {}).get("score", 1) < 0.5:
            gaps.append("Localização distante")

        return gaps

    async def generate_interview_questions(  # pylint: disable=too-many-locals
        self,
        candidate: Candidate,  # pylint: disable=unused-argument
        position: JobPosition,
        matching_result: dict = None,
    ) -> list[dict[str, Any]]:
        """
        Gera sugestões de perguntas para entrevista.

        Returns:
            Lista de perguntas categorizadas
        """
        questions = []

        # Perguntas técnicas baseadas em skills requeridas
        required_skills = position.required_skills or []
        for skill in required_skills[:5]:
            questions.append(
                {
                    "category": "tecnica",
                    "skill": skill,
                    "question": f"Descreva sua experiência com {skill}. Pode dar um exemplo de projeto onde utilizou?",
                    "objective": f"Avaliar profundidade de conhecimento em {skill}",
                }
            )

        # Perguntas comportamentais
        behavioral_questions = [
            {
                "category": "comportamental",
                "question": "Conte sobre um desafio significativo que enfrentou em um projeto e como resolveu.",
                "objective": "Avaliar resolução de problemas e resiliência",
            },
            {
                "category": "comportamental",
                "question": "Como você lida com prazos apertados e múltiplas prioridades?",
                "objective": "Avaliar gestão de tempo e stress",
            },
            {
                "category": "comportamental",
                "question": "Descreva uma situação em que teve que trabalhar com alguém difícil. Como lidou?",
                "objective": "Avaliar habilidades interpessoais",
            },
        ]
        questions.extend(behavioral_questions)

        # Perguntas específicas baseadas em gaps
        if matching_result:
            gaps = matching_result.get("details", {})

            if not gaps.get("experience", {}).get("meets_requirement"):
                questions.append(
                    {
                        "category": "experiencia",
                        "question": "Sua experiência é menor que o requisito. Como pretende compensar isso?",
                        "objective": "Avaliar capacidade de aprendizado rápido",
                    }
                )

        # Perguntas sobre motivação
        questions.append(
            {
                "category": "motivacao",
                "question": f"O que te atraiu para a vaga de {position.title}?",
                "objective": "Avaliar alinhamento com a posição",
            }
        )

        questions.append(
            {
                "category": "motivacao",
                "question": "Onde você se vê profissionalmente em 3-5 anos?",
                "objective": "Avaliar planos de carreira e fit com a empresa",
            }
        )

        return questions
