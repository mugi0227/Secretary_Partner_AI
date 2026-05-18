import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  FaClock,
  FaComments,
  FaFolder,
  FaHeartPulse,
  FaImage,
  FaPlus,
  FaXmark,
} from 'react-icons/fa6';
import { heartbeatApi } from '../../api/heartbeat';
import { tasksApi } from '../../api/tasks';
import { projectsApi } from '../../api/projects';
import type {
  Task,
  TaskAssignment,
  TaskAssignmentsCreate,
  ToolActionProposalPayload,
} from '../../api/types';
import type { ApprovalResult } from '../../api/proposals';
import { useChat, type ProposalInfo } from '../../hooks/useChat';
import { useHeartbeatUnreadCount } from '../../hooks/useHeartbeatUnreadCount';
import { useTaskModal } from '../../hooks/useTaskModal';
import { useTimezone } from '../../hooks/useTimezone';
import { formatDate } from '../../utils/dateTime';
import { ChatInput } from './ChatInput';
import { ChatMessage } from './ChatMessage';
import { DraftCard, DraftCardData } from './DraftCard';
import { ProposalPanel } from './ProposalPanel';
import { QuestionsPanel } from './QuestionsPanel';
import { userStorage } from '../../utils/userStorage';
import nagiIcon from '../../assets/nagi_icon.png';
import './ChatWindow.css';

const HEARTBEAT_SESSION_PREFIX = 'heartbeat-';
const LEGACY_HEARTBEAT_SESSION_ID = 'heartbeat';

const isHeartbeatSessionId = (sessionId: string) =>
  sessionId === LEGACY_HEARTBEAT_SESSION_ID
  || sessionId.startsWith(HEARTBEAT_SESSION_PREFIX);

interface ChatWindowProps {
  isOpen: boolean;
  onClose: () => void;
  initialMessage?: string | null;
  onInitialMessageConsumed?: () => void;
  draftCard?: DraftCardData | null;
  onDraftCardConsumed?: () => void;
  projectContext?: { projectId: string; projectName: string } | null;
}

export function ChatWindow({ isOpen, onClose, initialMessage, onInitialMessageConsumed, draftCard, onDraftCardConsumed, projectContext }: ChatWindowProps) {
  const queryClient = useQueryClient();
  const timezone = useTimezone();
  const {
    messages,
    sendMessageStream,
    cancelStream,
    clearChat,
    updateProposalResult,
    isLoading,
    isStreaming,
    sessions,
    fetchSessions,
    loadHistory,
    sessionId,
    isLoadingSessions,
    isLoadingHistory,
    selectedModel,
    setSelectedModel,
  } = useChat();
  const [processedProposalIds, setProcessedProposalIds] = useState<Set<string>>(new Set());
  const [processedQuestionMessageIds, setProcessedQuestionMessageIds] = useState<Set<string>>(new Set());
  const approvedProposalsRef = useRef<ProposalInfo[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const shouldAutoScroll = useRef(true);
  const [isDragging, setIsDragging] = useState(false);
  const [draggedImage, setDraggedImage] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [historyMode, setHistoryMode] = useState<'all' | 'heartbeat'>('all');
  const {
    count: heartbeatUnreadCount,
    unreadSessionIds: heartbeatUnreadSessionIds,
  } = useHeartbeatUnreadCount();
  const unreadHeartbeatSessionIds = useMemo(
    () => new Set(heartbeatUnreadSessionIds),
    [heartbeatUnreadSessionIds],
  );
  const hasHeartbeatUnread = heartbeatUnreadCount > 0;
  const [approvalMode, setApprovalMode] = useState<'manual' | 'auto'>(() => {
    return (userStorage.get('aiApprovalMode') as 'manual' | 'auto') || 'auto';
  });
  const { data: meetingTasks = [] } = useQuery<Task[]>({
    queryKey: ['meetings', 'chat-preview'],
    queryFn: () => tasksApi.getAll({ includeDone: true, onlyMeetings: true }),
    staleTime: 30_000,
    enabled: isOpen,
  });

  // Task modal for viewing created tasks inline
  const [modalProjectId, setModalProjectId] = useState<string | null>(null);
  const handleSelectedTaskChange = useCallback((task: Task | null) => {
    setModalProjectId(task?.project_id ?? null);
  }, []);

  const { data: projectMembers = [] } = useQuery({
    queryKey: ['project-members', modalProjectId],
    queryFn: () => projectsApi.listMembers(modalProjectId!),
    enabled: !!modalProjectId,
    staleTime: 5 * 60_000,
  });

  const { data: projectAssignments = [] } = useQuery<TaskAssignment[]>({
    queryKey: ['project-assignments', modalProjectId],
    queryFn: () => projectsApi.listAssignments(modalProjectId!),
    enabled: !!modalProjectId,
    staleTime: 30_000,
  });

  const memberOptions = useMemo(
    () => projectMembers.map((m) => ({
      id: m.member_user_id,
      label: m.member_display_name || m.member_user_id,
    })),
    [projectMembers],
  );

  const assignMutation = useMutation({
    mutationFn: ({ taskId, data }: { taskId: string; data: TaskAssignmentsCreate }) =>
      tasksApi.assignTaskMultiple(taskId, data),
    onSuccess: () => {
      for (const key of [
        ['project-assignments', modalProjectId],
        ['tasks'], ['task-detail'], ['task-assignments'], ['project'],
      ]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });

  const handleAssigneeChange = useCallback(
    (taskId: string, memberIds: string[]) => {
      assignMutation.mutate({ taskId, data: { assignee_ids: memberIds } });
    },
    [assignMutation],
  );

  const taskModal = useTaskModal({
    tasks: [],
    memberOptions,
    taskAssignments: projectAssignments,
    onAssigneeChange: handleAssigneeChange,
    onRefetch: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
    onSelectedTaskChange: handleSelectedTaskChange,
  });

  const markHeartbeatReadMutation = useMutation({
    mutationFn: heartbeatApi.markRead,
    onSuccess: (data) => {
      queryClient.setQueryData(['heartbeat', 'unread-count'], data);
      queryClient.invalidateQueries({ queryKey: ['heartbeat', 'unread-count'] });
    },
  });

  // Extract pending proposals from messages
  const pendingProposals = useMemo(() => {
    const allProposals = messages.flatMap((msg) => msg.proposals || []);
    return allProposals.filter((p) => !processedProposalIds.has(p.proposalId));
  }, [messages, processedProposalIds]);

  const invalidateAfterProposal = () => {
    for (const key of [
      ['tasks'], ['subtasks'], ['top3'], ['today-tasks'], ['today-plan'], ['schedule'],
      ['task-detail'], ['task-assignments'],
      ['projects'], ['project'], ['meeting-agendas'], ['member-child-tasks'],
    ]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };

  const shouldRecalculateSchedule = (proposal: ProposalInfo) => {
    if (proposal.proposalType !== 'tool_action') {
      return false;
    }
    const payload = proposal.payload as ToolActionProposalPayload;
    return payload.tool_name === 'apply_schedule_request';
  };

  const recalculateScheduleForProposals = async (proposals: ProposalInfo[]) => {
    if (!proposals.some(shouldRecalculateSchedule)) {
      return;
    }
    try {
      await tasksApi.recalculateSchedulePlan({
        fromNow: true,
        maxDays: 30,
        filterByAssignee: true,
      });
    } catch (error) {
      console.error('Failed to recalculate schedule after approval:', error);
    }
  };

  // Generate approval confirmation message for AI
  const generateApprovalMessage = (proposals: { description: string }[]) => {
    if (proposals.length === 1) {
      return `（承諾しました: ${proposals[0].description}）`;
    }
    const descriptions = proposals.map((p) => `・${p.description}`).join('\n');
    return `（以下を承諾しました:\n${descriptions}）`;
  };

  const handleProposalApproved = async (
    proposalId: string,
    proposal: ProposalInfo,
    result: ApprovalResult,
  ) => {
    updateProposalResult(proposalId, result);
    setProcessedProposalIds((prev) => new Set([...prev, proposalId]));
    approvedProposalsRef.current = [
      ...approvedProposalsRef.current,
      proposal,
    ];
    await recalculateScheduleForProposals([proposal]);
    invalidateAfterProposal();
    // Only send confirmation if this was the last pending proposal
    const remainingCount = pendingProposals.filter((p) => p.proposalId !== proposalId).length;
    if (remainingCount === 0) {
      const approvedBatch = approvedProposalsRef.current;
      if (approvedBatch.length > 0) {
        sendMessageStream(generateApprovalMessage(approvedBatch), undefined, undefined, projectContext);
      }
      approvedProposalsRef.current = [];
    }
  };

  const handleProposalRejected = (proposalId: string) => {
    setProcessedProposalIds((prev) => new Set([...prev, proposalId]));
    invalidateAfterProposal();
    const remainingCount = pendingProposals.filter((p) => p.proposalId !== proposalId).length;
    if (remainingCount === 0 && approvedProposalsRef.current.length > 0) {
      sendMessageStream(generateApprovalMessage(approvedProposalsRef.current), undefined, undefined, projectContext);
      approvedProposalsRef.current = [];
    }
  };

  const handleAllProposalsApproved = async (
    approvedProposals: ProposalInfo[],
    results: Record<string, ApprovalResult>,
  ) => {
    for (const [proposalId, result] of Object.entries(results)) {
      updateProposalResult(proposalId, result);
    }
    const allIds = pendingProposals.map((p) => p.proposalId);
    setProcessedProposalIds((prev) => new Set([...prev, ...allIds]));
    await recalculateScheduleForProposals(approvedProposals);
    invalidateAfterProposal();
    // Send confirmation to AI for all approved proposals
    sendMessageStream(generateApprovalMessage(approvedProposals), undefined, undefined, projectContext);
    approvedProposalsRef.current = [];
  };

  const handleAllProposalsRejected = () => {
    const allIds = pendingProposals.map((p) => p.proposalId);
    setProcessedProposalIds((prev) => new Set([...prev, ...allIds]));
    invalidateAfterProposal();
    approvedProposalsRef.current = [];
  };

  // Extract pending questions from messages
  const pendingQuestionsData = (() => {
    for (const msg of messages) {
      if (msg.questions && msg.questions.length > 0 && !processedQuestionMessageIds.has(msg.id)) {
        return { messageId: msg.id, questions: msg.questions, context: msg.questionsContext };
      }
    }
    return null;
  })();

  const handleQuestionsSubmit = (answer: string) => {
    if (pendingQuestionsData) {
      setProcessedQuestionMessageIds((prev) => new Set([...prev, pendingQuestionsData.messageId]));
      sendMessageStream(answer, undefined, undefined, projectContext);
    }
  };

  const handleQuestionsCancel = () => {
    if (pendingQuestionsData) {
      setProcessedQuestionMessageIds((prev) => new Set([...prev, pendingQuestionsData.messageId]));
    }
  };

  useEffect(() => {
    if (messagesEndRef.current) {
      const behavior = shouldAutoScroll.current ? 'auto' : 'smooth';
      messagesEndRef.current.scrollIntoView({ behavior });
      shouldAutoScroll.current = false;
    }
  }, [messages]);

  useEffect(() => {
    if (isHistoryOpen) {
      fetchSessions();
    }
  }, [isHistoryOpen, fetchSessions]);

  // Note: initialMessage is now passed to ChatInput instead of auto-sending

  // Handle draft card from external sources
  // DraftCard (AI生成ダイアログ) 使用時は、デフォルトで新規チャットを作成する
  // 既存チャットに追加したい場合は、明示的に newChat: false を指定する
  useEffect(() => {
    if (draftCard && draftCard.newChat !== false) {
      clearChat();
    }
  }, [draftCard, clearChat]);

  const processImageFile = (file: File) => {
    // Check file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      alert('画像ファイルは5MB以下にしてください');
      return;
    }

    // Check file type
    if (!file.type.startsWith('image/')) {
      alert('画像ファイルを選択してください');
      return;
    }

    // Convert to Base64
    const reader = new FileReader();
    reader.onload = () => {
      setDraggedImage(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isLoading && e.dataTransfer.types.includes('Files')) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only hide overlay when leaving the window entirely
    if (e.currentTarget === e.target) {
      setIsDragging(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (isLoading) return;

    const files = Array.from(e.dataTransfer.files);
    const imageFile = files.find(file => file.type.startsWith('image/'));

    if (imageFile) {
      processImageFile(imageFile);
    }
  };

  const handleSelectSession = async (targetSessionId: string) => {
    try {
      shouldAutoScroll.current = true;
      await loadHistory(targetSessionId);
      setIsHistoryOpen(false);
    } catch (error) {
      console.error('Failed to load history:', error);
      alert('Failed to load history.');
    }
  };

  const formatSessionDate = (value?: string) => {
    if (!value) return 'Recent';
    return formatDate(
      value,
      { year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' },
      timezone,
    );
  };

  const handleApprovalModeChange = (mode: 'manual' | 'auto') => {
    setApprovalMode(mode);
    userStorage.set('aiApprovalMode', mode);
  };

  const heartbeatSessions = useMemo(
    () => sessions.filter((session) => isHeartbeatSessionId(session.session_id)),
    [sessions],
  );

  const regularSessions = useMemo(
    () => sessions.filter((session) => !isHeartbeatSessionId(session.session_id)),
    [sessions],
  );

  const visibleSessions = historyMode === 'heartbeat'
    ? heartbeatSessions
    : regularSessions;

  const historyTitle = historyMode === 'heartbeat'
    ? 'Heartbeat チャット'
    : 'Recent Chats';

  const emptyHistoryText = historyMode === 'heartbeat'
    ? 'まだHeartbeatはありません。'
    : 'No sessions yet.';

  const toggleHistory = (mode: 'all' | 'heartbeat') => {
    setHistoryMode(mode);
    setIsHistoryOpen((prev) => (prev && historyMode === mode ? false : true));
  };

  if (!isOpen) return null;

  return (
    <div
      className={`chat-window ${isDragging ? 'dragging' : ''}`}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="chat-drag-overlay">
          <div className="drag-overlay-content">
            <FaImage size={64} />
            <p>画像をドロップしてください</p>
          </div>
        </div>
      )}
      <div className="chat-header">
        <div className="chat-title-area">
          <div className="chat-title">
            <img src={nagiIcon} alt="Nagi" className="chat-title-icon" />
            <span>nagi</span>
          </div>
          {projectContext && (
            <div className="chat-project-scope">
              <FaFolder />
              <span>{projectContext.projectName}</span>
            </div>
          )}
        </div>
        <div className="chat-header-controls">
          <div className="chat-approval-toggle" role="group" aria-label="Approval mode">
            <button
              className={`approval-toggle-btn ${approvalMode === 'manual' ? 'active' : ''}`}
              onClick={() => handleApprovalModeChange('manual')}
              type="button"
              title="Require approval for edits"
            >
              Manual
            </button>
            <button
              className={`approval-toggle-btn ${approvalMode === 'auto' ? 'active' : ''}`}
              onClick={() => handleApprovalModeChange('auto')}
              type="button"
              title="Auto-run tools"
            >
              Auto
            </button>
          </div>
          <div className="chat-header-actions">
            <button
              className={`header-btn heartbeat-header-btn ${hasHeartbeatUnread ? 'has-unread' : ''}`}
              onClick={() => toggleHistory('heartbeat')}
              title={hasHeartbeatUnread ? `Heartbeat (${heartbeatUnreadCount} new)` : 'Heartbeat'}
              aria-label={hasHeartbeatUnread ? `Heartbeat (${heartbeatUnreadCount} new)` : 'Heartbeat'}
            >
              <FaHeartPulse />
              {hasHeartbeatUnread && (
                <span className="header-btn-badge" aria-hidden="true">
                  {heartbeatUnreadCount}
                </span>
              )}
            </button>
            <button
              className="header-btn"
              onClick={() => toggleHistory('all')}
              title="History"
            >
              <FaClock />
            </button>
            <button className="header-btn" onClick={clearChat} title="New chat">
              <FaPlus />
            </button>
            <button className="header-btn close-btn" onClick={onClose} title="Close">
              <FaXmark />
            </button>
          </div>
        </div>
      </div>

      {isHistoryOpen && (
        <div className="chat-history-panel">
          <div className="history-panel-header">
            <span>{historyTitle}</span>
            <div className="history-panel-actions">
              {historyMode === 'heartbeat' && hasHeartbeatUnread && (
                <button
                  className="history-mark-read-btn"
                  onClick={() => markHeartbeatReadMutation.mutate()}
                  type="button"
                  disabled={markHeartbeatReadMutation.isPending}
                >
                  すべて既読
                </button>
              )}
              <button
                className="header-btn close-btn"
                onClick={() => setIsHistoryOpen(false)}
                title="Close history"
              >
                <FaXmark />
              </button>
            </div>
          </div>
          <div className="history-panel-list">
            {(isLoadingSessions || isLoadingHistory) && (
              <div className="history-panel-empty">Loading history...</div>
            )}
            {!isLoadingSessions && !isLoadingHistory && visibleSessions.length === 0 && (
              <div className="history-panel-empty">{emptyHistoryText}</div>
            )}
            {!isLoadingSessions && !isLoadingHistory && visibleSessions.map((session) => (
              (() => {
                const isUnreadHeartbeatSession =
                  historyMode === 'heartbeat'
                  && unreadHeartbeatSessionIds.has(session.session_id);
                return (
              <button
                key={session.session_id}
                className={`history-panel-item ${session.session_id === sessionId ? 'active' : ''} ${isUnreadHeartbeatSession ? 'unread' : ''}`}
                onClick={() => handleSelectSession(session.session_id)}
                type="button"
                disabled={isLoadingHistory}
              >
                <span className="history-panel-title-row">
                  <span className="history-panel-title">{session.title || 'New Chat'}</span>
                  {isUnreadHeartbeatSession && (
                    <span className="history-new-badge">新規</span>
                  )}
                </span>
                <span className="history-panel-date">{formatSessionDate(session.updated_at)}</span>
              </button>
                );
              })()
            ))}
          </div>
        </div>
      )}

      <div className="chat-history">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="empty-icon">
              <FaComments />
            </div>
            <p className="empty-title">会話を始めましょう</p>
            <p className="empty-hint">
              何か頭にあることを書き出しますか？それともタスクの相談をしますか？
            </p>
          </div>
        )}
        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            role={message.role}
            content={message.content}
            timestamp={message.timestamp}
            toolCalls={message.toolCalls}
            proposals={message.proposals}
            meetingTasks={meetingTasks}
            isStreaming={message.isStreaming}
            imageUrl={message.imageUrl}
            toolPlacement={message.toolPlacement}
            timeline={message.timeline}
            onTaskClick={taskModal.openTaskDetailById}
            usage={message.usage}
          />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Priority: DraftCard > ProposalPanel > QuestionsPanel > ChatInput */}
      {draftCard ? (
        <DraftCard
          data={draftCard}
          onSend={(message) => {
            sendMessageStream(message, undefined, undefined, projectContext);
            onDraftCardConsumed?.();
          }}
          onCancel={() => onDraftCardConsumed?.()}
        />
      ) : pendingProposals.length > 0 ? (
        <ProposalPanel
          proposals={pendingProposals}
          onApproved={handleProposalApproved}
          onRejected={handleProposalRejected}
          onAllApproved={handleAllProposalsApproved}
          onAllRejected={handleAllProposalsRejected}
        />
      ) : pendingQuestionsData ? (
        <QuestionsPanel
          questions={pendingQuestionsData.questions}
          context={pendingQuestionsData.context}
          onSubmit={handleQuestionsSubmit}
          onCancel={handleQuestionsCancel}
        />
      ) : (
        <ChatInput
          onSend={(message, imageBase64, audioBase64, audioMimeType) =>
            sendMessageStream(
              message,
              imageBase64,
              undefined,
              projectContext,
              audioBase64,
              audioMimeType,
            )
          }
          onCancel={cancelStream}
          disabled={isLoading}
          isStreaming={isStreaming}
          externalImage={draggedImage}
          onImageClear={() => setDraggedImage(null)}
          initialValue={initialMessage}
          onInitialValueConsumed={onInitialMessageConsumed}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
        />
      )}

      {createPortal(taskModal.renderModals(), document.body)}
    </div>
  );
}
