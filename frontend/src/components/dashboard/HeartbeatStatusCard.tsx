import { useState } from 'react';
import { FaHeartPulse, FaChevronDown, FaChevronUp } from 'react-icons/fa6';
import { useHeartbeatStatus } from '../../hooks/useHeartbeatStatus';
import type { HeartbeatRiskTask } from '../../api/types';
import { toDateTime, todayInTimezone } from '../../utils/dateTime';
import './HeartbeatStatusCard.css';

interface HeartbeatStatusCardProps {
  onTaskClick?: (taskId: string) => void;
}

const riskLabels: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
};

const severityLabels: Record<string, string> = {
  critical: '危険',
  high: '高',
  medium: '中',
  low: '低',
};

function formatDeadline(item: HeartbeatRiskTask) {
  if (!item.due_date) {
    return '期限なし';
  }
  const dueDate = toDateTime(item.due_date).startOf('day');
  const today = todayInTimezone();
  const diffDays = Math.round(dueDate.diff(today, 'days').days);
  if (diffDays < 0) {
    return `期限超過${Math.abs(diffDays)}日`;
  }
  if (diffDays === 0) {
    return '期限は今日';
  }
  return `期限まであと${diffDays}日`;
}

function formatSlack(item: HeartbeatRiskTask) {
  if (item.slack_ratio === undefined || item.slack_ratio === null) {
    return '';
  }
  if (item.slack_ratio < 1) {
    return '工数不足見込み';
  }
  return `余裕${item.slack_ratio.toFixed(1)}倍`;
}

const COLLAPSED_COUNT = 3;

export function HeartbeatStatusCard({ onTaskClick }: HeartbeatStatusCardProps) {
  const { data, isLoading, isError } = useHeartbeatStatus();
  const [expanded, setExpanded] = useState(false);

  if (isLoading) {
    return (
      <div className="heartbeat-card">
        <div className="heartbeat-header">
          <div className="heartbeat-title">
            <FaHeartPulse />
            <span>見落としチェック</span>
          </div>
          <span className="risk-pill low">...</span>
        </div>
        <div className="heartbeat-meta">監視状況を確認中...</div>
      </div>
    );
  }

  if (isError || !data) {
    return null;
  }

  const riskLevel = data.risk_level;
  const topRisks = data.top_risks ?? [];
  const hasMore = topRisks.length > COLLAPSED_COUNT;
  const visibleRisks = expanded ? topRisks : topRisks.slice(0, COLLAPSED_COUNT);

  return (
    <div className={`heartbeat-card ${riskLevel}`}>
      <div className="heartbeat-header">
        <div className="heartbeat-title">
          <FaHeartPulse />
          <span>見落としチェック</span>
        </div>
        <span className={`risk-pill ${riskLevel}`}>
          リスク {riskLabels[riskLevel] ?? '低'}
        </span>
      </div>

      <div className="heartbeat-meta">
        <span>今日監視済み: {data.evaluated}件</span>
        <span>通知: {data.sent_today}/{data.limit}</span>
      </div>

      {topRisks.length === 0 ? (
        <div className="heartbeat-empty">今のところ見落としリスクは低めです。</div>
      ) : (
        <>
          <div className="heartbeat-risk-list">
            {visibleRisks.map((item) => {
              const slackText = formatSlack(item);
              return (
                <div
                  key={item.task_id}
                  className={`heartbeat-risk-item${onTaskClick ? ' clickable' : ''}`}
                  onClick={() => onTaskClick?.(item.task_id)}
                >
                  <span className={`severity-chip ${item.severity}`}>
                    {severityLabels[item.severity] ?? '中'}
                  </span>
                  <div className="risk-content">
                    <div className="risk-title">{item.title}</div>
                    <div className="risk-meta">
                      <span>{formatDeadline(item)}</span>
                      {slackText ? <span>{slackText}</span> : null}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {hasMore && (
            <button
              type="button"
              className="heartbeat-toggle"
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? (
                <>
                  <FaChevronUp />
                  <span>閉じる</span>
                </>
              ) : (
                <>
                  <FaChevronDown />
                  <span>他{topRisks.length - COLLAPSED_COUNT}件を表示</span>
                </>
              )}
            </button>
          )}
        </>
      )}
    </div>
  );
}
