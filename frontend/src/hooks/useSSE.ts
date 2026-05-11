/**
 * useSSE - Custom hook for SSE streaming
 */

import { useCallback, useRef } from 'react';
import type { SSEEvent } from '@/types';

interface UseSSEOptions {
  onMessage?: (event: SSEEvent) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

interface UseSSEReturn {
  startStream: (
    endpoint: string,
    data: unknown
  ) => Promise<void>;
  abortStream: () => void;
  isStreaming: boolean;
}

export function useSSE(options: UseSSEOptions = {}): UseSSEReturn {
  const abortControllerRef = useRef<AbortController | null>(null);
  const isStreamingRef = useRef(false);

  const startStream = useCallback(
    async (endpoint: string, data: unknown) => {
      // Abort any existing stream
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      // Create new abort controller
      abortControllerRef.current = new AbortController();
      isStreamingRef.current = true;

      try {
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(data),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        if (!reader) {
          throw new Error('Response body is null');
        }

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              try {
                const event = JSON.parse(data) as SSEEvent;

                // Check for completion event
                if ('success' in event && event.success) {
                  options.onComplete?.();
                }
                // Check for error event
                else if ('error' in event) {
                  options.onError?.(event.error);
                }
                // Regular message event
                else {
                  options.onMessage?.(event);
                }
              } catch (e) {
                console.error('Failed to parse SSE data:', e, data);
              }
            }
          }
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          console.log('Stream was aborted');
        } else {
          options.onError?.((error as Error).message);
        }
      } finally {
        isStreamingRef.current = false;
        abortControllerRef.current = null;
      }
    },
    [options]
  );

  const abortStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    isStreamingRef.current = false;
  }, []);

  return {
    startStream,
    abortStream,
    get isStreaming() {
      return isStreamingRef.current;
    },
  };
}
