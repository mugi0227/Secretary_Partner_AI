import { api } from './client';
import type { ChatRequest, ChatResponse } from './types';

export interface StreamChunk {
  chunk_type: 'tool_start' | 'tool_end' | 'text' | 'done' | 'error';
  tool_name?: string;
  tool_args?: Record<string, any>;
  tool_result?: string;
  content?: string;
  assistant_message?: string;
  session_id?: string;
  capture_id?: string;
}

export const chatApi = {
  sendMessage: (request: ChatRequest) =>
    api.post<ChatResponse>('/chat', request),

  /**
   * Stream chat response using Server-Sent Events
   */
  async *streamMessage(request: ChatRequest): AsyncGenerator<StreamChunk, void, unknown> {
    const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
    const token = localStorage.getItem('token');

    const response = await fetch(`${baseURL}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error('Response body is not readable');
    }

    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');

        // Keep the last incomplete line in buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6); // Remove 'data: ' prefix
            if (data.trim()) {
              try {
                const chunk = JSON.parse(data) as StreamChunk;
                yield chunk;
              } catch (e) {
                console.error('Failed to parse SSE data:', data, e);
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  },
};
