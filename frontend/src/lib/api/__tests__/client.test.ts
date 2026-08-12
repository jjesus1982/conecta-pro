import { describe, it, expect } from 'vitest';
import { apiClient } from '../client';

describe('lib/api/client re-export', () => {
  it('should re-export api as apiClient', () => {
    expect(apiClient).toBeDefined();
    expect(typeof apiClient.get).toBe('function');
    expect(typeof apiClient.post).toBe('function');
  });
});
