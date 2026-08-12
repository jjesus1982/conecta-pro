import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cn, debounce, sleep, isClient, copyToClipboard } from '../utils';

describe('cn (className merge)', () => {
  it('deve mesclar classes simples', () => {
    expect(cn('class1', 'class2')).toBe('class1 class2');
  });

  it('deve remover classes duplicadas do Tailwind', () => {
    expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4');
  });

  it('deve lidar com condicionais', () => {
    expect(cn('base', true && 'conditional')).toBe('base conditional');
    expect(cn('base', false && 'conditional')).toBe('base');
  });

  it('deve lidar com arrays de classes', () => {
    expect(cn(['class1', 'class2'])).toBe('class1 class2');
  });

  it('deve lidar com objetos', () => {
    expect(cn({ active: true, disabled: false })).toBe('active');
  });

  it('deve retornar string vazia quando não houver classes', () => {
    expect(cn()).toBe('');
  });

  it('deve mesclar classes do Tailwind corretamente', () => {
    expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500');
  });
});

describe('debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('deve atrasar a execução da função', () => {
    const fn = vi.fn();
    const debouncedFn = debounce(fn, 500);

    debouncedFn();
    expect(fn).not.toHaveBeenCalled();

    vi.advanceTimersByTime(500);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('deve cancelar chamadas anteriores', () => {
    const fn = vi.fn();
    const debouncedFn = debounce(fn, 500);

    debouncedFn();
    debouncedFn();
    debouncedFn();

    vi.advanceTimersByTime(500);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('deve passar argumentos corretamente', () => {
    const fn = vi.fn();
    const debouncedFn = debounce(fn, 500);

    debouncedFn('arg1', 'arg2');
    vi.advanceTimersByTime(500);

    expect(fn).toHaveBeenCalledWith('arg1', 'arg2');
  });

  it('deve funcionar com diferentes delays', () => {
    const fn = vi.fn();
    const debouncedFn = debounce(fn, 100);

    debouncedFn();
    vi.advanceTimersByTime(50);
    expect(fn).not.toHaveBeenCalled();

    vi.advanceTimersByTime(50);
    expect(fn).toHaveBeenCalled();
  });
});

describe('sleep', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('deve retornar uma Promise', () => {
    const result = sleep(100);
    expect(result).toBeInstanceOf(Promise);
  });

  it('deve resolver após o tempo especificado', async () => {
    const promise = sleep(500);
    vi.advanceTimersByTime(500);
    await expect(promise).resolves.toBeUndefined();
  });

  it('não deve resolver antes do tempo', async () => {
    let resolved = false;
    const promise = sleep(500).then(() => {
      resolved = true;
    });

    vi.advanceTimersByTime(400);
    // Aguardar o event loop processar
    await Promise.resolve();
    expect(resolved).toBe(false);

    vi.advanceTimersByTime(100);
    await promise;
    expect(resolved).toBe(true);
  });

  it('deve funcionar com zero ms', async () => {
    const promise = sleep(0);
    vi.advanceTimersByTime(0);
    await expect(promise).resolves.toBeUndefined();
  });
});

describe('isClient', () => {
  const originalWindow = global.window;

  afterEach(() => {
    // @ts-ignore
    global.window = originalWindow;
  });

  it('deve retornar true quando window está definido', () => {
    // @ts-ignore
    global.window = {};
    expect(isClient()).toBe(true);
  });

  it('deve retornar false quando window não está definido', () => {
    // @ts-ignore
    global.window = undefined;
    expect(isClient()).toBe(false);
  });
});

describe('copyToClipboard', () => {
  const originalClipboard = global.navigator.clipboard;

  beforeEach(() => {
    // @ts-ignore
    global.navigator.clipboard = {
      writeText: vi.fn(),
    };
  });

  afterEach(() => {
    // @ts-ignore
    global.navigator.clipboard = originalClipboard;
  });

  it('deve retornar true quando copia com sucesso', async () => {
    // @ts-ignore
    global.navigator.clipboard.writeText.mockResolvedValue(undefined);

    const result = await copyToClipboard('texto para copiar');
    expect(result).toBe(true);
    expect(global.navigator.clipboard.writeText).toHaveBeenCalledWith('texto para copiar');
  });

  it('deve retornar false quando ocorre erro', async () => {
    // @ts-ignore
    global.navigator.clipboard.writeText.mockRejectedValue(new Error('Erro'));

    const result = await copyToClipboard('texto para copiar');
    expect(result).toBe(false);
  });

  it('deve retornar false quando clipboard não está disponível', async () => {
    // @ts-ignore
    global.navigator.clipboard = undefined;

    const result = await copyToClipboard('texto');
    expect(result).toBe(false);
  });
});
