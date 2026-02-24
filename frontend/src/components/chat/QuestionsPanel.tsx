import { useState, useCallback, useRef } from 'react';
import { FaCircleQuestion, FaChevronLeft, FaChevronRight } from 'react-icons/fa6';
import type { PendingQuestion } from '../../api/types';
import './QuestionsPanel.css';

const OTHER_OPTION = 'その他（自由入力）';

interface QuestionState {
  selectedOptions: string[];
  otherText: string;
  freeText: string; // for free-text questions (no options)
}

interface QuestionsPanelProps {
  questions: PendingQuestion[];
  context?: string;
  onSubmit: (answers: string) => void;
  onCancel?: () => void;
}

/** Single question, ≤3 options, single-select → compact button UI */
function isSimpleConfirmation(questions: PendingQuestion[]): boolean {
  return (
    questions.length === 1 &&
    questions[0].options.length > 0 &&
    questions[0].options.length <= 3 &&
    !questions[0].allow_multiple
  );
}

/** Single question, no options → free-text input UI */
function isFreeTextOnly(questions: PendingQuestion[]): boolean {
  return questions.length === 1 && questions[0].options.length === 0;
}

/** Question has no predefined options */
function isFreeTextQuestion(q: PendingQuestion): boolean {
  return q.options.length === 0;
}

export function QuestionsPanel({ questions, context, onSubmit, onCancel }: QuestionsPanelProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showOtherInput, setShowOtherInput] = useState(false);
  const [simpleOtherText, setSimpleOtherText] = useState('');
  const [declineOption, setDeclineOption] = useState<string | null>(null);
  const [declineText, setDeclineText] = useState('');
  const autoAdvanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [answers, setAnswers] = useState<Record<string, QuestionState>>(() => {
    const initial: Record<string, QuestionState> = {};
    questions.forEach((q) => {
      initial[q.id] = { selectedOptions: [], otherText: '', freeText: '' };
    });
    return initial;
  });

  const formatAnswersAsText = useCallback(
    (overrideAnswers?: Record<string, QuestionState>): string => {
      const data = overrideAnswers ?? answers;
      const lines: string[] = [];

      questions.forEach((q) => {
        const answer = data[q.id];

        // Free-text question
        if (isFreeTextQuestion(q)) {
          lines.push(`${q.question}: ${answer.freeText.trim() || '（未回答）'}`);
          return;
        }

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
    },
    [answers, questions],
  );

  if (questions.length === 0) {
    return null;
  }

  // ============================================
  // Mode 1: Simple confirmation (1 question, ≤3 options, single-select)
  // ============================================
  if (isSimpleConfirmation(questions)) {
    const question = questions[0];
    const isBinaryChoice = question.options.length === 2;

    const handleSimpleSubmit = (option: string) => {
      onSubmit(`${question.question}: ${option}`);
    };

    const handleDeclineSubmit = () => {
      if (!declineOption) return;
      const text = declineText.trim();
      if (text) {
        onSubmit(`${question.question}: ${declineOption}。${text}`);
      } else {
        onSubmit(`${question.question}: ${declineOption}`);
      }
    };

    const handleSimpleClick = (option: string, index: number) => {
      // For binary choices, the second option opens a free text input
      if (isBinaryChoice && index === 1) {
        setDeclineOption(option);
        setDeclineText('');
      } else {
        handleSimpleSubmit(option);
      }
    };

    if (showOtherInput) {
      return (
        <div className="questions-panel questions-panel--simple">
          <div className="questions-panel-simple-body">
            <div className="questions-panel-simple-question">{question.question}</div>
            <div className="questions-panel-simple-other-area">
              <input
                type="text"
                className="questions-panel-simple-other-input"
                placeholder="自由に入力（任意）"
                value={simpleOtherText}
                onChange={(e) => setSimpleOtherText(e.target.value)}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && simpleOtherText.trim()) {
                    handleSimpleSubmit(simpleOtherText.trim());
                  }
                }}
              />
              <button
                className="questions-panel-simple-send"
                onClick={() => handleSimpleSubmit(simpleOtherText.trim())}
                disabled={!simpleOtherText.trim()}
              >
                送信
              </button>
            </div>
            <div className="questions-panel-simple-footer">
              <button
                className="questions-panel-simple-other-link"
                onClick={() => setShowOtherInput(false)}
              >
                選択肢に戻る
              </button>
              {onCancel && (
                <button
                  className="questions-panel-simple-other-link"
                  onClick={onCancel}
                >
                  スキップ
                </button>
              )}
            </div>
          </div>
        </div>
      );
    }

    // Decline option selected: show free text input with the option to add context
    if (declineOption) {
      return (
        <div className="questions-panel questions-panel--simple">
          <div className="questions-panel-simple-body">
            <div className="questions-panel-simple-question">{question.question}</div>
            <div className="questions-panel-decline-selected">
              <span className="questions-panel-decline-tag">{declineOption}</span>
            </div>
            <div className="questions-panel-simple-other-area">
              <input
                type="text"
                className="questions-panel-simple-other-input"
                placeholder="理由や代わりの提案があれば入力（任意）"
                value={declineText}
                onChange={(e) => setDeclineText(e.target.value)}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleDeclineSubmit();
                  }
                }}
              />
              <button
                className="questions-panel-simple-send"
                onClick={handleDeclineSubmit}
              >
                送信
              </button>
            </div>
            <div className="questions-panel-simple-footer">
              <button
                className="questions-panel-simple-other-link"
                onClick={() => setDeclineOption(null)}
              >
                選択肢に戻る
              </button>
              {onCancel && (
                <button
                  className="questions-panel-simple-other-link"
                  onClick={onCancel}
                >
                  スキップ
                </button>
              )}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="questions-panel questions-panel--simple">
        <div className="questions-panel-simple-body">
          {context && <div className="questions-panel-simple-context">{context}</div>}
          <div className="questions-panel-simple-question">{question.question}</div>
          <div className="questions-panel-simple-buttons">
            {question.options.map((option, index) => (
              <button
                key={option}
                className="questions-panel-simple-btn"
                onClick={() => handleSimpleClick(option, index)}
              >
                {option}
              </button>
            ))}
          </div>
          <div className="questions-panel-simple-footer">
            <button
              className="questions-panel-simple-other-link"
              onClick={() => setShowOtherInput(true)}
            >
              その他の回答を入力
            </button>
            {onCancel && (
              <button
                className="questions-panel-simple-other-link"
                onClick={onCancel}
              >
                スキップ
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ============================================
  // Mode 2: Free-text only (1 question, no options)
  // ============================================
  if (isFreeTextOnly(questions)) {
    const question = questions[0];
    const freeText = answers[question.id]?.freeText ?? '';

    const handleFreeTextSubmit = () => {
      if (freeText.trim()) {
        onSubmit(`${question.question}: ${freeText.trim()}`);
      }
    };

    return (
      <div className="questions-panel questions-panel--simple">
        <div className="questions-panel-simple-body">
          {context && <div className="questions-panel-simple-context">{context}</div>}
          <div className="questions-panel-simple-question">{question.question}</div>
          <div className="questions-panel-simple-other-area">
            <input
              type="text"
              className="questions-panel-simple-other-input"
              placeholder={question.placeholder ?? '入力してください'}
              value={freeText}
              onChange={(e) =>
                setAnswers((prev) => ({
                  ...prev,
                  [question.id]: { ...prev[question.id], freeText: e.target.value },
                }))
              }
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && freeText.trim()) {
                  handleFreeTextSubmit();
                }
              }}
            />
            <button
              className="questions-panel-simple-send"
              onClick={handleFreeTextSubmit}
              disabled={!freeText.trim()}
            >
              送信
            </button>
          </div>
          {onCancel && (
            <div className="questions-panel-simple-footer">
              <button
                className="questions-panel-simple-other-link"
                onClick={onCancel}
              >
                スキップ
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ============================================
  // Mode 3: Full mode (multiple questions, many options, multi-select, or mixed)
  // ============================================
  const currentQuestion = questions[currentIndex];
  const hasMultiple = questions.length > 1;
  const isLastQuestion = currentIndex === questions.length - 1;

  const handlePrev = () => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  };

  const handleNext = () => {
    setCurrentIndex((prev) => Math.min(questions.length - 1, prev + 1));
  };

  const handleOptionChange = (questionId: string, option: string, isMultiple: boolean) => {
    // Clear any pending auto-advance
    if (autoAdvanceTimer.current) {
      clearTimeout(autoAdvanceTimer.current);
      autoAdvanceTimer.current = null;
    }

    // Compute new answers outside the updater to avoid side-effects inside setState
    const current = answers[questionId];
    let newSelected: string[];

    if (isMultiple) {
      if (current.selectedOptions.includes(option)) {
        newSelected = current.selectedOptions.filter((o) => o !== option);
      } else {
        newSelected = [...current.selectedOptions, option];
      }
    } else {
      newSelected = [option];
    }

    const newAnswers = {
      ...answers,
      [questionId]: { ...current, selectedOptions: newSelected },
    };

    setAnswers(newAnswers);

    // Auto-advance for single-select (not "Other", not multi-select)
    // Timer MUST be outside setState to prevent double-fire in StrictMode
    if (!isMultiple && option !== OTHER_OPTION) {
      autoAdvanceTimer.current = setTimeout(() => {
        if (!isLastQuestion) {
          // Go to next question
          setCurrentIndex((prevIdx) => Math.min(questions.length - 1, prevIdx + 1));
        } else {
          // Last question: auto-submit only when ALL questions answered
          const allValid = questions.every((q) => {
            const a = newAnswers[q.id];
            if (isFreeTextQuestion(q)) return a.freeText.trim().length > 0;
            return a.selectedOptions.length > 0;
          });
          if (allValid) {
            onSubmit(formatAnswersAsText(newAnswers));
          }
        }
      }, 350);
    }
  };

  const handleOtherTextChange = (questionId: string, text: string) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: { ...prev[questionId], otherText: text },
    }));
  };

  const handleFreeTextChange = (questionId: string, text: string) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: { ...prev[questionId], freeText: text },
    }));
  };

  const handleSubmit = () => {
    onSubmit(formatAnswersAsText());
  };

  const isCurrentAnswered = (): boolean => {
    if (isFreeTextQuestion(currentQuestion)) {
      return answers[currentQuestion.id].freeText.trim().length > 0;
    }
    return answers[currentQuestion.id].selectedOptions.length > 0;
  };

  const hasAnyAnswer = questions.some((q) => {
    const answer = answers[q.id];
    if (isFreeTextQuestion(q)) return answer.freeText.trim().length > 0;
    return answer.selectedOptions.length > 0;
  });

  const answeredCount = questions.filter((q) => {
    const answer = answers[q.id];
    if (isFreeTextQuestion(q)) return answer.freeText.trim().length > 0;
    return answer.selectedOptions.length > 0;
  }).length;

  const unansweredCount = questions.length - answeredCount;

  const currentAnswer = answers[currentQuestion.id];
  const currentIsFreeText = isFreeTextQuestion(currentQuestion);

  return (
    <div className="questions-panel">
      <div className="questions-panel-header">
        <div className="questions-panel-title-area">
          <FaCircleQuestion className="questions-panel-icon" />
          <span className="questions-panel-badge">確認事項</span>
        </div>
        {hasMultiple && (
          <div className="questions-panel-pagination">
            <button
              className="questions-panel-nav-btn"
              onClick={handlePrev}
              disabled={currentIndex === 0}
            >
              <FaChevronLeft />
            </button>
            <div className="questions-panel-dots">
              {questions.map((q, i) => {
                const answered = isFreeTextQuestion(q)
                  ? answers[q.id].freeText.trim().length > 0
                  : answers[q.id].selectedOptions.length > 0;
                return (
                  <button
                    key={q.id}
                    className={`questions-panel-dot${i === currentIndex ? ' questions-panel-dot--active' : ''}${answered ? ' questions-panel-dot--answered' : ''}`}
                    onClick={() => setCurrentIndex(i)}
                    title={`質問${i + 1}${answered ? '（回答済み）' : ''}`}
                  />
                );
              })}
            </div>
            <button
              className="questions-panel-nav-btn"
              onClick={handleNext}
              disabled={currentIndex === questions.length - 1}
            >
              <FaChevronRight />
            </button>
          </div>
        )}
      </div>

      <div className="questions-panel-body">
        {context && currentIndex === 0 && (
          <div className="questions-panel-context">{context}</div>
        )}

        <div className="questions-panel-question">
          {hasMultiple && <span className="questions-panel-number">{currentIndex + 1}.</span>}
          {currentQuestion.question}
        </div>

        {currentIsFreeText ? (
          /* Free-text input for this question */
          <div className="questions-panel-freetext">
            <input
              type="text"
              className="questions-panel-other-input"
              placeholder={currentQuestion.placeholder ?? '入力してください'}
              value={currentAnswer.freeText}
              onChange={(e) => handleFreeTextChange(currentQuestion.id, e.target.value)}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && currentAnswer.freeText.trim()) {
                  if (!isLastQuestion) {
                    handleNext();
                  } else if (hasAnyAnswer) {
                    handleSubmit();
                  }
                }
              }}
            />
          </div>
        ) : (
          /* Options list */
          <div className="questions-panel-options">
            {currentQuestion.options.map((option) => (
              <label key={option} className="questions-panel-option">
                <input
                  type={currentQuestion.allow_multiple ? 'checkbox' : 'radio'}
                  name={`question-${currentQuestion.id}`}
                  checked={currentAnswer.selectedOptions.includes(option)}
                  onChange={() =>
                    handleOptionChange(currentQuestion.id, option, currentQuestion.allow_multiple)
                  }
                />
                <span className="questions-panel-option-text">{option}</span>
              </label>
            ))}
            <label className="questions-panel-option">
              <input
                type={currentQuestion.allow_multiple ? 'checkbox' : 'radio'}
                name={`question-${currentQuestion.id}`}
                checked={currentAnswer.selectedOptions.includes(OTHER_OPTION)}
                onChange={() =>
                  handleOptionChange(currentQuestion.id, OTHER_OPTION, currentQuestion.allow_multiple)
                }
              />
              <span className="questions-panel-option-text">{OTHER_OPTION}</span>
            </label>
            {currentAnswer.selectedOptions.includes(OTHER_OPTION) && (
              <input
                type="text"
                className="questions-panel-other-input"
                placeholder="自由に入力（任意）"
                value={currentAnswer.otherText}
                onChange={(e) => handleOtherTextChange(currentQuestion.id, e.target.value)}
                autoFocus
              />
            )}
          </div>
        )}
      </div>

      <div className="questions-panel-actions">
        {onCancel && (
          <button className="questions-panel-btn cancel" onClick={onCancel}>
            {hasAnyAnswer ? '回答を破棄してスキップ' : 'スキップ'}
          </button>
        )}
        <button
          className="questions-panel-btn submit"
          onClick={handleSubmit}
          disabled={!hasAnyAnswer}
          title={!hasAnyAnswer ? '少なくとも1つの質問に回答してください' : undefined}
        >
          {hasMultiple && !isCurrentAnswered() && !isLastQuestion
            ? '次へ'
            : unansweredCount > 0 && hasAnyAnswer
              ? `回答する（${unansweredCount}件未回答）`
              : '回答する'}
        </button>
      </div>
    </div>
  );
}
