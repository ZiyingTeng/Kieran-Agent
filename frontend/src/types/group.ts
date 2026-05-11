/**
 * Group related types - 匹配后端API
 */

export interface GroupMember {
  girlfriend_id: string;
  name: string;
}

export interface Group {
  group_id: string;
  group_name: string;
  members: string[];  // 成员女友ID列表
  owner_id: string;
  created_at: string;
  max_members?: number;
  is_active?: boolean;
  turn_strategy?: string;  // round_robin, random, reaction
  auto_response?: boolean;
  background?: string;
}

export interface CreateGroupRequest {
  name: string;           // 群组名称（后端用name，不是group_name）
  members: string[];      // 成员角色ID列表
  userId: string;         // 创建者用户ID（后端用userId，不是user_id）
  turn_strategy?: string; // 发言策略: round_robin, random, reaction
  auto_response?: boolean; // 是否自动让AI回应
  background?: string;    // 可选群聊场景背景
}

export interface GroupListResponse {
  userId?: string;
  groups: Group[];
}

export interface AddGroupMemberRequest {
  expertId: string;  // 角色ID（后端只传expertId）
}

export interface UpdateGroupNameRequest {
  name: string;  // 新的群组名称
}

export interface GroupChatRequest {
  message: string;
  userId: string;
  mentioned_girlfriends?: string[];  // 被@的角色ID列表
}

export interface GroupChatResponse {
  success: boolean;
  group_id: string;
  user_message?: {
    sender_id: string;
    sender_name: string;
    content: string;
    role: string;
    timestamp: string;
  };
  ai_responses: Array<{
    sender_id: string;
    sender_name: string;
    content: string;
    role: string;
    timestamp: string;
  }>;
  error?: string;
}

export interface GroupDetailResponse {
  group: Group;
  message_count: number;
}
