import { useState, useCallback, useEffect, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { chatApi, type StreamChunk } from '../api/chat';
import type { ChatRequest, ChatResponse, ChatMode, ChatSession, ChatHistoryMessage } from '../api/types';

export interface ToolCall {
  id: string;
  name: string;
  args?: Record<string, any>;
  result?: string;
  status: 'running' | 'completed';
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
  isStreaming?: boolean;
}

const SESSION_STORAGE_KEY = 'chat_session_id';

export function useChat() {
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionIdState] = useState<string | undefined>(() => {
    return localStorage.getItem(SESSION_STORAGE_KEY) || undefined;
  });
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  const setSessionId = useCallback((id?: string) => {
    setSessionIdState(id);
    if (id) {
      localStorage.setItem(SESSION_STORAGE_KEY, id);
    } else {
      localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  }, []);

  const mutation = useMutation({
    mutationFn: (request: ChatRequest) => chatApi.sendMessage(request),
    onSuccess: (response: ChatResponse) => {
      // Add assistant message
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.assistant_message,
          timestamp: new Date(),
        },
      ]);

      // Update session ID
      if (response.session_id) {
        setSessionId(response.session_id);
      }
    },
  });

  const fetchSessions = useCallback(async () => {
    setIsLoadingSessions(true);
    try {
      const data = await chatApi.listSessions();
      setSessions(data);
    } finally {
      setIsLoadingSessions(false);
    }
  }, []);

  const loadHistory = useCallback(async (targetSessionId: string) => {
    setIsLoadingHistory(true);
    try {
      const history = await chatApi.getHistory(targetSessionId);
      const mapped = history
        .filter((item) => item.role !== 'system')
        .map((item: ChatHistoryMessage) => ({
          id: crypto.randomUUID(),
          role: item.role === 'assistant' ? 'assistant' : 'user',
          content: item.content,
          timestamp: item.created_at ? new Date(item.created_at) : new Date(),
        }));
      setMessages(mapped);
      setSessionId(targetSessionId);
    } finally {
      setIsLoadingHistory(false);
    }
  }, [setSessionId]);

  const initialSessionId = useRef(sessionId);

  useEffect(() => {
    if (initialSessionId.current) {
      loadHistory(initialSessionId.current);
    }
  }, [loadHistory]);

  const sendMessageStream = useCallback(
    async (text: string, imageBase64?: string, mode?: ChatMode) => {
      // Add user message
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Create assistant message placeholder
      const assistantMessageId = crypto.randomUUID();
      const assistantMessage: Message = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        toolCalls: [],
        isStreaming: true,
      };
      setMessages((prev) => [...prev, assistantMessage]);

      setIsStreaming(true);

      try {
        // Stream response
        for await (const chunk of chatApi.streamMessage({
          text,
          image_base64: imageBase64,
          mode,
          session_id: sessionId,
        })) {
          switch (chunk.chunk_type) {
            case 'tool_start':
              // Add new tool call
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        toolCalls: [
                          ...(msg.toolCalls || []),
                          {
                            id: crypto.randomUUID(),
                            name: chunk.tool_name || 'unknown',
                            args: chunk.tool_args,
                            status: 'running' as const,
                          },
                        ],
                      }
                    : msg
                )
              );
              break;

            case 'tool_end':
              // Update tool call with result
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        toolCalls: msg.toolCalls?.map((tc) =>
                          tc.name === chunk.tool_name && tc.status === 'running'
                            ? {
                                ...tc,
                                result: chunk.tool_result,
                                status: 'completed' as const,
                              }
                            : tc
                        ),
                      }
                    : msg
                )
              );
              break;

            case 'text':
              // Append text character by character
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        content: msg.content + (chunk.content || ''),
                      }
                    : msg
                )
              );
              break;

            case 'done':
              // Finalize message
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        isStreaming: false,
                      }
                    : msg
                )
              );

              if (chunk.session_id) {
                setSessionId(chunk.session_id);
              }

              // Invalidate queries to refresh data
              queryClient.invalidateQueries({ queryKey: ['tasks'] });
              queryClient.invalidateQueries({ queryKey: ['top3'] });
              queryClient.invalidateQueries({ queryKey: ['projects'] });
              break;

            case 'error':
              // Show error
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        content: chunk.content || 'エラーが発生しました',
                        isStreaming: false,
                      }
                    : msg
                )
              );
              break;
          }
        }
      } catch (error) {
        console.error('Streaming error:', error);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  content: 'エラーが発生しました',
                  isStreaming: false,
                }
              : msg
          )
        );
      } finally {
        setIsStreaming(false);
      }
    },
    [sessionId]
  );

  const sendMessage = useCallback(
    (text: string, mode?: ChatMode) => {
      // Add user message
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Send to API
      mutation.mutate({
        text,
        mode,
        session_id: sessionId,
      });
    },
    [mutation, sessionId]
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setSessionId(undefined);
  }, [setSessionId]);

  return {
    messages,
    sendMessage,
    sendMessageStream,
    clearChat,
    sessions,
    fetchSessions,
    loadHistory,
    sessionId,
    isLoadingSessions,
    isLoadingHistory,
    isLoading: mutation.isPending || isStreaming,
    error: mutation.error,
  };
}
