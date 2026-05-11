/**
 * Girlfriend / Role related types
 */

// 后端返回的 GirlfriendInfo 格式
export interface Girlfriend {
  expertId: string;
  girlfriend_id: string;
  name: string;
  description: string;
  sys_prompt?: string;
  is_system: boolean;
  owner_id?: string;
}

export interface CreateGirlfriendRequest {
  name: string;
  sys_prompt: string;
  userId: string;
  model_name?: string;
}

export interface UpdateGirlfriendRequest {
  name?: string;
  sys_prompt?: string;
  model_name?: string;
}

// 后端返回的是数组，不是包装对象
export type GirlfriendListResponse = Girlfriend[];
