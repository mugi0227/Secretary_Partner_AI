import { FaSpinner, FaCheck, FaWrench } from 'react-icons/fa6';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ToolCall } from '../../hooks/useChat';
import './ChatMessage.css';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolCalls?: ToolCall[];
  isStreaming?: boolean;
}

export function ChatMessage({ role, content, timestamp, toolCalls, isStreaming }: ChatMessageProps) {
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('ja-JP', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getToolDisplayName = (toolName: string): string => {
    const toolNames: Record<string, string> = {
      get_current_datetime: '日時取得',
      create_task: 'タスク作成',
      update_task: 'タスク更新',
      delete_task: 'タスク削除',
      search_similar_tasks: 'タスク検索',
      breakdown_task: 'タスク分解',
      search_work_memory: 'メモリ検索',
      add_to_memory: 'メモリ追加',
      schedule_agent_task: 'スケジュール',
    };
    return toolNames[toolName] || toolName;
  };

  return (
    <div className={`chat-message ${role}`}>
      <div className="message-avatar">
        {role === 'assistant' ? '🤖' : '👤'}
      </div>
      <div className="message-content">
        {/* Tool Calls */}
        {toolCalls && toolCalls.length > 0 && (
          <div className="tool-calls">
            {toolCalls.map((tool) => (
              <div key={tool.id} className={`tool-call ${tool.status}`}>
                <div className="tool-icon">
                  {tool.status === 'running' ? (
                    <FaSpinner className="spinner" />
                  ) : (
                    <FaCheck />
                  )}
                </div>
                <div className="tool-info">
                  <div className="tool-name">
                    <FaWrench className="tool-wrench" />
                    {getToolDisplayName(tool.name)}
                  </div>
                  {tool.status === 'running' && (
                    <div className="tool-status">実行中...</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Message Text */}
        {content && (
          <div className="message-text markdown-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
            {isStreaming && <span className="streaming-cursor">▋</span>}
          </div>
        )}

        <div className="message-time">{formatTime(timestamp)}</div>
      </div>
    </div>
  );
}
