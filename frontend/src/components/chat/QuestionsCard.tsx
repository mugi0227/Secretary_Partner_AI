import { useState } from 'react';
import { FaCircleQuestion, FaCheck } from 'react-icons/fa6';
import type { PendingQuestion } from '../../api/types';
import './QuestionsCard.css';

const OTHER_OPTION = 'その他（自由入力）';

interface QuestionState {
  selectedOptions: string[];
  otherText: string;
}

interface QuestionsCardProps {
  questions: PendingQuestion[];
  context?: string;
  onSubmit: (answers: string) => void;
  onCancel?: () => void;
}

export function QuestionsCard({ questions, context, onSubmit, onCancel }: QuestionsCardProps) {
  // Initialize state for each question
  const [answers, setAnswers] = useState<Record<string, QuestionState>>(() => {
    const initial: Record<string, QuestionState> = {};
    questions.forEach((q) => {
      initial[q.id] = { selectedOptions: [], otherText: '' };
    });
    return initial;
  });

  const handleOptionChange = (questionId: string, option: string, isMultiple: boolean) => {
    setAnswers((prev) => {
      const current = prev[questionId];
      let newSelected: string[];

      if (isMultiple) {
        // Checkbox: toggle the option
        if (current.selectedOptions.includes(option)) {
          newSelected = current.selectedOptions.filter((o) => o !== option);
        } else {
          newSelected = [...current.selectedOptions, option];
        }
      } else {
        // Radio: replace selection
        newSelected = [option];
      }

      return {
        ...prev,
        [questionId]: { ...current, selectedOptions: newSelected },
      };
    });
  };

  const handleOtherTextChange = (questionId: string, text: string) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: { ...prev[questionId], otherText: text },
    }));
  };

  const formatAnswersAsText = (): string => {
    const lines: string[] = [];

    questions.forEach((q) => {
      const answer = answers[q.id];
      const selected = answer.selectedOptions.filter((o) => o !== OTHER_OPTION);
      const hasOtherSelected = answer.selectedOptions.includes(OTHER_OPTION);
      const otherText = answer.otherText.trim();

      let answerText: string;
      if (selected.length === 0 && hasOtherSelected) {
        answerText = otherText || 'その他';
      } else if (selected.length > 0 && hasOtherSelected) {
        answerText = [...selected, otherText || 'その他'].join('、');
      } else if (selected.length > 0) {
        answerText = selected.join('、');
      } else {
        answerText = '（未回答）';
      }

      lines.push(`${q.question}: ${answerText}`);
    });

    return lines.join('\n');
  };

  const handleSubmit = () => {
    const formattedText = formatAnswersAsText();
    onSubmit(formattedText);
  };

  const hasAnyAnswer = questions.some((q) => answers[q.id].selectedOptions.length > 0);

  const unansweredCount = questions.filter((q) => answers[q.id].selectedOptions.length === 0).length;

  return (
    <div className="questions-card">
      <div className="questions-card-header">
        <span className="questions-card-icon"><FaCircleQuestion /></span>
        <span className="questions-card-title">確認事項</span>
      </div>
      <div className="questions-card-body">
        {context && (
          <div className="questions-card-context">{context}</div>
        )}

        <div className="questions-card-list">
          {questions.map((q, index) => {
            const isAnswered = answers[q.id].selectedOptions.length > 0;
            return (
            <div key={q.id} className={`questions-card-item${isAnswered ? ' questions-card-item--answered' : ''}`}>
              <div className="questions-card-question">
                <span className="questions-card-number">{index + 1}.</span>
                {q.question}
                {isAnswered && <FaCheck className="questions-card-check" />}
              </div>
              <div className="questions-card-options">
                {q.options.map((option) => (
                  <label key={option} className="questions-card-option">
                    <input
                      type={q.allow_multiple ? 'checkbox' : 'radio'}
                      name={`question-${q.id}`}
                      checked={answers[q.id].selectedOptions.includes(option)}
                      onChange={() => handleOptionChange(q.id, option, q.allow_multiple)}
                    />
                    <span className="questions-card-option-text">{option}</span>
                  </label>
                ))}
                {/* その他（自由入力）オプション */}
                <label className="questions-card-option">
                  <input
                    type={q.allow_multiple ? 'checkbox' : 'radio'}
                    name={`question-${q.id}`}
                    checked={answers[q.id].selectedOptions.includes(OTHER_OPTION)}
                    onChange={() => handleOptionChange(q.id, OTHER_OPTION, q.allow_multiple)}
                  />
                  <span className="questions-card-option-text">{OTHER_OPTION}</span>
                </label>
                {answers[q.id].selectedOptions.includes(OTHER_OPTION) && (
                  <input
                    type="text"
                    className="questions-card-other-input"
                    placeholder="自由に入力（任意）"
                    value={answers[q.id].otherText}
                    onChange={(e) => handleOtherTextChange(q.id, e.target.value)}
                    autoFocus
                  />
                )}
              </div>
            </div>
            );
          })}
        </div>

        <div className="questions-card-actions">
          {onCancel && (
            <button className="questions-card-btn-cancel" onClick={onCancel}>
              {hasAnyAnswer ? '回答を破棄してスキップ' : 'スキップ'}
            </button>
          )}
          <button
            className="questions-card-btn-send"
            onClick={handleSubmit}
            disabled={!hasAnyAnswer}
          >
            {unansweredCount > 0 && hasAnyAnswer
              ? `回答する（${unansweredCount}件未回答）`
              : '回答する'}
          </button>
        </div>
      </div>
    </div>
  );
}
