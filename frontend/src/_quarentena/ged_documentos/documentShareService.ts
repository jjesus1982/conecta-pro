import api from '@/lib/api';

export const documentShareService = {
  async getShares(documentId: string) {
    const response = await api.get(`/api/v1/ged/documents/${documentId}/shares`);
    return response.data;
  },

  async shareDocument(documentId: string, data: any) {
    const response = await api.post(`/api/v1/ged/documents/${documentId}/shares`, data);
    return response.data;
  },

  async updateShare(documentId: string, shareId: string, data: any) {
    const response = await api.put(`/api/v1/ged/documents/${documentId}/shares/${shareId}`, data);
    return response.data;
  },

  async revokeShare(documentId: string, shareId: string) {
    const response = await api.delete(`/api/v1/ged/documents/${documentId}/shares/${shareId}`);
    return response.data;
  },

  async getPublicLink(documentId: string) {
    const response = await api.post(`/api/v1/ged/documents/${documentId}/shares/public-link`);
    return response.data;
  },

  // Convenience methods used by components
  async create(data: { document_id: string; [key: string]: unknown }) {
    const { document_id, ...rest } = data;
    const response = await api.post(`/api/v1/ged/documents/${document_id}/shares`, rest);
    return response.data;
  },

  async createPublicLink(data: { [key: string]: unknown } & { document_id?: string }) {
    const documentId = data.document_id;
    if (!documentId) throw new Error('document_id is required');
    const { document_id: _, ...rest } = data;
    const response = await api.post(`/api/v1/ged/documents/${documentId}/shares/public-link`, rest);
    return response.data;
  },
};
