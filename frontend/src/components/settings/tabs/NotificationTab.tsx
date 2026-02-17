import { FaBell } from 'react-icons/fa';
import type { HeartbeatIntensity } from '../../../api/types';

interface NotificationTabProps {
  // Quiet hours
  quietHoursEnabled: boolean;
  quietHoursStart: string;
  quietHoursEnd: string;
  onQuietHoursToggle: () => void;
  onQuietHoursStartChange: (value: string) => void;
  onQuietHoursEndChange: (value: string) => void;
  // Heartbeat
  heartbeatEnabled: boolean;
  heartbeatLimit: number;
  heartbeatWindowStart: string;
  heartbeatWindowEnd: string;
  heartbeatIntensity: HeartbeatIntensity;
  heartbeatCooldownHours: number;
  onHeartbeatEnabledToggle: () => void;
  onHeartbeatLimitChange: (value: string) => void;
  onHeartbeatWindowStartChange: (value: string) => void;
  onHeartbeatWindowEndChange: (value: string) => void;
  onHeartbeatIntensityChange: (value: HeartbeatIntensity) => void;
  onHeartbeatCooldownChange: (value: string) => void;
  // Weekly meeting reminder
  enableWeeklyMeetingReminder: boolean;
  onWeeklyMeetingReminderToggle: () => void;
  isLocalAuth: boolean;
  isUpdatingAccount: boolean;
}

export function NotificationTab({
  quietHoursEnabled,
  quietHoursStart,
  quietHoursEnd,
  onQuietHoursToggle,
  onQuietHoursStartChange,
  onQuietHoursEndChange,
  heartbeatEnabled,
  heartbeatLimit,
  heartbeatWindowStart,
  heartbeatWindowEnd,
  heartbeatIntensity,
  heartbeatCooldownHours,
  onHeartbeatEnabledToggle,
  onHeartbeatLimitChange,
  onHeartbeatWindowStartChange,
  onHeartbeatWindowEndChange,
  onHeartbeatIntensityChange,
  onHeartbeatCooldownChange,
  enableWeeklyMeetingReminder,
  onWeeklyMeetingReminderToggle,
  isLocalAuth,
  isUpdatingAccount,
}: NotificationTabProps) {
  const heartbeatControlsDisabled = !heartbeatEnabled;

  return (
    <div className="settings-section">
      <h3 className="section-title">
        <FaBell />
        通知設定
      </h3>
      <div className="setting-item">
        <div className="setting-row">
          <div className="setting-label-group">
            <span className="setting-label">Quiet Hours（静かな時間）</span>
            <p className="setting-description">
              指定した時間帯は通知やリマインダーを無効化します。
            </p>
          </div>
          <button
            className={`toggle-btn ${quietHoursEnabled ? 'active' : ''}`}
            onClick={onQuietHoursToggle}
          >
            <span className="toggle-slider"></span>
          </button>
        </div>

        {quietHoursEnabled && (
          <div className="quiet-hours-config">
            <div className="time-input-group">
              <label htmlFor="quietHoursStart">開始時刻</label>
              <input
                type="time"
                id="quietHoursStart"
                value={quietHoursStart}
                onChange={(event) => onQuietHoursStartChange(event.target.value)}
                className="setting-input"
              />
            </div>
            <span className="time-separator">{'\u301C'}</span>
            <div className="time-input-group">
              <label htmlFor="quietHoursEnd">終了時刻</label>
              <input
                type="time"
                id="quietHoursEnd"
                value={quietHoursEnd}
                onChange={(event) => onQuietHoursEndChange(event.target.value)}
                className="setting-input"
              />
            </div>
          </div>
        )}
      </div>

      <div className="setting-item">
        <div className="setting-row">
          <div className="setting-label-group">
            <span className="setting-label">Heartbeat（やさしい確認）</span>
            <p className="setting-description">
              タスクの見落としを防ぐため、やさしく声かけします。
            </p>
          </div>
          <button
            className={`toggle-btn ${heartbeatEnabled ? 'active' : ''}`}
            onClick={onHeartbeatEnabledToggle}
          >
            <span className="toggle-slider"></span>
          </button>
        </div>
      </div>

      <div className="setting-item">
        <label htmlFor="heartbeatLimit" className="setting-label">
          1日あたりの通知上限
        </label>
        <select
          id="heartbeatLimit"
          value={heartbeatLimit}
          onChange={(event) => onHeartbeatLimitChange(event.target.value)}
          className="setting-select"
          disabled={heartbeatControlsDisabled}
        >
          <option value={1}>1件</option>
          <option value={2}>2件</option>
          <option value={3}>3件</option>
        </select>
        <p className="setting-description">
          1〜3件の範囲で調整できます。
        </p>
      </div>

      <div className="setting-item">
        <span className="setting-label">通知時間帯</span>
        <div className="quiet-hours-config">
          <div className="time-input-group">
            <label htmlFor="heartbeatWindowStart">開始時刻</label>
            <input
              type="time"
              id="heartbeatWindowStart"
              value={heartbeatWindowStart}
              onChange={(event) => onHeartbeatWindowStartChange(event.target.value)}
              className="setting-input"
              disabled={heartbeatControlsDisabled}
            />
          </div>
          <span className="time-separator">{'\u301C'}</span>
          <div className="time-input-group">
            <label htmlFor="heartbeatWindowEnd">終了時刻</label>
            <input
              type="time"
              id="heartbeatWindowEnd"
              value={heartbeatWindowEnd}
              onChange={(event) => onHeartbeatWindowEndChange(event.target.value)}
              className="setting-input"
              disabled={heartbeatControlsDisabled}
            />
          </div>
        </div>
      </div>

      <div className="setting-item">
        <label htmlFor="heartbeatIntensity" className="setting-label">
          声かけの強さ
        </label>
        <select
          id="heartbeatIntensity"
          value={heartbeatIntensity}
          onChange={(event) => {
            onHeartbeatIntensityChange(event.target.value as HeartbeatIntensity);
          }}
          className="setting-select"
          disabled={heartbeatControlsDisabled}
        >
          <option value="gentle">やさしめ</option>
          <option value="standard">ふつう</option>
          <option value="firm">しっかり</option>
        </select>
        <p className="setting-description">
          伝え方のトーンを調整できます。
        </p>
      </div>

      <div className="setting-item">
        <label htmlFor="heartbeatCooldown" className="setting-label">
          同じタスクへの通知間隔（時間）
        </label>
        <input
          type="number"
          id="heartbeatCooldown"
          value={heartbeatCooldownHours}
          onChange={(event) => onHeartbeatCooldownChange(event.target.value)}
          className="setting-input capacity-input"
          min="1"
          max="168"
          step="1"
          disabled={heartbeatControlsDisabled}
        />
        <p className="setting-description">
          同じタスクへの声かけ頻度を抑えます。
        </p>
      </div>

      <div className="setting-item">
        <div className="setting-row">
          <div className="setting-label-group">
            <span className="setting-label">週次会議登録リマインダー</span>
            <p className="setting-description">
              毎週月曜日に、会議情報の登録を促すタスクを自動作成します。
            </p>
          </div>
          <button
            className={`toggle-btn ${enableWeeklyMeetingReminder ? 'active' : ''}`}
            onClick={onWeeklyMeetingReminderToggle}
            disabled={!isLocalAuth || isUpdatingAccount}
          >
            <span className="toggle-slider"></span>
          </button>
        </div>
      </div>
    </div>
  );
}
