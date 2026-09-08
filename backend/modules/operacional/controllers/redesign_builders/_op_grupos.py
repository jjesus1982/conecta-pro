"""F0 — composição dos grupos do OPERACIONAL (fundação tabs, MESMO padrão do financeiro
_fin_grupos.py). Mapeia TODA tela/ação para (grupo, aba); telas None são omitidas (nunca
aba vazia). Prefixo _ = o discovery de builders pula este helper. Reduz a sidebar de
~62 itens soltos → 8 grupos."""
from modules.operacional.controllers.redesign_data_controller import grp, moved

GRUPOS = [
    ("g-visao", "Visão Geral", "Cobertura, KPIs, mapa, campo e IA", [
        ("visao", "Resumo"), ("kpi", "KPIs"), ("cobertura", "Cobertura"),
        ("cobertura-risco", "Cobertura em risco"), ("mapa", "Mapa"),
        ("campo", "Campo"), ("triagem", "Triagem"), ("relatorios", "Relatórios"),
        ("consultor", "Consultor IA"), ("agentes", "Agentes"), ("ai-command-center", "AI Command")]),
    ("g-escalas", "Escalas & Turnos", "Escalas, grade, alocações, turnos e substituições", [
        ("escalas-mes", "Escalas do mês"), ("grade-redesenhar", "Redesenhar grade"),
        ("escalas", "Escalas"), ("escalas-grade", "Grade por pessoa"), ("escalas-templates", "Templates"),
        ("escalas-visual", "Editor visual"), ("alocacoes", "Alocações"), ("turnos", "Turnos"),
        ("substituicoes", "Substituições"), ("escala-submeter", "Submeter escala"),
        ("escala-aprovar", "Aprovar escala"), ("escala-rejeitar", "Rejeitar escala"),
        ("escala-publicar", "Publicar escala"), ("substituicao-confirmar", "Confirmar substituição"),
        ("substituicao-rejeitar", "Rejeitar substituição"), ("substituicao-concluir", "Concluir substituição"),
        ("registrar-falta", "Registrar falta"),
        ("escalar-substituto", "Escalar substituto"), ("postos-sem-escala", "Postos sem escala"),
        ("escalas-rascunho", "Escalas em rascunho")]),
    ("g-postos", "Postos & Presença", "Postos, presença, instruções e passagem de turno", [
        ("gerente-hoje", "Onde está o gerente"), ("gerente-checkin", "Cheguei no posto"), ("gerente-checkout", "Saí do posto"),
        ("postos", "Postos"), ("presenca", "Presença hoje"), ("ausentes-hoje", "Ausentes hoje"),
        ("instrucoes-posto", "Instruções de posto"),
        ("passagem-turno", "Passagem de turno"), ("passagem-turno-nova", "Nova passagem"),
        ("instrucao-posto-editar", "Editar instrução"), ("checkin-manual", "Check-in manual"),
        ("posto-localizacao", "Localização do posto"), ("posto-editar", "Editar posto")]),
    ("g-equipe", "Equipe & Ponto", "Colaboradores, avaliação e banco de horas", [
        ("colaboradores", "Colaboradores"), ("avaliacao-equipe", "Avaliação de equipe"),
        ("avaliacao-criar", "Avaliar colaborador"),
        ("banco-horas", "Banco de horas"), ("banco-horas-apuracao", "Apuração (ponto × escala)"),
        ("banco-horas-lancar", "Lançar horas"),
        ("banco-horas-aprovar", "Aprovar horas"), ("banco-horas-rejeitar", "Rejeitar horas"),
        ("banco-horas-compensar", "Compensar horas"), ("banco-horas-editar", "Editar horas"),
        ("banco-horas-excluir", "Excluir horas")]),
    # Diaristas: só o que toca dado VIVO (diaria_* + financial_pagamentos_diaristas).
    # Saíram 8 itens que operavam o universo diarist_* — 3 linhas de teste em `diarists`
    # (UUID) contra 51 diaristas reais em diaria_diaristas (integer): espaços de id
    # diferentes, nenhuma dessas ações jamais alcançaria uma pessoa real.
    #   diarista-ativar/desativar/avaliar, diarista-escala-criar, diarista-fechamento,
    #   diarista-assignment-criar/cancelar, diaristas-escala
    # A pior era "Gerar fechamento": criava DiaristPayment em tabela que ninguém paga —
    # sensação de fechamento feito sobre dinheiro que não fecha. Os endpoints continuam
    # de pé (nada apagado); apenas não são mais oferecidos até decisão do Jordan.
    ("g-diaristas", "Diaristas", "Diárias, cadastro e fechamento", [
        ("diarias", "Lançar diárias"), ("diaristas", "Diaristas"),
        ("lancar-diaria", "Lançar diária"), ("cadastrar-diarista", "Cadastrar diarista"),
        ("diaria-excluir", "Excluir diária"), ("diaristas-fechamento", "Fechamento")]),
    ("g-disciplina", "Disciplina & RH", "Disciplinar, medidas e reembolsos", [
        ("disciplinar", "Disciplinar"), ("medidas-administrativas", "Medidas admin."),
        ("reembolsos", "Reembolsos"), ("medida-assinar", "Assinar medida"),
        ("medida-submeter", "Submeter medida"),
        ("medida-aprovar", "Aprovar medida"), ("medida-rejeitar", "Rejeitar medida"),
        ("medida-documento", "Documento da medida")]),
    ("g-rondas", "Rondas & Ocorrências", "Rondas, mobile e ocorrências", [
        ("rondas-resumo-inspetores", "Prestação de contas"),
        ("rondas", "Rondas"), ("ronda-checkpoints", "Checkpoints"), ("ronda-mobile", "Ronda mobile"),
        ("ocorrencias", "Ocorrências"),
        ("ocorrencia-rapida", "Ocorrência rápida"), ("resolver-ocorrencia", "Resolver ocorrência"),
        ("comentar-ocorrencia", "Comentar ocorrência"), ("nova-ronda", "Nova ronda"),
        ("ronda-transicao", "Andamento da ronda")]),
    # Saíram "notificacoes" e "notificacoes-marcar-todas": o menu do operacional oferecia
    # duas entradas que este builder não entrega. "notificacoes" é tela do _build_meu_espaco
    # (outro módulo) e "notificacoes-marcar-todas" não existe em builder nenhum. Clicar em
    # qualquer uma abria tela vazia — o mesmo "Aguardando dado" que já derrubou este módulo.
    ("g-comunicacao", "Comunicação", "Comunicados e alertas", [
        ("comunicados", "Comunicados"),
        ("comunicado-novo", "Novo comunicado"), ("comunicado-publicar", "Publicar comunicado"),
        ("comunicado-editar", "Editar comunicado"), ("comunicado-excluir", "Excluir comunicado"),
        ("alerta-criar", "Novo alerta"), ("alerta-ack", "Reconhecer alerta")]),
]


def montar_grupos(out: dict) -> None:
    """Compõe os grupos a partir das telas JÁ montadas em out e stub-a as antigas (redirect).
    Ordem importa: capturar as referências ANTES de stubar (igual ao _fin_grupos)."""
    novos = {}
    for gid, titulo, sub, tabs in GRUPOS:
        novos[gid] = grp(titulo, sub, [(tid, lbl, out.get(tid)) for tid, lbl in tabs])
    for gid, _t, _s, tabs in GRUPOS:
        for tid, _l in tabs:
            if tid in out:
                out[tid] = moved(gid, tid)
    out.update(novos)
