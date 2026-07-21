"""Dossiê + score do candidato (Fase 6.2).

Roda as verificações por CPF que são REAIS/gratuitas hoje (CPF válido, histórico
interno na Conecta, consistência dos dados/documentos) e consolida num score com
indicadores para o RH. As fontes que dependem do robô (Receita/TST/Justiça Federal)
ou de provedor pago entram como 'pendente' — NUNCA fabricamos: fonte não conectada =
"aguardando integração", não um dado inventado.

Padrão do sistema: score 0-100 + nível + fatores (igual fraud_risk_profiles).
"""

import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_BASE = 50  # ponto de partida neutro


def _cpf_digits(cpf: str | None) -> str:
    return re.sub(r"\D", "", cpf or "")


def _valida_cpf(cpf: str) -> bool:
    d = _cpf_digits(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for i in (9, 10):
        s = sum(int(d[n]) * ((i + 1) - n) for n in range(i))
        dig = (s * 10) % 11 % 10
        if dig != int(d[i]):
            return False
    return True


def _check_cpf(cpf: str) -> dict[str, Any]:
    ok = _valida_cpf(cpf)
    return {"check_type": "cpf_valido", "provider": "validação local", "status": "ok" if ok else "alerta",
            "severidade": 15 if ok else -60, "resumo": "CPF válido" if ok else "CPF inválido (dígito verificador)"}


def _check_historico_interno(db: Session, cpf: str, employee_id: str) -> dict[str, Any]:
    d = _cpf_digits(cpf)
    rows = db.execute(
        text("SELECT status, motivo_desligamento, nome FROM employees "
             "WHERE regexp_replace(coalesce(cpf,''),'\\D','','g') = :c AND id::text <> :id "
             "  AND coalesce(is_homologacao,false)=false AND status <> 'candidato'"),
        {"c": d, "id": employee_id},
    ).mappings().all()
    if not rows:
        return {"check_type": "historico_interno", "provider": "base Conecta", "status": "ok",
                "severidade": 0, "resumo": "Sem histórico anterior na Conecta"}
    justa_causa = any("justa causa" in (r["motivo_desligamento"] or "").lower() for r in rows)
    if justa_causa:
        return {"check_type": "historico_interno", "provider": "base Conecta", "status": "alerta",
                "severidade": -40, "resumo": "Desligamento anterior por justa causa"}
    return {"check_type": "historico_interno", "provider": "base Conecta", "status": "ok",
            "severidade": 8, "resumo": f"Já teve vínculo com a Conecta ({rows[0]['status']})",
            "resultado": {"vinculos": len(rows)}}


def _check_consistencia(db: Session, cpf: str, employee_id: str, dados_ok: int) -> dict[str, Any]:
    d = _cpf_digits(cpf)
    docs = db.execute(
        text("SELECT tipo, extracted FROM candidate_documents WHERE employee_id::text = :id"),
        {"id": employee_id},
    ).mappings().all()
    n_docs = len(docs)
    cpf_bate = None
    for doc in docs:
        ex = doc["extracted"] or {}
        if isinstance(ex, dict) and ex.get("cpf"):
            cpf_bate = _cpf_digits(ex["cpf"]) == d
            break
    sev = 0
    partes = []
    if dados_ok >= 7:
        sev += 12; partes.append("dados eSocial completos")
    else:
        sev -= 3; partes.append(f"dados {dados_ok}/7")
    if n_docs > 0:
        sev += 6; partes.append(f"{n_docs} documento(s) anexado(s)")
    if cpf_bate is True:
        sev += 8; partes.append("CPF do documento confere")
    elif cpf_bate is False:
        sev -= 30; partes.append("CPF do documento NÃO confere")
    status = "alerta" if cpf_bate is False else "ok"
    return {"check_type": "consistencia_dados", "provider": "interno", "status": status,
            "severidade": sev, "resumo": "; ".join(partes),
            "resultado": {"documentos": n_docs, "cpf_confere": cpf_bate, "dados_ok": dados_ok}}


import os as _os

_ROBO_URL = _os.getenv("BGCHECK_ROBO_URL", "http://conecta-pro-det-robot:8099")

# Fontes que dependem do robô/pago — entram como PENDENTE (honesto, não fabrica).
# antecedentes/processos federais/mandados agora são checks REAIS via Infosimples
# (inertes → status 'pendente' automático enquanto não houver INFOSIMPLES_TOKEN).
_PENDENTES: list[tuple[str, str, str]] = []


# e-mail de sistema p/ certidões que o provedor exige campo de e-mail (CJF)
_EMAIL_SISTEMA = _os.getenv("INFOSIMPLES_EMAIL", "rh@conectamais.pro")


def _uf_de(naturalidade: Any) -> str | None:
    """Extrai a UF de um campo de naturalidade tipo 'Manaus/AM' ou 'Manaus - AM'."""
    m = re.search(r"[/\-\s]([A-Z]{2})\b\s*$", (naturalidade or "").strip().upper())
    return m.group(1) if m else None


def _data_br(d: Any) -> str | None:
    s = str(d or "")[:10]
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else None


def _check_infosimples(key: str, params: dict, check_type: str, provider: str,
                       label: str, sev_alerta: int = -30, sev_ok: int = 10,
                       requeridos: list[str] | None = None) -> dict[str, Any]:
    """Check genérico via Infosimples. Inerte (pendente) sem token; senão consulta + anexa PDF.
    `requeridos`: se algum campo obrigatório estiver vazio, NÃO chama a API (erro de param é COBRADO)."""
    import base64
    from modules.people_management.hr.services import infosimples_service as inf
    if not inf.habilitado():
        return {"check_type": check_type, "provider": provider, "status": "pendente",
                "severidade": 0, "resumo": f"{label} — aguardando INFOSIMPLES_TOKEN"}
    faltando = [k for k in (requeridos or []) if not params.get(k)]
    if faltando:  # não dispara (a Infosimples cobra até em erro de parâmetro)
        return {"check_type": check_type, "provider": provider, "status": "pendente", "severidade": 0,
                "resumo": f"{label} — aguardando dados: {', '.join(faltando)}"}
    res = inf.consultar(key, params)
    code = res.get("code")
    pdf = inf.primeiro_pdf(res)
    b64 = base64.b64encode(pdf).decode() if pdf else None
    base = {"check_type": check_type, "provider": provider, "_pdf_b64": b64, "_fonte_url": f"infosimples:{key}"}
    # código 612 = a fonte não retornou registro → para consultas de BUSCA, isso é "nada consta"
    if code == 612:
        return {**base, "status": "ok", "severidade": sev_ok, "resumo": f"{label}: nada consta"}
    if code != 200:
        return {"check_type": check_type, "provider": provider, "status": "pendente", "severidade": 0,
                "resumo": f"{label} — {res.get('code_message') or res.get('msg') or 'não concluída'}"}
    # SEGURANÇA: resposta 200 só vira "nada consta" quando é INEQUÍVOCO (evita falso positivo
    # que reprovaria candidato bom). Qualquer ambiguidade → anexa PDF e MANDA REVISAR (humano decide).
    # 1º) flag confiável do provedor (ex.: antecedentes PF conseguiu_emitir_certidao_negativa)
    if inf.certidao_negativa(res):
        return {**base, "status": "ok", "severidade": sev_ok, "resumo": f"{label}: nada consta"}
    consta = inf._tem_consta(res)
    if consta is False:
        return {**base, "status": "ok", "severidade": sev_ok, "resumo": f"{label}: nada consta"}
    return {**base, "status": "revisar", "severidade": 0,
            "resumo": f"{label}: possível registro — revisar certidão anexada"}


def _check_tst_robo(cpf: str) -> dict[str, Any]:
    """Chama o robô (CNDT/TST) pelos débitos trabalhistas do CPF (captcha de imagem)."""
    import httpx
    d = re.sub(r"\D", "", cpf or "")
    try:
        r = httpx.post(f"{_ROBO_URL}/consulta/tst", params={"cpf": d}, timeout=200)
        dd = r.json()
    except Exception as e:  # noqa: BLE001
        return {"check_type": "processos_trabalhistas", "provider": "TST (robô)", "status": "pendente",
                "severidade": 0, "resumo": f"Consulta indisponível ({str(e)[:40]})"}
    if not dd.get("ok"):
        return {"check_type": "processos_trabalhistas", "provider": "TST (robô)", "status": "pendente",
                "severidade": 0, "resumo": dd.get("msg", "Consulta não concluída")}
    base = {"check_type": "processos_trabalhistas", "provider": "TST (robô)",
            "_pdf_b64": dd.get("pdf_b64"), "_fonte_url": dd.get("fonte_url")}
    if dd.get("tem_debito"):
        return {**base, "status": "alerta", "severidade": -15,
                "resumo": "CNDT POSITIVA — consta débito trabalhista"}
    return {**base, "status": "ok", "severidade": 5,
            "resumo": "CNDT negativa — sem débito trabalhista"}


def _check_receita_robo(cpf: str, data_nasc: Any) -> dict[str, Any]:
    """Chama o robô (Receita, hCaptcha via 2Captcha) pela situação cadastral do CPF.
    Erro/timeout → pendente (não fabrica). CPF não encontrado = red flag."""
    import httpx
    dn = str(data_nasc)[:10] if data_nasc else ""
    try:
        r = httpx.post(f"{_ROBO_URL}/consulta/receita",
                       params={"cpf": cpf, "data_nascimento": dn}, timeout=130)
        d = r.json()
    except Exception as e:  # noqa: BLE001
        return {"check_type": "receita_situacao", "provider": "Receita Federal (robô)", "status": "pendente",
                "severidade": 0, "resumo": f"Consulta indisponível ({str(e)[:40]})"}
    if not d.get("ok"):
        return {"check_type": "receita_situacao", "provider": "Receita Federal (robô)", "status": "pendente",
                "severidade": 0, "resumo": d.get("msg", "Consulta não concluída")}
    if d.get("erro_form") or (not d.get("encontrado")):
        # Identidade NÃO confirmada na Receita (CPF↔nome↔nascimento). Não penaliza o score com -50
        # (o robô hCaptcha é instável), MAS fica PENDENTE e BLOQUEIA a aprovação até resolver —
        # o sistema não aceita CPF/nome/documento que não confere. (gate em _pendencias_identidade)
        return {"check_type": "receita_situacao", "provider": "Receita Federal (robô)", "status": "pendente",
                "severidade": 0, "resumo": "Identidade não confirmada na Receita — conferir CPF/data de nascimento",
                "resultado": {"encontrado": False}}
    situacao = (d.get("situacao") or "").upper()
    regular = situacao == "REGULAR"
    return {"check_type": "receita_situacao", "provider": "Receita Federal (robô)",
            "status": "ok" if regular else "alerta", "severidade": 15 if regular else -20,
            "resumo": f"Situação na Receita: {situacao or 'consultada'}" + (f" · {d['nome']}" if d.get("nome") else ""),
            "resultado": {"encontrado": True, "situacao": situacao, "nome": d.get("nome")}}


_TIPO_CERTIDAO = {
    "processos_trabalhistas": "certidao_cndt",
    "processos_civeis": "certidao_jf",
    "processos_criminais_federais": "certidao_jf",
    "antecedentes_criminais": "certidao_antecedentes",
    "mandados_prisao": "certidao_mandados",
    "improbidade": "certidao_improbidade",
    "trabalho_escravo": "certidao_trabalho_escravo",
    "ceis_inidoneos": "certidao_ceis",
    "receita_situacao": "comprovante_receita",
}

# título humano da certidão p/ o arquivo permanente do colaborador (DP)
_TITULO_CERTIDAO = {
    "certidao_cndt": "Certidão Negativa de Débitos Trabalhistas (TST)",
    "certidao_jf": "Certidão da Justiça Federal",
    "certidao_antecedentes": "Certidão de Antecedentes Criminais (PF)",
    "certidao_mandados": "Certidão de Mandados de Prisão (BNMP/CNJ)",
    "certidao_improbidade": "Certidão de Improbidade e Inelegibilidade (CNJ)",
    "certidao_trabalho_escravo": "Certidão — Lista Suja do Trabalho Escravo",
    "certidao_ceis": "Certidão de Inidôneos e Suspensos (CEIS)",
    "comprovante_receita": "Comprovante — Situação Receita Federal",
}
# condomínio "default" usado pelos documentos legados do DP (multi-tenant de fachada)
_CONDOMINIO_DEFAULT = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _salvar_certidao_pdf(db: Session, employee_id: str, check_type: str, b64: str, fonte_url: str | None) -> None:
    """Arquiva o PDF oficial da certidão em candidate_documents (clicável/download no RH)."""
    import base64
    import os
    import uuid as _uuid
    from pathlib import Path
    try:
        raw = base64.b64decode(b64)
        if raw[:4] != b"%PDF":
            return
        tipo = _TIPO_CERTIDAO.get(check_type, f"certidao_{check_type}")
        base = os.getenv("CANDIDATO_UPLOAD_DIR", "/app/uploads/candidatos_staging")
        pasta = Path(base) / "certidoes" / str(employee_id)
        pasta.mkdir(parents=True, exist_ok=True)
        fpath = pasta / f"{tipo}_{_uuid.uuid4().hex[:8]}.pdf"
        fpath.write_bytes(raw)
        titulo = _TITULO_CERTIDAO.get(tipo, tipo.replace("_", " ").title())
        # SAVEPOINT: falha ao salvar a certidão não aborta a persistência dos checks
        with db.begin_nested():
            # 1) dossiê do candidato (esteira do RH)
            db.execute(text("DELETE FROM candidate_documents WHERE employee_id=CAST(:e AS uuid) AND tipo=:t"),
                       {"e": employee_id, "t": tipo})
            db.execute(
                text("INSERT INTO candidate_documents (staging_token, employee_id, tipo, file_path, mime_type, "
                     " original_name, extract_status, extracted) VALUES (:s, CAST(:e AS uuid), :t, :p, "
                     " 'application/pdf', :o, 'robo', CAST(:x AS jsonb))"),
                {"s": f"robo_{employee_id}", "e": employee_id, "t": tipo, "p": str(fpath), "o": f"{titulo}.pdf",
                 "x": json.dumps({"fonte_url": fonte_url})},
            )
            # 2) ARQUIVO PERMANENTE do colaborador (DP) — aparece em dp/documentos p/ sempre
            db.execute(text("DELETE FROM hr_employee_documents WHERE employee_id=CAST(:e AS uuid) AND document_type=:t"),
                       {"e": employee_id, "t": tipo})
            db.execute(
                text("INSERT INTO hr_employee_documents (id, condominio_id, employee_id, document_type, category, "
                     " title, file_path, file_name, mime_type, status, is_published, reference_type, metadata, "
                     " created_at, updated_at) VALUES (gen_random_uuid(), CAST(:c AS uuid), CAST(:e AS uuid), :t, "
                     " 'kyc_admissional', :ti, :p, :fn, 'application/pdf', 'active', true, 'candidate_kyc', "
                     " CAST(:x AS jsonb), now(), now())"),
                {"c": _CONDOMINIO_DEFAULT, "e": employee_id, "t": tipo, "ti": titulo, "p": str(fpath),
                 "fn": f"{titulo}.pdf", "x": json.dumps({"fonte_url": fonte_url, "origem": "kyc_infosimples"})},
            )
    except Exception:
        pass


def _nivel_e_recomendacao(score: float) -> tuple[str, str]:
    if score >= 70:
        return "baixo", "aprovar"
    if score >= 45:
        return "medio", "avaliar"
    return "alto", "cautela"


def verificar(db: Session, employee_id: str, via_robo: bool = True) -> dict[str, Any]:
    """Roda as verificações reais, persiste o dossiê + score e retorna o resultado.
    via_robo=True consulta a Receita pelo robô (lento, captcha)."""
    emp = db.execute(
        text("SELECT cpf, nome, data_nascimento, nome_mae, nome_pai, naturalidade, "
             "(CASE WHEN nullif(trim(coalesce(telefone,'')),'') IS NOT NULL THEN 1 ELSE 0 END"
             " + CASE WHEN nullif(trim(coalesce(cep,'')),'') IS NOT NULL THEN 1 ELSE 0 END"
             " + CASE WHEN nullif(trim(coalesce(nome_mae,'')),'') IS NOT NULL THEN 1 ELSE 0 END"
             " + CASE WHEN nullif(trim(coalesce(rg,'')),'') IS NOT NULL THEN 1 ELSE 0 END"
             " + CASE WHEN nullif(trim(coalesce(pis,'')),'') IS NOT NULL THEN 1 ELSE 0 END"
             " + CASE WHEN nullif(trim(coalesce(naturalidade,'')),'') IS NOT NULL THEN 1 ELSE 0 END"
             " + CASE WHEN nullif(trim(coalesce(pix_key,'')),'') IS NOT NULL THEN 1 ELSE 0 END) AS dados_ok "
             "FROM employees WHERE id::text = :id"),
        {"id": employee_id},
    ).mappings().first()
    if not emp:
        raise ValueError("candidato não encontrado")
    cpf = emp["cpf"] or ""

    checks = [
        _check_cpf(cpf),
        _check_historico_interno(db, cpf, employee_id),
        _check_consistencia(db, cpf, employee_id, int(emp["dados_ok"] or 0)),
    ]
    if via_robo and _valida_cpf(cpf):
        checks.append(_check_receita_robo(cpf, emp["data_nascimento"]))
        checks.append(_check_tst_robo(cpf))  # CNDT/débitos trabalhistas (robô, captcha de imagem)
    # ── Infosimples (API por CPF, sem captcha) — INERTE sem INFOSIMPLES_TOKEN ──
    if _valida_cpf(cpf):
        cpf_d = re.sub(r"\D", "", cpf)
        # antecedentes PF exige birthdate em ISO (aaaa-mm-dd) — NÃO dd/mm/yyyy
        birthdate_iso = str(emp["data_nascimento"])[:10] if emp["data_nascimento"] else None
        pf_params = {"cpf": cpf_d, "nome": emp["nome"], "birthdate": birthdate_iso,
                     "nome_mae": emp["nome_mae"], "nome_pai": emp["nome_pai"],
                     "uf_nascimento": _uf_de(emp["naturalidade"])}
        # Antecedentes PF: só dispara com TODOS os campos (a PF exige — e erro de param é cobrado)
        checks.append(_check_infosimples("antecedentes_pf", pf_params, "antecedentes_criminais",
                                         "PF/SINIC (Infosimples)", "Antecedentes criminais PF", sev_alerta=-40,
                                         requeridos=["cpf", "nome", "birthdate", "nome_mae", "nome_pai", "uf_nascimento"]))
        # Mandados de prisão (BNMP): só CPF — VERIFICADO (nada consta = code 612)
        checks.append(_check_infosimples("mandados_prisao", {"cpf": cpf_d}, "mandados_prisao",
                                         "CNJ/BNMP (Infosimples)", "Mandados de prisão", sev_alerta=-60))
        # Idoneidade (CPF + nome) — params VERIFICADOS
        nome = emp["nome"]
        checks.append(_check_infosimples("improbidade", {"cpf": cpf_d, "nome": nome}, "improbidade",
                                         "CNJ (Infosimples)", "Improbidade/inelegibilidade",
                                         sev_alerta=-30, requeridos=["cpf", "nome"]))
        checks.append(_check_infosimples("trabalho_escravo", {"cpf": cpf_d, "nome": nome}, "trabalho_escravo",
                                         "MTE/SIT (Infosimples)", "Trabalho escravo (lista suja)",
                                         sev_alerta=-50, requeridos=["cpf", "nome"]))
        checks.append(_check_infosimples("ceis", {"cpf": cpf_d, "nome": nome}, "ceis_inidoneos",
                                         "Portal Transparência (Infosimples)", "Inidôneos/suspensos (CEIS)",
                                         sev_alerta=-20, requeridos=["cpf", "nome"]))
        # TODO: trf-unificada (params rejeitados) — habilitar após acertar cpf/email/tipo
    # arquiva os PDFs oficiais das certidões (clicável/download no RH)
    for c in checks:
        if c.get("_pdf_b64"):
            _salvar_certidao_pdf(db, employee_id, c["check_type"], c.pop("_pdf_b64"), c.pop("_fonte_url", None))
    # persiste os checks reais
    for c in checks:
        db.execute(
            text("INSERT INTO candidate_background_checks (employee_id, check_type, provider, status, "
                 " resultado, severidade, resumo, checked_at) "
                 "VALUES (CAST(:e AS uuid), :t, :p, :st, CAST(:r AS jsonb), :sev, :res, now()) "
                 "ON CONFLICT (employee_id, check_type) DO UPDATE SET status=EXCLUDED.status, "
                 " resultado=EXCLUDED.resultado, severidade=EXCLUDED.severidade, resumo=EXCLUDED.resumo, checked_at=now()"),
            {"e": employee_id, "t": c["check_type"], "p": c.get("provider"), "st": c["status"],
             "r": json.dumps(c.get("resultado")), "sev": c["severidade"], "res": c.get("resumo")},
        )
    # pendentes (não pontuam, só aparecem)
    for t, prov, resumo in _PENDENTES:
        db.execute(
            text("INSERT INTO candidate_background_checks (employee_id, check_type, provider, status, severidade, resumo) "
                 "VALUES (CAST(:e AS uuid), :t, :p, 'pendente', 0, :res) "
                 "ON CONFLICT (employee_id, check_type) DO UPDATE SET provider=EXCLUDED.provider, resumo=EXCLUDED.resumo"),
            {"e": employee_id, "t": t, "p": prov, "res": resumo},
        )

    score = max(0.0, min(100.0, float(_BASE + sum(c["severidade"] for c in checks))))
    nivel, recomendacao = _nivel_e_recomendacao(score)
    fatores = [{"check": c["check_type"], "impacto": c["severidade"], "status": c["status"], "resumo": c.get("resumo")}
               for c in checks]
    checks_ok = sum(1 for c in checks if c["status"] == "ok")

    prev = db.execute(text("SELECT total_score FROM candidate_scores WHERE employee_id::text=:id"),
                      {"id": employee_id}).scalar()
    db.execute(
        text("INSERT INTO candidate_scores (employee_id, total_score, previous_score, nivel, recomendacao, "
             " fatores, checks_ok, checks_total, calculated_at) "
             "VALUES (CAST(:e AS uuid), :s, :prev, :n, :rec, CAST(:f AS jsonb), :ok, :tot, now()) "
             "ON CONFLICT (employee_id) DO UPDATE SET total_score=EXCLUDED.total_score, "
             " previous_score=candidate_scores.total_score, nivel=EXCLUDED.nivel, recomendacao=EXCLUDED.recomendacao, "
             " fatores=EXCLUDED.fatores, checks_ok=EXCLUDED.checks_ok, checks_total=EXCLUDED.checks_total, calculated_at=now()"),
        {"e": employee_id, "s": score, "prev": prev, "n": nivel, "rec": recomendacao,
         "f": json.dumps(fatores), "ok": checks_ok, "tot": len(checks)},
    )
    db.commit()
    return {
        "score": round(score, 1), "nivel": nivel, "recomendacao": recomendacao,
        "checks_reais": checks_ok, "checks_total": len(checks),
        "fatores": fatores,
        "pendentes": [{"check_type": t, "provider": p, "resumo": r} for t, p, r in _PENDENTES],
    }
