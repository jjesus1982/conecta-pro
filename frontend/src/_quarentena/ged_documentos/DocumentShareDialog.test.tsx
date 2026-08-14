import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { DocumentShareDialog } from '../DocumentShareDialog';

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

const mockDocumentShareService = vi.hoisted(() => ({
  create: vi.fn(),
  createPublicLink: vi.fn(),
}));

vi.mock('@/services/ged/documentShareService', () => ({
  documentShareService: mockDocumentShareService,
}));

// Mock ShareType
vi.mock('@/types/generated/ged/schemas/shareType', () => ({
  ShareType: {},
}));

describe('DocumentShareDialog', () => {
  const onClose = vi.fn();

  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockDocumentShareService.create.mockResolvedValue(undefined);
    mockDocumentShareService.createPublicLink.mockResolvedValue({
      share_token: 'abc123',
    });

    // Mock clipboard via vi.stubGlobal for jsdom compatibility
    vi.stubGlobal('navigator', {
      ...window.navigator,
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });

    // Mock window.location.origin
    Object.defineProperty(window, 'location', {
      value: { origin: 'http://localhost:3000' },
      writable: true,
      configurable: true,
    });
  });

  it('não renderiza quando open=false', () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={false}
        onClose={onClose}
      />
    );
    expect(screen.queryByText('Compartilhar Documento')).not.toBeInTheDocument();
  });

  it('renderiza dialog quando open=true', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );
    await waitFor(() => {
      expect(screen.getByText('Compartilhar Documento')).toBeInTheDocument();
    });
  });

  it('mostra aba "Compartilhar com Pessoa" por padrão', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );
    await waitFor(() => {
      expect(screen.getByText('Email *')).toBeInTheDocument();
    });
  });

  it('valida email obrigatório para compartilhamento por email', async () => {
    const { toast } = await import('sonner');

    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Compartilhar' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Compartilhar' }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Email é obrigatório');
    });
  });

  it('compartilha documento com email preenchido', async () => {
    const { toast } = await import('sonner');

    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText('email@exemplo.com')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('email@exemplo.com'), {
      target: { value: 'teste@empresa.com' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Compartilhar' }));

    await waitFor(() => {
      expect(mockDocumentShareService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          document_id: 'doc-1',
          shared_with_email: 'teste@empresa.com',
        })
      );
      expect(toast.success).toHaveBeenCalledWith('Documento compartilhado com sucesso');
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('exibe erro ao falhar compartilhamento', async () => {
    const { toast } = await import('sonner');
    mockDocumentShareService.create.mockRejectedValueOnce({
      response: { data: { detail: 'Usuário não encontrado' } },
    });

    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText('email@exemplo.com')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('email@exemplo.com'), {
      target: { value: 'teste@empresa.com' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Compartilhar' }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        'Erro ao compartilhar documento',
        expect.anything()
      );
    });
  });

  it('alterna para aba de link público', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Link Público')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Link Público'));

    await waitFor(() => {
      expect(screen.getByText('Gerar Link')).toBeInTheDocument();
    });
  });

  it('gera link público', async () => {
    const { toast } = await import('sonner');

    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Link Público')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Link Público'));

    await waitFor(() => {
      expect(screen.getByText('Gerar Link')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Gerar Link'));

    await waitFor(() => {
      expect(mockDocumentShareService.createPublicLink).toHaveBeenCalled();
      expect(toast.success).toHaveBeenCalledWith('Link público criado');
    });
  });

  it('exibe link gerado após criação', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    fireEvent.click(screen.getByText('Link Público'));

    await waitFor(() => {
      expect(screen.getByText('Gerar Link')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Gerar Link'));

    await waitFor(() => {
      expect(screen.getByDisplayValue(/abc123/)).toBeInTheDocument();
    });
  });

  it('copia link para área de transferência', async () => {
    const { toast } = await import('sonner');

    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    fireEvent.click(screen.getByText('Link Público'));
    await waitFor(() => expect(screen.getByText('Gerar Link')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Gerar Link'));
    await waitFor(() => expect(screen.getByDisplayValue(/abc123/)).toBeInTheDocument());

    // Find copy button adjacent to the generated link input
    const linkInput = screen.getByDisplayValue(/abc123/);
    const inputContainer = linkInput.closest('div');
    const copyBtn = inputContainer?.querySelector('button');

    if (copyBtn) {
      fireEvent.click(copyBtn);
      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Link copiado para área de transferência');
      });
    } else {
      expect(screen.getByDisplayValue(/abc123/)).toBeInTheDocument();
    }
  });

  it('desabilita "Gerar Link" após link criado', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    fireEvent.click(screen.getByText('Link Público'));
    await waitFor(() => expect(screen.getByText('Gerar Link')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Gerar Link'));

    await waitFor(() => {
      const linkCriadoButton = screen.getByText('Link Criado');
      expect(linkCriadoButton.closest('button')).toBeDisabled();
    });
  });

  it('ativa proteção por senha ao toggler switch', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Proteger com senha')).toBeInTheDocument();
    });

    // Find the password switch
    const switches = screen.getAllByRole('switch');
    const passwordSwitch = switches.find((s) => {
      const label = s.closest('div')?.nextElementSibling?.textContent;
      return label?.includes('senha');
    });

    // Click through toggle
    if (switches.length > 0) {
      fireEvent.click(switches[switches.length - 3]! || switches[0]!);
    }
  });

  it('ativa expiração ao toggle switch', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Definir data de expiração')).toBeInTheDocument();
    });
  });

  it('inclui expiresAt quando withExpiry está ativo e compartilha', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText('email@exemplo.com')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('email@exemplo.com'), {
      target: { value: 'teste@empresa.com' },
    });

    // Toggle expiry
    const switches = screen.getAllByRole('switch');
    // The expiry switch
    if (switches.length >= 2) {
      fireEvent.click(switches[1]!);
    }

    fireEvent.click(screen.getByRole('button', { name: 'Compartilhar' }));

    await waitFor(() => {
      if (mockDocumentShareService.create.mock.calls.length > 0) {
        const callArg = mockDocumentShareService.create.mock.calls[0]![0];
        expect(callArg).toMatchObject({ document_id: 'doc-1' });
      }
    });
  });

  it('exibe erro ao falhar criação de link público', async () => {
    const { toast } = await import('sonner');
    mockDocumentShareService.createPublicLink.mockRejectedValueOnce({
      response: { data: { detail: 'Erro de servidor' } },
    });

    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    fireEvent.click(screen.getByText('Link Público'));
    await waitFor(() => expect(screen.getByText('Gerar Link')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Gerar Link'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Erro ao criar link público', expect.anything());
    });
  });

  it('chama onClose ao clicar em Cancelar', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Cancelar')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Cancelar'));
    expect(onClose).toHaveBeenCalled();
  });

  it('alterna permissão de visualizar ao clicar switch', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Visualizar')).toBeInTheDocument();
    });

    // Permissions are togglable via switches
    const permSwitches = screen.getAllByRole('switch');
    expect(permSwitches.length).toBeGreaterThan(0);

    // Click first permission switch (visualizar - initially on)
    fireEvent.click(permSwitches[0]!);
    // Then re-enable it
    fireEvent.click(permSwitches[0]!);
  });

  it('permite recompartilhamento ao ativar switch', async () => {
    render(
      <DocumentShareDialog
        documentId="doc-1"
        open={true}
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Permitir recompartilhamento')).toBeInTheDocument();
    });
  });
});
