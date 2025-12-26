import { useState, useRef, useEffect, KeyboardEvent, ChangeEvent } from 'react';
import { FaPlus, FaMicrophone, FaPaperPlane, FaImage, FaXmark } from 'react-icons/fa6';
import './ChatInput.css';

interface ChatInputProps {
  onSend: (message: string, imageBase64?: string) => void;
  disabled?: boolean;
  externalImage?: string | null;
  onImageClear?: () => void;
}

export function ChatInput({ onSend, disabled, externalImage, onImageClear }: ChatInputProps) {
  const [input, setInput] = useState('');
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync external image to selected image
  useEffect(() => {
    if (externalImage) {
      setSelectedImage(externalImage);
    }
  }, [externalImage]);

  // Auto-resize textarea based on content
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
    }
  }, [input]);

  const handleSubmit = () => {
    if ((input.trim() || selectedImage) && !disabled) {
      onSend(input.trim() || '画像を添付しました', selectedImage || undefined);
      setInput('');
      setSelectedImage(null);
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleImageSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processImageFile(file);
    }
  };

  const handleRemoveImage = () => {
    setSelectedImage(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    if (onImageClear) {
      onImageClear();
    }
  };

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
      setSelectedImage(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter without Shift = Submit
    // Shift+Enter = New line (default behavior)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="chat-input-container">
      {selectedImage && (
        <div className="image-preview">
          <img src={selectedImage} alt="Selected" />
          <button className="remove-image-btn" onClick={handleRemoveImage} title="画像を削除">
            <FaXmark />
          </button>
        </div>
      )}
      <div className="chat-input-area">
        <input
          type="file"
          ref={fileInputRef}
          accept="image/*"
          onChange={handleImageSelect}
          style={{ display: 'none' }}
        />
        <button
          className="input-action-btn"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          title="画像を添付"
        >
          <FaImage />
        </button>
        <div className="input-wrapper">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="メッセージを入力... (Shift+Enterで改行)"
            disabled={disabled}
            rows={1}
          />
        </div>
        <button className="mic-btn" title="音声入力" disabled>
          <FaMicrophone />
        </button>
        <button
          className="send-btn"
          onClick={handleSubmit}
          disabled={(!input.trim() && !selectedImage) || disabled}
          title="送信"
        >
          <FaPaperPlane />
        </button>
      </div>
    </div>
  );
}
