import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useQueryClient } from '@tanstack/react-query';
import { FaChevronRight } from 'react-icons/fa';
import { tasksApi } from '../../api/tasks';
import { todayInTimezone } from '../../utils/dateTime';
import { useTimezone } from '../../hooks/useTimezone';
import './PostponePopover.css';

interface PostponePopoverProps {
  taskId: string;
  className?: string;
  onSuccess?: () => void;
}

export function PostponePopover({ taskId, className, onSuccess }: PostponePopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const timezone = useTimezone();

  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setPopoverPos({
      top: rect.bottom + 4,
      left: rect.right,
    });
  }, []);

  // Position + outside click
  useEffect(() => {
    if (!isOpen) return;
    updatePosition();

    const handleClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        triggerRef.current?.contains(target) ||
        popoverRef.current?.contains(target)
      ) return;
      setIsOpen(false);
      setShowDatePicker(false);
      setReason('');
    };

    const handleScroll = () => updatePosition();

    document.addEventListener('mousedown', handleClick);
    window.addEventListener('scroll', handleScroll, true);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      window.removeEventListener('scroll', handleScroll, true);
    };
  }, [isOpen, updatePosition]);

  const invalidateAll = () => {
    for (const key of [
      ['tasks'], ['subtasks'], ['top3'], ['today-tasks'], ['today-plan'], ['schedule'],
      ['task-detail'], ['task-assignments'], ['project'],
    ]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };

  const handlePostpone = async (dateStr: string, pin: boolean) => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await tasksApi.postpone(taskId, {
        to_date: dateStr,
        pin,
        reason: reason.trim() || undefined,
      });
      if (onSuccess) {
        onSuccess();
      } else {
        invalidateAll();
      }
      setIsOpen(false);
      setShowDatePicker(false);
      setReason('');
    } catch {
      alert('延期に失敗しました');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTomorrow = (e: React.MouseEvent) => {
    e.stopPropagation();
    const tomorrow = todayInTimezone(timezone).plus({ days: 1 });
    handlePostpone(tomorrow.toISODate()!, false);
  };

  const handleDateSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const dateStr = e.target.value;
    if (dateStr) {
      handlePostpone(dateStr, true);
    }
  };

  const minDate = todayInTimezone(timezone).plus({ days: 2 }).toISODate()!;

  return (
    <div className={`postpone-popover-wrapper ${className || ''}`}>
      <button
        ref={triggerRef}
        className="postpone-trigger-btn"
        onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen); }}
        title="明日やる / 延期する"
        disabled={isSubmitting}
      >
        <FaChevronRight size={10} />
      </button>

      {isOpen && popoverPos && createPortal(
        <div
          ref={popoverRef}
          className="postpone-popover"
          style={{ top: popoverPos.top, left: popoverPos.left }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            className="postpone-tomorrow-btn"
            onClick={handleTomorrow}
            disabled={isSubmitting}
          >
            明日やる
          </button>

          {!showDatePicker ? (
            <button
              className="postpone-pick-date-btn"
              onClick={() => setShowDatePicker(true)}
            >
              日付を選択...
            </button>
          ) : (
            <input
              type="date"
              className="postpone-date-input"
              min={minDate}
              onChange={handleDateSelect}
              autoFocus
            />
          )}

          <input
            type="text"
            className="postpone-reason-input"
            placeholder="理由（任意）"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
          />
        </div>,
        document.body,
      )}
    </div>
  );
}
