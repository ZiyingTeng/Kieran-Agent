/**
 * Model related types - 匹配后端API
 */

export interface Model {
  id: string;
  name: string;
  description: string;
  requires_api_key: boolean;
  api_key_env?: string;
  is_default?: boolean;  // 可选，只有当前模型才有
}

export interface ModelListResponse {
  success: boolean;
  models?: Model[];
  current_model?: string;
}

export interface ModelSettings {
  selectedModel: string;
  customApiPath: string;
  useAigirlApi: boolean;
}

export interface SendMessageRequest {
  userId: string;
  expertId: string;
  mes: string;
  source?: string;
  modelName?: string;
  apiPath?: string;
  imageUrl?: string;
  retry?: boolean;
  messageId?: string;
}
