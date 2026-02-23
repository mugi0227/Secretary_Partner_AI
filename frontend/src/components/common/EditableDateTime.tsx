import { AnimatePresence, motion } from 'framer-motion';
import { DateTime } from 'luxon';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FaClock, FaEdit, FaTimes, FaTrash } from 'react-icons/fa';
import { getStoredTimezone } from '../../utils/dateTime';
import './EditableDateTime.css';

interface EditableDateTimeProps {
  value: string | null | undefined;
  onSave: (newValue: string | null) => Promise<void>;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  timezone?: string;
  showTime?: boolean;
  icon?: React.ReactNode;
  formatDisplay?: (value: string, tz: string) => string;
}

export function EditableDateTime({
  value,
  onSave,
  placeholder = '未設定',
  className = '',
  disabled = false,
  timezone = getStoredTimezone(),
  showTime = true,
  icon,
  formatDisplay,
}: EditableDateTimeProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [pendingValue, setPendingValue] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const blurTimeoutRef = useRef<number>();

  // Convert ISO string to local datetime-local format
  const toLocalInput = useCallback((isoString: string | null | undefined): string => {
    if (!isoString) return '';
    try {
      const dt = DateTime.fromISO(isoString, { zone: timezone });
      if (!dt.isValid) return '';
      return showTime
        ? dt.toFormat("yyyy-MM-dd'T'HH:mm")
        : dt.toFormat('yyyy-MM-dd');
    } catch {
      return '';
    }
  }, [timezone, showTime]);

  // Convert local datetime-local to ISO string
  const toISOString = useCallback((localValue: string): string | null => {
    if (!localValue) return null;
    try {
      const dt = DateTime.fromISO(localValue, { zone: timezone });
      if (!dt.isValid) return null;
      return dt.toISO();
    } catch {
      return null;
    }
  }, [timezone]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isEditing]);

  // Cleanup blur timeout on unmount
  useEffect(() => {
    return () => {
      if (blurTimeoutRef.current) {
        clearTimeout(blurTimeoutRef.current);
      }
    };
  }, []);

  const handleStartEdit = useCallback(() => {
    if (disabled) return;
    setPendingValue(toLocalInput(value));
    setIsEditing(true);
  }, [value, disabled, toLocalInput]);

  const handleSave = useCallback(async () => {
    if (blurTimeoutRef.current) clearTimeout(blurTimeoutRef.current);
    if (isSaving) return;
    setIsSaving(true);
    try {
      const isoValue = toISOString(pendingValue);
      await onSave(isoValue);
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to save:', error);
    } finally {
      setIsSaving(false);
    }
  }, [pendingValue, onSave, isSaving, toISOString]);

  const handleClear = useCallback(async () => {
    if (blurTimeoutRef.current) clearTimeout(blurTimeoutRef.current);
    if (isSaving) return;
    setIsSaving(true);
    try {
      await onSave(null);
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to clear:', error);
    } finally {
      setIsSaving(false);
    }
  }, [onSave, isSaving]);

  const handleNow = useCallback(() => {
    const now = DateTime.now().setZone(timezone);
    const formatted = showTime
      ? now.toFormat("yyyy-MM-dd'T'HH:mm")
      : now.toFormat('yyyy-MM-dd');
    setPendingValue(formatted);
  }, [timezone, showTime]);

  const handleCancel = useCallback(() => {
    if (blurTimeoutRef.current) clearTimeout(blurTimeoutRef.current);
    setIsEditing(false);
    setPendingValue('');
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleCancel();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      handleSave();
    }
  }, [handleCancel, handleSave]);

  // Auto-save when focus leaves the entire component
  const handleContainerBlur = useCallback((e: React.FocusEvent) => {
    const relatedTarget = e.relatedTarget as Node | null;
    if (relatedTarget && containerRef.current?.contains(relatedTarget)) return;

    blurTimeoutRef.current = window.setTimeout(() => {
      if (containerRef.current && !containerRef.current.contains(document.activeElement)) {
        handleSave();
      }
    }, 150);
  }, [handleSave]);

  const handleContainerFocus = useCallback(() => {
    if (blurTimeoutRef.current) {
      clearTimeout(blurTimeoutRef.current);
    }
  }, []);

  const displayValue = value
    ? (formatDisplay
      ? formatDisplay(value, timezone)
      : DateTime.fromISO(value, { zone: timezone }).toFormat('yyyy/MM/dd HH:mm'))
    : null;

  return (
    <div
      ref={containerRef}
      className={`editable-datetime ${className} ${isEditing ? 'editing' : ''} ${disabled ? 'disabled' : ''}`}
      onBlur={isEditing ? handleContainerBlur : undefined}
      onFocus={isEditing ? handleContainerFocus : undefined}
    >
      <AnimatePresence mode="wait">
        {isEditing ? (
          <motion.div
            key="edit"
            className="datetime-edit-mode"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <input
              ref={inputRef}
              type={showTime ? 'datetime-local' : 'date'}
              value={pendingValue}
              onChange={(e) => setPendingValue(e.target.value)}
              onKeyDown={handleKeyDown}
              className="datetime-input"
              disabled={isSaving}
            />
            <div className="datetime-actions">
              <button
                type="button"
                className="datetime-btn now"
                onClick={handleNow}
                disabled={isSaving}
                title="今"
              >
                <FaClock />
              </button>
              {value && (
                <button
                  type="button"
                  className="datetime-btn clear"
                  onClick={handleClear}
                  disabled={isSaving}
                  title="クリア"
                >
                  <FaTrash />
                </button>
              )}
              <button
                type="button"
                className="datetime-btn cancel"
                onClick={handleCancel}
                disabled={isSaving}
                title="キャンセル"
              >
                <FaTimes />
              </button>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="view"
            className="datetime-view-mode"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={handleStartEdit}
          >
            <span className={`datetime-value ${!displayValue ? 'empty' : ''}`}>
              {icon}
              {displayValue || placeholder}
            </span>
            {!disabled && (
              <button
                type="button"
                className="datetime-edit-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  handleStartEdit();
                }}
                title="編集"
              >
                <FaEdit />
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
