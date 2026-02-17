import { FaClock } from 'react-icons/fa';
import type { WorkdayHours } from '../../../utils/capacitySettings';
import { computeWorkdayCapacityHours, DEFAULT_WEEKLY_WORK_HOURS } from '../../../utils/capacitySettings';

const WEEKDAY_LABELS = ['日', '月', '火', '水', '木', '金', '土'];

const formatCapacityHours = (hours: number) => {
  const rounded = Math.round(hours * 10) / 10;
  return `${rounded}h`;
};

interface WorkHoursTemplate {
  id: string;
  label: string;
  hours: WorkdayHours[];
}

interface WorkHoursTabProps {
  // Template
  workHoursTemplateId: string;
  workHoursTemplates: WorkHoursTemplate[];
  onWorkHoursTemplateChange: (templateId: string) => void;
  // Bulk
  bulkTarget: 'all' | 'weekdays' | 'weekends';
  bulkEnabled: boolean;
  bulkStart: string;
  bulkEnd: string;
  bulkBreakEnabled: boolean;
  bulkBreakStart: string;
  bulkBreakEnd: string;
  onBulkTargetChange: (value: 'all' | 'weekdays' | 'weekends') => void;
  onBulkEnabledChange: (value: boolean) => void;
  onBulkStartChange: (value: string) => void;
  onBulkEndChange: (value: string) => void;
  onBulkBreakEnabledChange: (value: boolean) => void;
  onBulkBreakStartChange: (value: string) => void;
  onBulkBreakEndChange: (value: string) => void;
  onBulkApply: () => void;
  // Weekly work hours
  weeklyWorkHours: WorkdayHours[];
  onWorkdayToggle: (index: number) => void;
  onWorkdayTimeChange: (index: number, field: 'start' | 'end', value: string) => void;
  onBreakTimeChange: (index: number, field: 'start' | 'end', value: string) => void;
  onAddBreak: (index: number) => void;
  onRemoveBreak: (index: number) => void;
  // Buffer & break
  dailyBufferHours: number;
  breakAfterTaskMinutes: number;
  onDailyBufferChange: (value: string) => void;
  onBreakAfterTaskMinutesChange: (value: string) => void;
  // Daily capacity (moved from notifications, optional)
  dailyCapacityEnabled: boolean;
  heartbeatDailyCapacity: number;
  onDailyCapacityEnabledChange: (value: boolean) => void;
  onHeartbeatDailyCapacityChange: (value: string) => void;
}

export function WorkHoursTab({
  workHoursTemplateId,
  workHoursTemplates,
  onWorkHoursTemplateChange,
  bulkTarget,
  bulkEnabled,
  bulkStart,
  bulkEnd,
  bulkBreakEnabled,
  bulkBreakStart,
  bulkBreakEnd,
  onBulkTargetChange,
  onBulkEnabledChange,
  onBulkStartChange,
  onBulkEndChange,
  onBulkBreakEnabledChange,
  onBulkBreakStartChange,
  onBulkBreakEndChange,
  onBulkApply,
  weeklyWorkHours,
  onWorkdayToggle,
  onWorkdayTimeChange,
  onBreakTimeChange,
  onAddBreak,
  onRemoveBreak,
  dailyBufferHours,
  breakAfterTaskMinutes,
  onDailyBufferChange,
  onBreakAfterTaskMinutesChange,
  dailyCapacityEnabled,
  heartbeatDailyCapacity,
  onDailyCapacityEnabledChange,
  onHeartbeatDailyCapacityChange,
}: WorkHoursTabProps) {
  return (
    <div className="settings-section">
      <h3 className="section-title">
        <FaClock />
        勤務時間
      </h3>
      <div className="setting-item">
        <label htmlFor="workHoursTemplate" className="setting-label">
          勤務時間テンプレート
        </label>
        <select
          id="workHoursTemplate"
          value={workHoursTemplateId}
          onChange={(event) => onWorkHoursTemplateChange(event.target.value)}
          className="setting-select"
        >
          <option value="custom">カスタム</option>
          {workHoursTemplates.map(template => (
            <option key={template.id} value={template.id}>
              {template.label}
            </option>
          ))}
        </select>
        <p className="setting-description">
          開始/終了と休憩をまとめて反映します。
        </p>
      </div>
      <div className="setting-item">
        <span className="setting-label">まとめて設定</span>
        <div className="workhours-bulk">
          <div className="workhours-bulk-row">
            <select
              value={bulkTarget}
              onChange={(event) => onBulkTargetChange(event.target.value as 'all' | 'weekdays' | 'weekends')}
              className="setting-select workhours-select"
            >
              <option value="all">全曜日</option>
              <option value="weekdays">平日</option>
              <option value="weekends">週末</option>
            </select>
            <label className="workhours-toggle">
              <input
                type="checkbox"
                checked={bulkEnabled}
                onChange={(event) => onBulkEnabledChange(event.target.checked)}
              />
              稼働する
            </label>
          </div>
          <div className="workhours-bulk-row">
            <div className="workhours-time-range">
              <input
                type="time"
                value={bulkStart}
                onChange={(event) => onBulkStartChange(event.target.value)}
                className="setting-input workhours-time-input"
                disabled={!bulkEnabled}
              />
              <span className="workhours-separator">-</span>
              <input
                type="time"
                value={bulkEnd}
                onChange={(event) => onBulkEndChange(event.target.value)}
                className="setting-input workhours-time-input"
                disabled={!bulkEnabled}
              />
            </div>
            <label className="workhours-toggle">
              <input
                type="checkbox"
                checked={bulkBreakEnabled}
                onChange={(event) => onBulkBreakEnabledChange(event.target.checked)}
                disabled={!bulkEnabled}
              />
              休憩
            </label>
            <div className="workhours-time-range">
              <input
                type="time"
                value={bulkBreakStart}
                onChange={(event) => onBulkBreakStartChange(event.target.value)}
                className="setting-input workhours-time-input"
                disabled={!bulkEnabled || !bulkBreakEnabled}
              />
              <span className="workhours-separator">-</span>
              <input
                type="time"
                value={bulkBreakEnd}
                onChange={(event) => onBulkBreakEndChange(event.target.value)}
                className="setting-input workhours-time-input"
                disabled={!bulkEnabled || !bulkBreakEnabled}
              />
            </div>
            <button
              type="button"
              className="setting-action-btn secondary workhours-apply-btn"
              onClick={onBulkApply}
            >
              適用
            </button>
          </div>
        </div>
        <p className="setting-description">
          曜日まとめて開始/終了と休憩を設定できます。
        </p>
      </div>
      <div className="setting-item">
        <span className="setting-label">曜日別の勤務時間</span>
        <div className="workhours-grid">
          {WEEKDAY_LABELS.map((label, index) => {
            const day = weeklyWorkHours[index] ?? DEFAULT_WEEKLY_WORK_HOURS[index];
            const capacityHours = computeWorkdayCapacityHours(day);
            return (
              <div
                key={label}
                className={`weekday-item workhours-item ${index === 0 ? 'sun' : ''} ${
                  index === 6 ? 'sat' : ''
                }`}
              >
                <div className="workhours-day-row">
                  <label className="workhours-toggle">
                    <input
                      type="checkbox"
                      checked={day.enabled}
                      onChange={() => onWorkdayToggle(index)}
                    />
                    <span className="weekday-label">{label}</span>
                  </label>
                  <span className="workhours-capacity">
                    {day.enabled ? formatCapacityHours(capacityHours) : '休み'}
                  </span>
                </div>
                <div className="workhours-time-row">
                  <input
                    type="time"
                    value={day.start}
                    onChange={(event) => onWorkdayTimeChange(index, 'start', event.target.value)}
                    className="setting-input workhours-time-input"
                    disabled={!day.enabled}
                  />
                  <span className="workhours-separator">-</span>
                  <input
                    type="time"
                    value={day.end}
                    onChange={(event) => onWorkdayTimeChange(index, 'end', event.target.value)}
                    className="setting-input workhours-time-input"
                    disabled={!day.enabled}
                  />
                </div>
                <div className="workhours-break-row">
                  {day.breaks.length > 0 ? (
                    <>
                      <div className="workhours-time-range">
                        <input
                          type="time"
                          value={day.breaks[0].start}
                          onChange={(event) => onBreakTimeChange(index, 'start', event.target.value)}
                          className="setting-input workhours-time-input"
                          disabled={!day.enabled}
                        />
                        <span className="workhours-separator">-</span>
                        <input
                          type="time"
                          value={day.breaks[0].end}
                          onChange={(event) => onBreakTimeChange(index, 'end', event.target.value)}
                          className="setting-input workhours-time-input"
                          disabled={!day.enabled}
                        />
                      </div>
                      <button
                        type="button"
                        className="workhours-link-btn"
                        onClick={() => onRemoveBreak(index)}
                        disabled={!day.enabled}
                      >
                        休憩なし
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="workhours-link-btn"
                      onClick={() => onAddBreak(index)}
                      disabled={!day.enabled}
                    >
                      休憩を追加
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <p className="setting-description">
          1日の稼働時間は開始/終了と休憩から自動計算されます。
        </p>
      </div>
      <div className="setting-item">
        <label htmlFor="dailyBufferHours" className="setting-label">
          バッファ時間（時間）
        </label>
        <input
          type="number"
          id="dailyBufferHours"
          value={dailyBufferHours}
          onChange={(event) => onDailyBufferChange(event.target.value)}
          className="setting-input capacity-input"
          placeholder="1"
          min="0"
          max="24"
          step="0.5"
        />
        <p className="setting-description">
          稼働時間から差し引いて計算します。
        </p>
      </div>
      <div className="setting-item">
        <label htmlFor="breakAfterTaskMinutes" className="setting-label">
          タスク間休憩（分）
        </label>
        <input
          type="number"
          id="breakAfterTaskMinutes"
          value={breakAfterTaskMinutes}
          onChange={(event) => onBreakAfterTaskMinutesChange(event.target.value)}
          className="setting-input capacity-input"
          placeholder="5"
          min="0"
          max="60"
          step="1"
        />
        <p className="setting-description">
          タスク終了ごとに指定分の空白を入れます。
        </p>
      </div>

      <div className="setting-item">
        <div className="setting-row">
          <div className="setting-label-group">
            <span className="setting-label">1タスクあたりの1日作業目安</span>
            <p className="setting-description">
              有効にすると、期限までに必要な日数の目安計算に使います。
            </p>
          </div>
          <button
            className={`toggle-btn ${dailyCapacityEnabled ? 'active' : ''}`}
            onClick={() => onDailyCapacityEnabledChange(!dailyCapacityEnabled)}
          >
            <span className="toggle-slider"></span>
          </button>
        </div>
        {dailyCapacityEnabled && (
          <div style={{ marginTop: '0.75rem' }}>
            <label htmlFor="heartbeatDailyCapacity" className="setting-label">
              目安時間（分）
            </label>
            <input
              type="number"
              id="heartbeatDailyCapacity"
              value={heartbeatDailyCapacity}
              onChange={(event) => onHeartbeatDailyCapacityChange(event.target.value)}
              className="setting-input capacity-input"
              min="15"
              max="480"
              step="5"
            />
          </div>
        )}
      </div>
    </div>
  );
}
