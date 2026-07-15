'use client';

import { useState } from 'react';
import { msgFromDetail } from '@/lib/string';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { FolderTree } from './FolderTree';
import { toast } from 'sonner';
import type { FolderResponse } from '@/types/generated/ged/schemas/folderResponse';
import { folderService } from '@/services/ged/folderService';

type Folder = FolderResponse;

interface MoveFolderDialogProps {
  folder: Folder | null;
  open: boolean;
  onClose: () => void;
  onMoved?: () => void;
}

export function MoveFolderDialog({ folder, open, onClose, onMoved }: MoveFolderDialogProps) {
  const [selectedFolder, setSelectedFolder] = useState<Folder | null>(null);
  const [loading, setLoading] = useState(false);

  const handleMove = async () => {
    if (!folder) return;

    setLoading(true);
    try {
      await folderService.move(folder.id, selectedFolder?.id);
      toast.success('Pasta movida com sucesso');
      onMoved?.();
      onClose();
    } catch (error: any) {
      toast.error('Erro ao mover pasta', {
        description: error.response?.msgFromDetail(data?.detail) || 'Erro desconhecido',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Mover Pasta</DialogTitle>
          <DialogDescription>
            Selecione o novo local para a pasta &quot;{folder?.name}&quot;
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Pasta atual */}
          <div className="p-3 bg-gray-50 rounded border">
            <p className="text-sm text-gray-600">Pasta atual:</p>
            <p className="font-medium">{folder?.full_path}</p>
          </div>

          {/* Seleção de destino */}
          <div>
            <p className="text-sm font-medium mb-2">Selecione o destino:</p>
            <div className="border rounded-lg p-2 max-h-96 overflow-y-auto">
              <FolderTree
                onFolderSelect={setSelectedFolder}
                selectedFolderId={selectedFolder?.id}
              />
            </div>
          </div>

          {/* Pasta selecionada */}
          {selectedFolder && (
            <div className="p-3 bg-blue-50 rounded border border-blue-200">
              <p className="text-sm text-blue-600">Novo local:</p>
              <p className="font-medium">{selectedFolder.full_path}</p>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={handleMove} disabled={loading || !selectedFolder}>
            {loading ? 'Movendo...' : 'Mover Pasta'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
