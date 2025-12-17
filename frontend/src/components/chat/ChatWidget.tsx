import { useState } from 'react';
import { FaComments, FaXmark } from 'react-icons/fa6';
import { ChatWindow } from './ChatWindow';
import './ChatWidget.css';

export function ChatWidget() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        className="chat-fab"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Open chat"
      >
        {isOpen ? <FaXmark /> : <FaComments />}
      </button>
      <ChatWindow isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  );
}
