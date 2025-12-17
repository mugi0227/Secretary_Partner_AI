import { useEffect, useRef } from 'react';
import { FaRobot, FaTrash, FaXmark, FaComments } from 'react-icons/fa6';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { useChat } from '../../hooks/useChat';
import './ChatWindow.css';

interface ChatWindowProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ChatWindow({ isOpen, onClose }: ChatWindowProps) {
  const { messages, sendMessageStream, clearChat, isLoading } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  if (!isOpen) return null;

  return (
      <div className="chat-window">
        <div className="chat-header">
          <div className="chat-title">
            <FaRobot />
            <span>Secretary Partner</span>
          </div>
          <div className="chat-header-actions">
            <button className="header-btn" onClick={clearChat} title="Clear chat">
              <FaTrash />
            </button>
            <button className="header-btn close-btn" onClick={onClose} title="Close">
              <FaXmark />
            </button>
          </div>
        </div>

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
              isStreaming={message.isStreaming}
            />
          ))}
          <div ref={messagesEndRef} />
        </div>

        <ChatInput onSend={sendMessageStream} disabled={isLoading} />
      </div>
  );
}
