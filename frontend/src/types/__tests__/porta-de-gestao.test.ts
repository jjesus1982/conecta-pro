import { describe, it, expect } from 'vitest';
import { temAcessoGestao, isSelfServiceUser, SELF_SERVICE_ROUTE } from '../modules';

/**
 * A porta que decide onde a pessoa ABRE o app.
 *
 * Origem: 17/09/2026. `/dashboard` é o `start_url` do manifest.json — é nele que o app
 * instalado no celular abre. O teste lá usava `isSelfServiceUser`, que só reconhece
 * role='funcionario'; os 26 'agente' e os 6 'lider' caíam no painel de GESTÃO, que não é
 * deles. A decisão do Jordan de 11/08/2026 já dizia o contrário e só não estava aplicada
 * neste ponto: PORTAL_ONLY_ROLES = funcionario, agente, lider.
 */

const u = (role: string, permissions: string[] = []) =>
  ({ id: '1', email: 'x@y.z', name: 'X', role, permissions, is_active: true }) as never;

describe('temAcessoGestao — quem vê o painel', () => {
  it('portal-only NÃO tem gestão, mesmo com permissão de módulo herdada', () => {
    // O líder de posto tem 'module:sst' herdado e ainda assim só vê o portal (11/08/2026).
    for (const role of ['funcionario', 'agente', 'lider']) {
      expect(temAcessoGestao(u(role))).toBe(false);
      expect(temAcessoGestao(u(role, ['module:sst']))).toBe(false);
    }
  });

  it('quem faz ronda MANTÉM o painel — são 3 supervisores, não os agentes', () => {
    expect(temAcessoGestao(u('supervisor', ['module:operacional']))).toBe(true);
    expect(temAcessoGestao(u('gerente_operacional', ['module:operacional']))).toBe(true);
  });

  it('admin entra', () => {
    expect(temAcessoGestao(u('admin'))).toBe(true);
    expect(temAcessoGestao(u('qualquer', ['all']))).toBe(true);
  });

  it('sem usuário, sem gestão', () => {
    expect(temAcessoGestao(null)).toBe(false);
    expect(temAcessoGestao(undefined)).toBe(false);
  });
});

describe('a diferença que causou o defeito', () => {
  it('isSelfServiceUser NÃO reconhece agente nem líder — por isso não serve de porta', () => {
    expect(isSelfServiceUser(u('agente'))).toBe(false);
    expect(isSelfServiceUser(u('lider'))).toBe(false);
    // ...mas os dois são portal-only. Usar a função antiga mandava ambos para o painel.
    expect(temAcessoGestao(u('agente'))).toBe(false);
    expect(temAcessoGestao(u('lider'))).toBe(false);
  });
});

describe('o destino existe', () => {
  it('SELF_SERVICE_ROUTE aponta para o Meu Espaço', () => {
    expect(SELF_SERVICE_ROUTE).toBe('/modulos/meu-espaco');
  });
});
