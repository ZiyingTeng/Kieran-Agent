/**
 * Models API
 */

import { apiClient } from './client';
import { API_ENDPOINTS } from '@/utils/constants';
import type {
  ModelListResponse,
  SendMessageRequest,
  ChatMessageResponse,
} from '@/types';

/**
 * Get available models
 */
export async function getModels(): Promise<ModelListResponse> {
  return apiClient.get<ModelListResponse>(API_ENDPOINTS.MODELS);
}

/**
 * Test API connection with a model
 */
export async function testApiConnection(
  request: SendMessageRequest
): Promise<ChatMessageResponse> {
  return apiClient.post<ChatMessageResponse>(
    API_ENDPOINTS.MODELS_TEST,
    request
  );
}
