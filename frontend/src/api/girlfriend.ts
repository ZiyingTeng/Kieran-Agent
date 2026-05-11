/**
 * Girlfriend/Roles API - 匹配后端API
 */

import { apiClient } from './client';
import { API_ENDPOINTS } from '@/utils/constants';
import type {
  Girlfriend,
  CreateGirlfriendRequest,
  UpdateGirlfriendRequest,
} from '@/types';

/**
 * Get all girlfriends (system and custom)
 * GET /girlfriends?user_id={userId}
 */
export async function getGirlfriends(
  userId: string
): Promise<Girlfriend[]> {
  return apiClient.get<Girlfriend[]>(API_ENDPOINTS.GIRLFRIENDS(userId));
}

/**
 * Get a single girlfriend by ID
 * GET /girlfriends/{expertId}
 */
export async function getGirlfriend(
  expertId: string
): Promise<Girlfriend> {
  return apiClient.get<Girlfriend>(API_ENDPOINTS.GIRLFRIEND_GET(expertId));
}

/**
 * Create a new custom girlfriend
 * POST /girlfriends
 */
export async function createGirlfriend(
  request: CreateGirlfriendRequest
): Promise<Girlfriend> {
  return apiClient.post<Girlfriend>(API_ENDPOINTS.GIRLFRIEND_CREATE, request);
}

/**
 * Update a girlfriend
 * PUT /girlfriends/{expertId}?user_id={userId}
 */
export async function updateGirlfriend(
  expertId: string,
  request: UpdateGirlfriendRequest,
  userId: string
): Promise<Girlfriend> {
  return apiClient.put<Girlfriend>(
    `${API_ENDPOINTS.GIRLFRIEND_UPDATE(expertId)}?user_id=${encodeURIComponent(userId)}`,
    request
  );
}

/**
 * Delete a girlfriend
 * DELETE /girlfriends/{expertId}?user_id={userId}
 */
export async function deleteGirlfriend(
  expertId: string,
  userId: string
): Promise<{ success: boolean }> {
  return apiClient.delete<{ success: boolean }>(
    `${API_ENDPOINTS.GIRLFRIEND_DELETE(expertId)}?user_id=${encodeURIComponent(userId)}`
  );
}

/**
 * Upload girlfriend role config (AIGirl compatible)
 * POST /api/roles/upload
 */
export async function uploadRole(
  formData: FormData
): Promise<{ success: boolean; msg?: string }> {
  const response = await fetch(`${window.location.origin}/api/roles/upload`, {
    method: 'POST',
    body: formData,
  });
  return await response.json();
}

/**
 * Delete girlfriend role (AIGirl compatible)
 * POST /api/roles/role_delete
 */
export async function deleteRole(
  userId: string,
  expertId: string
): Promise<{ success: boolean; msg?: string }> {
  return apiClient.post(API_ENDPOINTS.DELETE_ROLE, {
    userId,
    expertId,
  });
}
