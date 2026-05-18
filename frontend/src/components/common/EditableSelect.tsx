import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FaCheck, FaChevronDown, FaEdit, FaTimes } from 'react-icons/fa';
import './EditableSelect.css';

export interface SelectOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
}

interface EditableSelectProps {
  value: string | null | undefined;
  options: SelectOption[];
  onSave: (newValue: string | null) => Promise<void>;
  placeholder?: string;
  className?: string;
  allowClear?: boolean;
  disabled?: boolean;
  renderValue?: (option: SelectOption | null) => React.ReactNode;
  icon?: React.ReactNode;
}

export function EditableSelect({
  value,
  options,
  onSave,
  placeholder = '未設定',
  className = '',
  allowClear = true,
  disabled = false,
  renderValue,
  icon,
}: EditableSelectProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [pendingValue, setPendingValue] = useState<string | null>(value ?? null);
  const [isSaving, setIsSaving] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const selectRef = useRef<HTMLDivElement>(null);

  const handleCancel = useCallback(() => {
    setIsEditing(false);
    setIsOpen(false);
    setPendingValue(value ?? null);
  }, [value]);

  useEffect(() => {
    if (isEditing) {
      setPendingValue(value ?? null);
      setIsOpen(true);
    }
  }, [isEditing, value]);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (selectRef.current && !selectRef.current.contains(e.target as Node)) {
        handleCancel();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen, handleCancel]);

  const handleStartEdit = useCallback(() => {
    if (disabled) return;
    setIsEditing(true);
  }, [disabled]);

  const handleSave = useCallback(async () => {
    if (isSaving) return;
    setIsSaving(true);
    try {
      await onSave(pendingValue);
      setIsEditing(false);
      setIsOpen(false);
    } catch (error) {
      console.error('Failed to save:', error);
    } finally {
      setIsSaving(false);
    }
  }, [pendingValue, onSave, isSaving]);

  const handleSelect = useCallback(async (optionValue: string | null) => {
    if (isSaving) return;
    setPendingValue(optionValue);
    setIsSaving(true);
    try {
      await onSave(optionValue);
      setIsEditing(false);
      setIsOpen(false);
    } catch (error) {
      console.error('Failed to save:', error);
    } finally {
      setIsSaving(false);
    }
  }, [onSave, isSaving]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleCancel();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      handleSave();
    }
  }, [handleCancel, handleSave]);

  const selectedOption = options.find(opt => opt.value === value) ?? null;
  const pendingOption = options.find(opt => opt.value === pendingValue) ?? null;

  const renderDisplayValue = (opt: SelectOption | null) => {
    if (renderValue) {
      return renderValue(opt);
    }
    if (!opt) {
      return <span className="editable-select-placeholder">{placeholder}</span>;
    }
    return (
      <span className="editable-select-value">
        {opt.icon}
        {opt.label}
      </span>
    );
  };

  return (
    <div
      className={`editable-select ${className} ${isEditing ? 'editing' : ''} ${disabled ? 'disabled' : ''}`}
      ref={selectRef}
      onKeyDown={handleKeyDown}
    >
      <AnimatePresence mode="wait">
        {isEditing ? (
          <motion.div
            key="edit"
            className="editable-select-edit-mode"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <div className="editable-select-dropdown-wrapper">
              <button
                type="button"
                className="editable-select-trigger"
                onClick={() => setIsOpen(!isOpen)}
                disabled={isSaving}
              >
                {icon}
                {pendingOption ? pendingOption.label : placeholder}
                <FaChevronDown className={`chevron ${isOpen ? 'open' : ''}`} />
              </button>

              <AnimatePresence>
                {isOpen && (
                  <motion.ul
                    className="editable-select-options"
                    initial={{ opacity: 0, y: -8, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -8, scale: 0.95 }}
                    transition={{ duration: 0.15 }}
                  >
                    {allowClear && (
                      <li
                        className={`editable-select-option ${pendingValue === null ? 'selected' : ''}`}
                        onClick={() => handleSelect(null)}
                      >
                        <span className="option-label">{placeholder}</span>
                        {pendingValue === null && <FaCheck className="check-icon" />}
                      </li>
                    )}
                    {options.map((option) => (
                      <li
                        key={option.value}
                        className={`editable-select-option ${pendingValue === option.value ? 'selected' : ''}`}
                        onClick={() => handleSelect(option.value)}
                      >
                        {option.icon && <span className="option-icon">{option.icon}</span>}
                        <span className="option-label">{option.label}</span>
                        {pendingValue === option.value && <FaCheck className="check-icon" />}
                      </li>
                    ))}
                  </motion.ul>
                )}
              </AnimatePresence>
            </div>

            <div className="editable-select-actions">
              <button
                type="button"
                className="editable-select-btn cancel"
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
            className="editable-select-view-mode"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={handleStartEdit}
          >
            <div className="editable-select-content">
              {icon}
              {renderDisplayValue(selectedOption)}
            </div>
            {!disabled && (
              <button
                type="button"
                className="editable-select-edit-btn"
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
