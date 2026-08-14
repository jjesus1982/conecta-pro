import api from '@/lib/api';

export const approvalService = {
  async getApprovals(documentId: string) {
    const response = await api.get(`/api/v1/ged/documents/${documentId}/approvals`);
    return response.data;
  },

  async requestApproval(documentId: string, data: any) {
    const response = await api.post(`/api/v1/ged/documents/${documentId}/approvals`, data);
    return response.data;
  },

  async approve(documentId: string, approvalId: string, data?: any) {
    const response = await api.post(`/api/v1/ged/documents/${documentId}/approvals/${approvalId}/approve`, data);
    return response.data;
  },

  async reject(documentId: string, approvalId: string, data: any) {
    const response = await api.post(`/api/v1/ged/documents/${documentId}/approvals/${approvalId}/reject`, data);
    return response.data;
  },
};
