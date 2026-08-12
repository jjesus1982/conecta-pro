/**
 * Health Occupational - Service Layer Index
 * Módulo de Saúde Ocupacional (NR-4, NR-6, NR-7, NR-9)
 *
 * @module health-occupational
 * @author Conecta PRO Team
 * @date 2026-01-28
 */

// PCMSO - Exames Médicos e ASO (NR-7)
export * from './pcmso';
export { default as pcmsoService } from './pcmso';

// EPI - Equipamentos de Proteção (NR-6)
export * from './epi';
export { default as epiService } from './epi';

// PPRA/PGR - Riscos Ocupacionais (NR-9)
export * from './ppra';
export { default as ppraService } from './ppra';
