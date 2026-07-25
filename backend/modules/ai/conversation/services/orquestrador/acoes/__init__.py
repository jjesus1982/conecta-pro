"""Fase 5.4 — Ações propor→aprovar do orquestrador escopado.

A primitiva `base.propor` grava PENDENTE na tabela nativa do domínio, audita
append-only e entrega no sino ao aprovador por role. O LLM NUNCA executa.
"""
