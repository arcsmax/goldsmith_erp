import client from './client';

export interface OrderComment {
  id: number;
  order_id: number;
  user_id: number;
  user_name: string | null;
  text: string;
  created_at: string;
  updated_at: string;
}

export const commentsApi = {
  getForOrder: async (orderId: number): Promise<OrderComment[]> => {
    const { data } = await client.get(`/orders/${orderId}/comments`);
    return data;
  },
  create: async (orderId: number, text: string): Promise<OrderComment> => {
    const { data } = await client.post(`/orders/${orderId}/comments`, { text });
    return data;
  },
  update: async (orderId: number, commentId: number, text: string): Promise<OrderComment> => {
    const { data } = await client.put(`/orders/${orderId}/comments/${commentId}`, { text });
    return data;
  },
  delete: async (orderId: number, commentId: number): Promise<void> => {
    await client.delete(`/orders/${orderId}/comments/${commentId}`);
  }
};
