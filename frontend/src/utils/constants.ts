// API Constants
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || window.location.origin;

// Local Storage Keys
export const STORAGE_KEYS = {
  CHAT_STATE: (userId: string) => `chat_state_${userId}`,
  MODEL_SETTINGS: 'model_settings',
  USER_ID: 'current_user_id',
};

// Chat Types
export const ChatType = {
  PRIVATE: 'private',
  GROUP: 'group',
} as const;

export type ChatTypeValue = typeof ChatType[keyof typeof ChatType];

// Message Roles
export const MessageRole = {
  USER: 'user',
  ASSISTANT: 'assistant',
  SYSTEM: 'system',
} as const;

export type MessageRoleValue = typeof MessageRole[keyof typeof MessageRole];

// Connection Status
export const ConnectionStatus = {
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
} as const;

// API Endpoints
export const API_ENDPOINTS = {
  // Chat
  SEND_MESSAGE: '/api/mobile/chat',
  UPDATE_HISTORY: '/api/roles/update_history',
  GET_HISTORY: (userId: string, girlfriendId: string) =>
    `/history?user_id=${userId}&expertId=${girlfriendId}`,
  CLEAR_HISTORY: (userId: string, girlfriendId: string) =>
    `/clear?user_id=${userId}&expertId=${girlfriendId}`,
  DELETE_HISTORY: '/api/roles/delete',
  DELETE_ROLE: '/api/roles/role_delete',
  UPLOAD_ROLE: '/api/roles/upload',

  // Session
  SESSION_HISTORY: (sessionId: string) => `/sessions/${sessionId}/history`,
  ADMIN_SESSIONS: '/admin/sessions',

  // Girlfriend - 使用后端实际的端点
  GIRLFRIENDS: (userId: string) => `/girlfriends?user_id=${userId}`,
  GIRLFRIEND_GET: (girlfriendId: string) => `/girlfriends/${girlfriendId}`,
  GIRLFRIEND_CREATE: '/girlfriends',
  GIRLFRIEND_UPDATE: (girlfriendId: string) => `/girlfriends/${girlfriendId}`,
  GIRLFRIEND_DELETE: (girlfriendId: string) => `/girlfriends/${girlfriendId}`,

  // Models
  MODELS: '/api/models',
  MODELS_TEST: '/api/mobile/chat',
} as const;
