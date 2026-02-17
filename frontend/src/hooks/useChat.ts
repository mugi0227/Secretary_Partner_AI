import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { chatApi } from '../api/chat';
import { heartbeatApi } from '../api/heartbeat';
import type {
  ChatHistoryMessage,
  ChatMode,
  ChatRequest,
  ChatResponse,
  ChatSession,
  MemoryCreate,
  PendingQuestion,
  PhaseBreakdownProposal,
  ProjectCreate,
  TaskAssignmentProposal,
  TaskCreate,
  TokenUsage,
  ToolActionProposalPayload,
} from '../api/types';
import { useTimezone } from './useTimezone';
import { nowInTimezone, toDateTime } from '../utils/dateTime';
import { userStorage } from '../utils/userStorage';

export interface ToolCall {
  id: string;
  toolCallId?: string;
  name: string;
  args?: Record<string, unknown>;
  result?: string;
  error?: string;
  status: 'running' | 'completed' | 'failed';
}

export type TimelineEvent =
  | {
    id: string;
    kind: 'announcement';
    content: string;
    finalized?: boolean;
    toolName?: string;
  }
  | {
    id: string;
    kind: 'tool';
    name: string;
    status: 'running' | 'completed' | 'failed';
  };

export interface ProposalInfo {
  id: string;
  proposalId: string;
  proposalType:
    | 'create_task'
    | 'create_project'
    | 'create_work_memory'
    | 'assign_task'
    | 'phase_breakdown'
    | 'tool_action';
  description: string;
  payload: TaskCreate | ProjectCreate | MemoryCreate | TaskAssignmentProposal | PhaseBreakdownProposal | ToolActionProposalPayload;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
  proposals?: ProposalInfo[];
  questions?: PendingQuestion[];
  questionsContext?: string;
  isStreaming?: boolean;
  imageUrl?: string;
  suppressText?: boolean;
  toolPlacement?: 'before' | 'after';
  timeline?: TimelineEvent[];
  usage?: TokenUsage;
}

const SESSION_STORAGE_KEY = 'chat_session_id';
const HEARTBEAT_SESSION_PREFIX = 'heartbeat-';
const LEGACY_HEARTBEAT_SESSION_ID = 'heartbeat';

const isHeartbeatSession = (sessionId: string) =>
  sessionId === LEGACY_HEARTBEAT_SESSION_ID
  || sessionId.startsWith(HEARTBEAT_SESSION_PREFIX);

const APPROVAL_TOOL_NAMES = new Set([
  'create_task',
  'update_task',
  'delete_task',
  'assign_task',
  'create_project',
  'update_project',
  'invite_project_member',
  'create_project_summary',
  'create_work_memory',
  'create_meeting',
  'add_to_memory',
  'refresh_user_profile',
  'schedule_agent_task',
  'apply_schedule_request',
  'add_agenda_item',
  'update_agenda_item',
  'delete_agenda_item',
  'reorder_agenda_items',
  'create_phase',
  'update_phase',
  'delete_phase',
  'create_milestone',
  'update_milestone',
  'delete_milestone',
]);

const readString = (value: unknown): string | undefined => {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
};

const readFirstString = (
  args: Record<string, unknown> | undefined,
  keys: string[],
): string | undefined => {
  if (!args) {
    return undefined;
  }
  for (const key of keys) {
    const candidate = readString(args[key]);
    if (candidate) {
      return candidate;
    }
  }
  return undefined;
};

const getToolAnnouncement = (
  _toolName: string,
  args?: Record<string, unknown>,
): { content: string; finalized: boolean } | null => {
  const proposalDescription = readFirstString(args, ['proposal_description']);
  if (!proposalDescription) {
    return null;
  }
  return { content: proposalDescription, finalized: true };
};



export function useChat() {
  const queryClient = useQueryClient();
  const timezone = useTimezone();
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionIdState] = useState<string | undefined>(() => {
    return userStorage.get(SESSION_STORAGE_KEY) || undefined;
  });
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const hasLoadedInitialHistory = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const setSessionId = useCallback((id?: string) => {
    setSessionIdState(id);
    if (id) {
      userStorage.set(SESSION_STORAGE_KEY, id);
    } else {
      userStorage.remove(SESSION_STORAGE_KEY);
    }
  }, []);

  const [selectedModel, setSelectedModelState] = useState<string | undefined>(() => {
    return userStorage.get('selectedModel') || undefined;
  });

  const setSelectedModel = useCallback((model?: string) => {
    setSelectedModelState(model);
    if (model) {
      userStorage.set('selectedModel', model);
    } else {
      userStorage.remove('selectedModel');
    }
  }, []);

  const mutation = useMutation({
    mutationFn: (request: ChatRequest) => chatApi.sendMessage(request),
    onSuccess: (response: ChatResponse) => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.assistant_message,
          timestamp: nowInTimezone(timezone).toJSDate(),
        },
      ]);

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
        .map((item: ChatHistoryMessage): Message => ({
          id: crypto.randomUUID(),
          role: item.role === 'assistant' ? 'assistant' : 'user',
          content: item.content,
          timestamp: item.created_at
            ? toDateTime(item.created_at, timezone).toJSDate()
            : nowInTimezone(timezone).toJSDate(),
        }));
      setMessages(mapped);
      setSessionId(targetSessionId);
      if (isHeartbeatSession(targetSessionId)) {
        try {
          await heartbeatApi.markRead();
          queryClient.invalidateQueries({ queryKey: ['heartbeat', 'unread-count'] });
        } catch (error) {
          console.error('Failed to mark heartbeat messages as read', error);
        }
      }
    } finally {
      setIsLoadingHistory(false);
    }
  }, [queryClient, setSessionId, timezone]);

  const initialSessionId = useRef(sessionId);

  useEffect(() => {
    if (hasLoadedInitialHistory.current) {
      return;
    }

    const bootstrapHistory = async () => {
      if (initialSessionId.current) {
        await loadHistory(initialSessionId.current);
        hasLoadedInitialHistory.current = true;
        return;
      }

      try {
        const data = await chatApi.listSessions();
        setSessions(data);
        if (data.length > 0) {
          await loadHistory(data[0].session_id);
        }
      } finally {
        hasLoadedInitialHistory.current = true;
      }
    };

    bootstrapHistory();
  }, [loadHistory]);

  useEffect(() => {
    const handleAuthChange = () => {
      setMessages([]);
      setSessions([]);
      hasLoadedInitialHistory.current = false;
      const storedSession = userStorage.get(SESSION_STORAGE_KEY) || undefined;
      setSessionIdState(storedSession);
    };
    window.addEventListener('auth-changed', handleAuthChange);
    return () => {
      window.removeEventListener('auth-changed', handleAuthChange);
    };
  }, []);

  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.isStreaming
            ? { ...msg, isStreaming: false, content: msg.content || '[Stream cancelled]' }
            : msg
        )
      );
    }
  }, []);

  const sendMessageStream = useCallback(
    async (
      text: string,
      imageBase64?: string,
      mode?: ChatMode,
      projectContext?: { projectId: string; projectName: string } | null,
      audioBase64?: string,
      audioMimeType?: string,
    ) => {
      // Cancel any ongoing stream
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text || (audioBase64 ? '[Voice input]' : ''),
        timestamp: nowInTimezone(timezone).toJSDate(),
        imageUrl: imageBase64,
      };
      setMessages((prev) => [...prev, userMessage]);

      const assistantMessageId = crypto.randomUUID();
      const assistantMessage: Message = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: nowInTimezone(timezone).toJSDate(),
        toolCalls: [],
        proposals: [],
        timeline: [],
        isStreaming: true,
      };
      setMessages((prev) => [...prev, assistantMessage]);

      setIsStreaming(true);

      try {
        const approvalMode = (userStorage.get('aiApprovalMode') as 'manual' | 'auto') || 'auto';
        const manualApproval = approvalMode === 'manual';

        const context: Record<string, unknown> | undefined =
          projectContext
            ? { project_id: projectContext.projectId, project_name: projectContext.projectName }
            : undefined;

        for await (const chunk of chatApi.streamMessage({
          text,
          audio_base64: audioBase64,
          audio_mime_type: audioMimeType,
          image_base64: imageBase64,
          mode,
          session_id: sessionId,
          approval_mode: approvalMode,
          proposal_mode: approvalMode === 'manual',
          context,
          model: selectedModel || undefined,
        }, abortControllerRef.current.signal)) {
          switch (chunk.chunk_type) {
            case 'tool_start': {
              const toolName = chunk.tool_name || 'unknown';
              const toolArgs = chunk.tool_args;
              const toolId = crypto.randomUUID();
              const toolCallId = chunk.tool_call_id as string | undefined;
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? (() => {
                      const nextToolCalls = [
                        ...(msg.toolCalls || []),
                        {
                          id: toolId,
                          toolCallId,
                          name: toolName,
                          args: toolArgs,
                          status: 'running' as const,
                        },
                      ];

                      if (!manualApproval) {
                        return {
                          ...msg,
                          toolCalls: nextToolCalls,
                        };
                      }

                      const nextTimeline = [...(msg.timeline || [])];
                      let suppressText = msg.suppressText;
                      let nextIsStreaming = msg.isStreaming;
                      if (toolName && APPROVAL_TOOL_NAMES.has(toolName)) {
                        const announcement = getToolAnnouncement(toolName, toolArgs);
                        if (announcement) {
                          nextTimeline.push({
                            id: crypto.randomUUID(),
                            kind: 'announcement',
                            content: announcement.content,
                            finalized: announcement.finalized,
                            toolName,
                          });
                          suppressText = true;
                          nextIsStreaming = false;
                        }
                      }
                      nextTimeline.push({
                        id: toolId,
                        kind: 'tool',
                        name: toolName,
                        status: 'running',
                      });

                      return {
                        ...msg,
                        toolCalls: nextToolCalls,
                        timeline: nextTimeline,
                        suppressText,
                        isStreaming: nextIsStreaming,
                        toolPlacement: 'after' as const,
                      };
                    })()
                    : msg
                )
              );
              break;
            }

            case 'tool_end': {
              const toolName = chunk.tool_name || 'unknown';
              const endToolCallId = chunk.tool_call_id as string | undefined;
              setMessages((prev) =>
                prev.map((msg) => {
                  if (msg.id !== assistantMessageId) {
                    return msg;
                  }
                  // Update only the matching tool call, not all with the same name
                  let tcUpdated = false;
                  const nextToolCalls = msg.toolCalls?.map((tc) => {
                    if (tcUpdated) return tc;
                    const matches = endToolCallId
                      ? tc.toolCallId === endToolCallId
                      : tc.name === toolName && tc.status === 'running';
                    if (matches) {
                      tcUpdated = true;
                      return {
                        ...tc,
                        result: chunk.tool_result,
                        status: 'completed' as const,
                      };
                    }
                    return tc;
                  });
                  if (!manualApproval || !msg.timeline || msg.timeline.length === 0) {
                    return {
                      ...msg,
                      toolCalls: nextToolCalls,
                    };
                  }
                  let tlUpdated = false;
                  const nextTimeline = msg.timeline.map((item) => {
                    if (!tlUpdated && item.kind === 'tool' && item.name === toolName && item.status === 'running') {
                      tlUpdated = true;
                      return {
                        ...item,
                        status: 'completed' as const,
                      };
                    }
                    return item;
                  });
                  return {
                    ...msg,
                    toolCalls: nextToolCalls,
                    timeline: nextTimeline,
                  };
                })
              );
              break;
            }

            case 'tool_error': {
              const toolName = chunk.tool_name || 'unknown';
              const errToolCallId = chunk.tool_call_id as string | undefined;
              setMessages((prev) =>
                prev.map((msg) => {
                  if (msg.id !== assistantMessageId) {
                    return msg;
                  }
                  let tcUpdated = false;
                  const nextToolCalls = msg.toolCalls?.map((tc) => {
                    if (tcUpdated) return tc;
                    const matches = errToolCallId
                      ? tc.toolCallId === errToolCallId
                      : tc.name === toolName && tc.status === 'running';
                    if (matches) {
                      tcUpdated = true;
                      return {
                        ...tc,
                        error: chunk.error_message,
                        status: 'failed' as const,
                      };
                    }
                    return tc;
                  });
                  if (!manualApproval || !msg.timeline || msg.timeline.length === 0) {
                    return {
                      ...msg,
                      toolCalls: nextToolCalls,
                    };
                  }
                  let tlUpdated = false;
                  const nextTimeline = msg.timeline.map((item) => {
                    if (!tlUpdated && item.kind === 'tool' && item.name === toolName && item.status === 'running') {
                      tlUpdated = true;
                      return {
                        ...item,
                        status: 'failed' as const,
                      };
                    }
                    return item;
                  });
                  return {
                    ...msg,
                    toolCalls: nextToolCalls,
                    timeline: nextTimeline,
                  };
                })
              );
              break;
            }

            case 'text':
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? (msg.suppressText
                      ? msg
                      : {
                        ...msg,
                        content: msg.content + (chunk.content || ''),
                      })
                    : msg
                )
              );
              break;

            case 'done':
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                      ...msg,
                      isStreaming: false,
                      usage: chunk.usage,
                    }
                    : msg
                )
              );

              if (chunk.session_id) {
                setSessionId(chunk.session_id);
              }

              for (const key of [
                ['tasks'], ['subtasks'], ['top3'], ['today-tasks'], ['schedule'],
                ['task-detail'], ['task-assignments'],
                ['projects'], ['project'],
                ['project-children'], ['project-link-requests'],
                ['incoming-link-requests'], ['project-achievements'],
                ['meetings'],
                ['meeting-agendas'], ['agenda-items'], ['task-agendas'],
                ['meeting-session'], ['meeting-sessions'],
                ['phases'],
                ['recurring-tasks'],
                ['achievements'],
              ]) {
                queryClient.invalidateQueries({ queryKey: key });
              }
              break;

            case 'proposal':
              if (chunk.proposal_id && chunk.proposal_type && chunk.payload) {
                const rawProposalType = String(chunk.proposal_type ?? '');
                const normalizedProposalType =
                  rawProposalType === 'create_skill'
                    ? 'create_work_memory'
                    : rawProposalType;
                const proposalInfo: ProposalInfo = {
                  id: crypto.randomUUID(),
                  proposalId: chunk.proposal_id,
                  proposalType: normalizedProposalType as
                    | 'create_task'
                    | 'create_project'
                    | 'create_work_memory'
                    | 'assign_task'
                    | 'phase_breakdown'
                    | 'tool_action',
                  description: chunk.description || '',
                  payload: chunk.payload as unknown as TaskCreate | ProjectCreate | MemoryCreate | TaskAssignmentProposal | PhaseBreakdownProposal | ToolActionProposalPayload,
                };
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? (() => {
                        const proposals = [
                          ...(msg.proposals || []),
                          proposalInfo,
                        ];
                        if (!manualApproval) {
                          return {
                            ...msg,
                            proposals,
                          };
                        }
                        return {
                          ...msg,
                          proposals,
                          isStreaming: false,
                          suppressText: true,
                          toolPlacement: 'after' as const,
                          timeline: msg.timeline,
                        };
                      })()
                      : msg
                  )
                );
              }
              break;

            case 'questions':
              if (chunk.questions && chunk.questions.length > 0) {
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId
                      ? {
                        ...msg,
                        questions: chunk.questions,
                        questionsContext: chunk.context,
                      }
                      : msg
                  )
                );
              }
              break;

            case 'error':
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                      ...msg,
                      content: chunk.content || '繧ｨ繝ｩ繝ｼ縺檎匱逕溘＠縺ｾ縺励◆',
                      isStreaming: false,
                    }
                    : msg
                )
              );
              break;
          }
        }
      } catch (error) {
        // Ignore abort errors (user cancelled)
        if (error instanceof Error && error.name === 'AbortError') {
          return;
        }
        console.error('Streaming error:', error);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                ...msg,
                content: '繧ｨ繝ｩ繝ｼ縺檎匱逕溘＠縺ｾ縺励◆',
                isStreaming: false,
              }
              : msg
          )
        );
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
      }
    },
    [queryClient, sessionId, setSessionId, timezone]
  );

  const sendMessage = useCallback(
    (text: string, mode?: ChatMode, imageUrl?: string) => {
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        timestamp: nowInTimezone(timezone).toJSDate(),
        imageUrl,
      };
      setMessages((prev) => [...prev, userMessage]);

      const approvalMode = (userStorage.get('aiApprovalMode') as 'manual' | 'auto') || 'auto';
      mutation.mutate({
        text,
        mode,
        session_id: sessionId,
        image_url: imageUrl,
        approval_mode: approvalMode,
        proposal_mode: approvalMode === 'manual',
      });
    },
    [mutation, sessionId, timezone]
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setSessionId(undefined);
  }, [setSessionId]);

  /** Patch a toolCall result after proposal approval (inject task_id etc.) */
  const updateProposalResult = useCallback(
    (proposalId: string, approvalResult: { task_id?: string; project_id?: string }) => {
      setMessages((prev) =>
        prev.map((msg) => {
          if (!msg.toolCalls) return msg;
          let changed = false;
          const updatedToolCalls = msg.toolCalls.map((tc) => {
            if (!tc.result) return tc;
            try {
              const parsed = JSON.parse(tc.result);
              if (parsed.proposal_id === proposalId) {
                changed = true;
                return {
                  ...tc,
                  result: JSON.stringify({
                    ...parsed,
                    ...approvalResult,
                    status: 'approved',
                  }),
                };
              }
            } catch { /* ignore */ }
            return tc;
          });
          return changed ? { ...msg, toolCalls: updatedToolCalls } : msg;
        })
      );
    },
    [],
  );

  return {
    messages,
    sendMessage,
    sendMessageStream,
    cancelStream,
    clearChat,
    updateProposalResult,
    sessions,
    fetchSessions,
    loadHistory,
    sessionId,
    isLoadingSessions,
    isLoadingHistory,
    isLoading: mutation.isPending || isStreaming,
    isStreaming,
    error: mutation.error,
    selectedModel,
    setSelectedModel,
  };
}

