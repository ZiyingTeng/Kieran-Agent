/**
 * Chat API - 匹配后端API
 */

import { apiClient } from './client';
import { API_ENDPOINTS } from '@/utils/constants';
import type {
  ChatMessageResponse,
  SendMessageRequest,
} from '@/types';

/**
 * Send a private chat message
 * POST /api/mobile/chat
 */
export async function sendPrivateMessage(
  request: SendMessageRequest
): Promise<ChatMessageResponse> {
  return apiClient.post<ChatMessageResponse>(
    API_ENDPOINTS.SEND_MESSAGE,
    request
  );
}

/**
 * Send a group chat message with SSE streaming
 * POST /groups/{group_id}/chat/stream
 */
export async function sendGroupMessage(
  groupId: string,
  message: string,
  userId: string,
  mentionedGirlfriends: string[],
  onMessage: (event: unknown) => void,
  onComplete: () => void,
  onError: (error: string) => void
): Promise<void> {
  const requestData = {
    message,
    userId,
    mentioned_girlfriends: mentionedGirlfriends,
  };

  return apiClient.stream(
    `/groups/${groupId}/chat/stream`,
    requestData,
    onMessage,
    onComplete,
    onError
  );
}

/**
 * Update message history
 * POST /api/roles/update_history
 */
export async function updateHistory(
  userId: string,
  expertId: string,
  mes: string,
  reply: string
): Promise<{ success: boolean; msg?: string }> {
  return apiClient.post(API_ENDPOINTS.UPDATE_HISTORY, {
    userId,
    expertId,
    mes,
    reply,
  });
}

/**
 * Get chat history from backend
 * GET /history?user_id={userId}&expertId={expertId}
 */
export async function getHistory(
  userId: string,
  girlfriendId: string,
  limit: number = 50
): Promise<{ success: boolean; history?: Array<{ role: string; content: string; name?: string; timestamp?: string; emotion?: string }> }> {
  return apiClient.get(`/history?user_id=${userId}&expertId=${girlfriendId}&limit=${limit}`);
}

/**
 * Clear chat history
 * POST /clear?user_id={userId}&expertId={expertId}
 */
export async function clearHistory(
  userId: string,
  girlfriendId: string
): Promise<{ success: boolean; msg?: string }> {
  return apiClient.post(`/clear?user_id=${userId}&expertId=${girlfriendId}`);
}

/**
 * Delete chat history (alternative endpoint)
 * POST /api/roles/delete
 */
export async function deleteHistory(
  userId: string,
  expertId: string
): Promise<{ success: boolean; msg?: string }> {
  return apiClient.post(API_ENDPOINTS.DELETE_HISTORY, {
    userId,
    expertId,
  });
}

/**
 * Get session history
 * GET /sessions/{session_id}/history
 */
export async function getSessionHistory(
  sessionId: string
): Promise<{
  session_id: string;
  messages: Array<{ role: string; content: string; name?: string }>;
}> {
  return apiClient.get(API_ENDPOINTS.SESSION_HISTORY(sessionId));
}

/**
 * List all sessions (admin)
 * GET /admin/sessions
 */
export async function listAllSessions(): Promise<{
  users: Record<string, Record<string, Array<{ session_id: string }>>>;
}> {
  return apiClient.get(API_ENDPOINTS.ADMIN_SESSIONS);
}
