/**
 * General API response types
 */

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface ApiError {
  message: string;
  status?: number;
  code?: string;
}

export interface ChatMessageResponse {
  success: boolean;
  content?: string;
  session_id?: string;
  timestamp?: string;
  error?: string;
  emotion?: string;  // 情绪标签 (Happiness, Sadness, Anger, etc.)
  code?: number;     // 响应代码
}
