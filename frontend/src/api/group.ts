/**
 * Group API - 匹配后端API
 */

import { apiClient } from './client';
import type {
  Group,
  GroupListResponse,
  CreateGroupRequest,
  AddGroupMemberRequest,
  UpdateGroupNameRequest,
  GroupChatRequest,
  GroupDetailResponse,
} from '@/types';

/**
 * Get all groups for a user
 * GET /groups?user_id={userId}
 */
export async function getGroups(
  userId: string
): Promise<GroupListResponse> {
  return apiClient.get<GroupListResponse>(`/groups?user_id=${userId}`);
}

/**
 * Get group detail
 * GET /groups/{group_id}
 */
export async function getGroup(
  groupId: string
): Promise<GroupDetailResponse> {
  return apiClient.get<GroupDetailResponse>(`/groups/${groupId}`);
}

/**
 * Create a new group
 * POST /groups
 */
export async function createGroup(
  request: CreateGroupRequest
): Promise<{ success: boolean; group_id?: string; group?: Group; error?: string }> {
  return apiClient.post('/groups', request);
}

/**
 * Delete a group
 * DELETE /groups/{group_id}?user_id={userId}
 */
export async function deleteGroup(
  groupId: string,
  userId: string
): Promise<{ success: boolean }> {
  return apiClient.delete(`/groups/${groupId}?user_id=${userId}`);
}

/**
 * Update group name
 * PUT /groups/{group_id}/name
 */
export async function updateGroupName(
  groupId: string,
  request: UpdateGroupNameRequest
): Promise<{ success: boolean; group?: Group }> {
  return apiClient.put(`/groups/${groupId}/name`, request);
}

/**
 * Add a member to a group
 * POST /groups/{group_id}/members
 */
export async function addGroupMember(
  groupId: string,
  request: AddGroupMemberRequest
): Promise<{ success: boolean; group?: Group }> {
  return apiClient.post(`/groups/${groupId}/members`, request);
}

/**
 * Remove a member from a group
 * DELETE /groups/{group_id}/members/{member_id}
 */
export async function removeGroupMember(
  groupId: string,
  memberId: string
): Promise<{ success: boolean; group?: Group }> {
  return apiClient.delete(`/groups/${groupId}/members/${memberId}`);
}

/**
 * Send a message to a group chat
 * POST /groups/{group_id}/chat
 */
export async function sendGroupChat(
  groupId: string,
  request: GroupChatRequest,
  onMessage: (event: unknown) => void,
  onComplete: () => void,
  onError: (error: string) => void
): Promise<void> {
  return apiClient.stream(
    `/groups/${groupId}/chat`,
    request,
    onMessage,
    onComplete,
    onError
  );
}

/**
 * Get group chat history
 * GET /groups/{group_id}/history?limit={limit}
 */
export async function getGroupHistory(
  groupId: string,
  limit: number = 50
): Promise<{
  group_id: string;
  messages: Array<{
    sender_id: string;
    sender_name: string;
    content: string;
    role: string;
    timestamp: string;
    message_id: string;
  }>;
  total_count: number;
}> {
  return apiClient.get(`/groups/${groupId}/history?limit=${limit}`);
}
