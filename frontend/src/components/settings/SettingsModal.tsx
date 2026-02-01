import { useEffect, useState } from 'react';
import { FaTimes, FaMoon, FaSun, FaBell, FaUser, FaClock, FaCog, FaCalendarAlt } from 'react-icons/fa';
import { motion } from 'framer-motion';
import { useQueryClient } from '@tanstack/react-query';
import { useTheme } from '../../context/ThemeContext';
import { DEFAULT_DAILY_BUFFER_HOURS, DEFAULT_DAILY_CAPACITY_HOURS } from '../../utils/capacitySettings';
import { setStoredTimezone } from '../../utils/dateTime';
import { userStorage } from '../../utils/userStorage';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { usersApi } from '../../api/users';
import { ApiError } from '../../api/client';
import './SettingsModal.css';

const WEEKDAY_LABELS = ['日', '月', '火', '水', '木', '金', '土'];

const CAPACITY_TEMPLATES = [
  {
    id: 'weekdays',
    label: '平日8時間/週末0時間',
    hours: [0, 8, 8, 8, 8, 8, 0],
  },
  {
    id: 'everyday',
    label: '全曜日8時間',
    hours: [8, 8, 8, 8, 8, 8, 8],
  },
  {
    id: 'light',
    label: '平日6時間/週末0時間',
    hours: [0, 6, 6, 6, 6, 6, 0],
  },
];

const parseStoredNumber = (value: string | null, fallback: number) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const loadWeeklyCapacity = (fallback: number) => {
  const savedWeeklyCapacityHours = userStorage.get('weeklyCapacityHours');
  if (!savedWeeklyCapacityHours) {
    return Array(7).fill(fallback);
  }
  try {
    const parsed = JSON.parse(savedWeeklyCapacityHours);
    if (Array.isArray(parsed) && parsed.length === 7) {
      return parsed.map((value: unknown) => {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric : fallback;
      });
    }
  } catch {
    return Array(7).fill(fallback);
  }
  return Array(7).fill(fallback);
};

const getErrorMessage = (error: unknown, fallback: string) => {
  if (error instanceof ApiError) {
    const data = error.data as { detail?: string } | null;
    if (data?.detail) {
      return data.detail;
    }
    return `${fallback} (${error.status})`;
  }
  return fallback;
};

interface SettingsModalProps {
  onClose: () => void;
}

export function SettingsModal({ onClose }: SettingsModalProps) {
  const { theme, toggleTheme } = useTheme();
  const queryClient = useQueryClient();
  const { data: currentUser } = useCurrentUser();
  const authMode = (import.meta.env.VITE_AUTH_MODE as string | undefined)?.toLowerCase() || '';
  const isLocalAuth = authMode === 'local';
  const [userName, setUserName] = useState('');
  const [userLastName, setUserLastName] = useState('');
  const [userFirstName, setUserFirstName] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [userTimezone, setUserTimezone] = useState('Asia/Tokyo');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [accountError, setAccountError] = useState<string | null>(null);
  const [accountSuccess, setAccountSuccess] = useState<string | null>(null);
  const [isUpdatingAccount, setIsUpdatingAccount] = useState(false);
  const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);
  const [dailyCapacityHours, setDailyCapacityHours] = useState(() =>
    parseStoredNumber(userStorage.get('dailyCapacityHours'), DEFAULT_DAILY_CAPACITY_HOURS)
  );
  const [dailyBufferHours, setDailyBufferHours] = useState(() =>
    parseStoredNumber(userStorage.get('dailyBufferHours'), DEFAULT_DAILY_BUFFER_HOURS)
  );
  const [weeklyCapacityHours, setWeeklyCapacityHours] = useState(() => {
    const baseHours = parseStoredNumber(
      userStorage.get('dailyCapacityHours'),
      DEFAULT_DAILY_CAPACITY_HOURS
    );
    return loadWeeklyCapacity(baseHours);
  });
  const [capacityTemplateId, setCapacityTemplateId] = useState(
    () => userStorage.get('capacityTemplateId') || 'custom'
  );
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(
    () => userStorage.get('quietHoursEnabled') === 'true'
  );
  const [quietHoursStart, setQuietHoursStart] = useState(
    () => userStorage.get('quietHoursStart') || '22:00'
  );
  const [quietHoursEnd, setQuietHoursEnd] = useState(
    () => userStorage.get('quietHoursEnd') || '07:00'
  );
  const [calendarIntegrationEnabled, setCalendarIntegrationEnabled] = useState(
    () => userStorage.get('calendarIntegrationEnabled') === 'true'
  );

  useEffect(() => {
    if (!currentUser) return;
    setUserName(currentUser.username || currentUser.display_name || '');
    setUserLastName(currentUser.last_name || '');
    setUserFirstName(currentUser.first_name || '');
    setUserEmail(currentUser.email || '');
    setUserTimezone(currentUser.timezone || 'Asia/Tokyo');
    setStoredTimezone(currentUser.timezone || 'Asia/Tokyo');
  }, [currentUser]);

  const handleUserNameChange = (value: string) => {
    setUserName(value);
    setAccountError(null);
    setAccountSuccess(null);
  };

  const handleDailyCapacityChange = (value: string) => {
    const hours = parseFloat(value);
    if (!isNaN(hours) && hours > 0 && hours <= 24) {
      setDailyCapacityHours(hours);
      userStorage.set('dailyCapacityHours', String(hours));
      const updatedWeekly = Array(7).fill(hours);
      setWeeklyCapacityHours(updatedWeekly);
      userStorage.set('weeklyCapacityHours', JSON.stringify(updatedWeekly));
      userStorage.set('capacityTemplateId', 'custom');
      setCapacityTemplateId('custom');
      window.dispatchEvent(new Event('capacity-settings-updated'));
    }
  };

  const handleDailyBufferChange = (value: string) => {
    const hours = parseFloat(value);
    if (!isNaN(hours) && hours >= 0 && hours <= 24) {
      setDailyBufferHours(hours);
      userStorage.set('dailyBufferHours', String(hours));
      window.dispatchEvent(new Event('capacity-settings-updated'));
    }
  };

  const handleWeeklyCapacityChange = (dayIndex: number, value: string) => {
    const hours = parseFloat(value);
    if (!isNaN(hours) && hours >= 0 && hours <= 24) {
      const updated = [...weeklyCapacityHours];
      updated[dayIndex] = hours;
      setWeeklyCapacityHours(updated);
      userStorage.set('weeklyCapacityHours', JSON.stringify(updated));
      userStorage.set('capacityTemplateId', 'custom');
      setCapacityTemplateId('custom');
      window.dispatchEvent(new Event('capacity-settings-updated'));
    }
  };

  const handleCapacityTemplateChange = (templateId: string) => {
    setCapacityTemplateId(templateId);
    userStorage.set('capacityTemplateId', templateId);
    const template = CAPACITY_TEMPLATES.find(item => item.id === templateId);
    if (!template) {
      return;
    }
    setWeeklyCapacityHours(template.hours);
    userStorage.set('weeklyCapacityHours', JSON.stringify(template.hours));
    const baseHours = template.hours[1] ?? template.hours[0] ?? DEFAULT_DAILY_CAPACITY_HOURS;
    setDailyCapacityHours(baseHours);
    userStorage.set('dailyCapacityHours', String(baseHours));
    window.dispatchEvent(new Event('capacity-settings-updated'));
  };

  const handleQuietHoursToggle = () => {
    const newValue = !quietHoursEnabled;
    setQuietHoursEnabled(newValue);
    userStorage.set('quietHoursEnabled', String(newValue));
  };

  const handleQuietHoursStartChange = (value: string) => {
    setQuietHoursStart(value);
    userStorage.set('quietHoursStart', value);
  };

  const handleQuietHoursEndChange = (value: string) => {
    setQuietHoursEnd(value);
    userStorage.set('quietHoursEnd', value);
  };

  const handleCalendarIntegrationToggle = () => {
    const newValue = !calendarIntegrationEnabled;
    setCalendarIntegrationEnabled(newValue);
    userStorage.set('calendarIntegrationEnabled', String(newValue));
  };

  const hasAccountChanges = () => {
    const nextUserName = userName.trim();
    const nextFirstName = userFirstName.trim();
    const nextLastName = userLastName.trim();
    const nextEmail = userEmail.trim();
    const currentUserName = currentUser?.username || currentUser?.display_name || '';
    const currentUserFirstName = currentUser?.first_name || '';
    const currentUserLastName = currentUser?.last_name || '';
    const currentUserEmail = currentUser?.email || '';
    const currentUserTimezone = currentUser?.timezone || 'Asia/Tokyo';

    return (
      (nextUserName && nextUserName !== currentUserName) ||
      (nextLastName !== currentUserLastName) ||
      (nextFirstName !== currentUserFirstName) ||
      (nextEmail && nextEmail !== currentUserEmail) ||
      newPassword.trim() ||
      (userTimezone && userTimezone !== currentUserTimezone)
    );
  };

  const handleAccountSaveClick = () => {
    setAccountError(null);
    setAccountSuccess(null);

    if (!isLocalAuth) {
      setAccountError('ローカル認証のみ更新できます。');
      return;
    }

    if (!hasAccountChanges()) {
      setAccountError('変更点がありません。');
      return;
    }

    setShowPasswordConfirm(true);
  };

  const handlePasswordConfirmCancel = () => {
    setShowPasswordConfirm(false);
    setCurrentPassword('');
    setAccountError(null);
  };

  const handleAccountSave = async () => {
    setAccountError(null);
    setAccountSuccess(null);

    if (!currentPassword.trim()) {
      setAccountError('現在のパスワードを入力してください。');
      return;
    }

    const payload: {
      current_password: string;
      username?: string;
      email?: string;
      first_name?: string;
      last_name?: string;
      new_password?: string;
      timezone?: string;
    } = { current_password: currentPassword };

    const nextUserName = userName.trim();
    const nextFirstName = userFirstName.trim();
    const nextLastName = userLastName.trim();
    const nextEmail = userEmail.trim();
    const currentUserName = currentUser?.username || currentUser?.display_name || '';
    const currentUserFirstName = currentUser?.first_name || '';
    const currentUserLastName = currentUser?.last_name || '';
    const currentUserEmail = currentUser?.email || '';
    const currentUserTimezone = currentUser?.timezone || 'Asia/Tokyo';

    if (nextUserName && nextUserName !== currentUserName) {
      payload.username = nextUserName;
    }
    if (nextLastName !== currentUserLastName) {
      payload.last_name = nextLastName;
    }
    if (nextFirstName !== currentUserFirstName) {
      payload.first_name = nextFirstName;
    }
    if (nextEmail && nextEmail !== currentUserEmail) {
      payload.email = nextEmail;
    }
    if (newPassword.trim()) {
      payload.new_password = newPassword.trim();
    }
    if (userTimezone && userTimezone !== currentUserTimezone) {
      payload.timezone = userTimezone;
    }

    setIsUpdatingAccount(true);
    try {
      await usersApi.updateCredentials(payload);
      if (payload.timezone) {
        setStoredTimezone(payload.timezone);
      }
      setAccountSuccess('更新しました。');
      setCurrentPassword('');
      setNewPassword('');
      setShowPasswordConfirm(false);
      queryClient.invalidateQueries({ queryKey: ['current-user'] });
    } catch (error) {
      setAccountError(getErrorMessage(error, '更新に失敗しました。'));
    } finally {
      setIsUpdatingAccount(false);
    }
  };

  return (
    <div className="modal-overlay settings-modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <motion.div
        className="base-modal settings-modal"
        onClick={(event) => event.stopPropagation()}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
      >
        <div className="settings-modal-header">
          <div className="header-left">
            <FaCog className="header-icon" />
            <h2>設定</h2>
          </div>
          <button className="close-btn" onClick={onClose}>
            <FaTimes />
          </button>
        </div>

        <div className="settings-modal-content">
          <div className="settings-section">
            <h3 className="section-title">
              <FaUser />
              ユーザー設定
            </h3>
            <div className="setting-item">
              <label htmlFor="userName" className="setting-label">
                ユーザー名（ログインID）
              </label>
              <input
                type="text"
                id="userName"
                value={userName}
                onChange={(event) => handleUserNameChange(event.target.value)}
                className="setting-input"
                placeholder="ユーザー名"
                disabled={!isLocalAuth || isUpdatingAccount}
              />
              <p className="setting-description">
                登録時のユーザー名を変更します（ローカル認証のみ）。
              </p>
            </div>
            <div className="setting-item">
              <label htmlFor="userLastName" className="setting-label">
                姓（任意）
              </label>
              <input
                type="text"
                id="userLastName"
                value={userLastName}
                onChange={(event) => {
                  setUserLastName(event.target.value);
                  setAccountError(null);
                  setAccountSuccess(null);
                }}
                className="setting-input"
                placeholder="Yamada"
                disabled={!isLocalAuth || isUpdatingAccount}
              />
              <label htmlFor="userFirstName" className="setting-label">
                名（任意）
              </label>
              <input
                type="text"
                id="userFirstName"
                value={userFirstName}
                onChange={(event) => {
                  setUserFirstName(event.target.value);
                  setAccountError(null);
                  setAccountSuccess(null);
                }}
                className="setting-input"
                placeholder="Taro"
                disabled={!isLocalAuth || isUpdatingAccount}
              />
            </div>
            <div className="setting-item">
              <label htmlFor="userEmail" className="setting-label">
                メールアドレス
              </label>
              <input
                type="email"
                id="userEmail"
                value={userEmail}
                onChange={(event) => {
                  setUserEmail(event.target.value);
                  setAccountError(null);
                  setAccountSuccess(null);
                }}
                className="setting-input"
                placeholder="user@example.com"
                disabled={!isLocalAuth || isUpdatingAccount}
              />
            </div>
            <div className="setting-item">
              <label htmlFor="newPassword" className="setting-label">
                新しいパスワード（任意）
              </label>
              <input
                type="password"
                id="newPassword"
                value={newPassword}
                onChange={(event) => {
                  setNewPassword(event.target.value);
                  setAccountError(null);
                  setAccountSuccess(null);
                }}
                className="setting-input"
                placeholder="********"
                disabled={!isLocalAuth || isUpdatingAccount}
              />
            </div>
            <div className="setting-item">
              <label htmlFor="userTimezone" className="setting-label">
                タイムゾーン
              </label>
              <select
                id="userTimezone"
                value={userTimezone}
                onChange={(event) => {
                  setUserTimezone(event.target.value);
                  setAccountError(null);
                  setAccountSuccess(null);
                }}
                className="setting-select"
                disabled={!isLocalAuth || isUpdatingAccount}
              >
                <option value="Asia/Tokyo">日本 (Asia/Tokyo)</option>
                <option value="America/New_York">ニューヨーク (America/New_York)</option>
                <option value="America/Los_Angeles">ロサンゼルス (America/Los_Angeles)</option>
                <option value="Europe/London">ロンドン (Europe/London)</option>
                <option value="Europe/Paris">パリ (Europe/Paris)</option>
                <option value="Asia/Shanghai">上海 (Asia/Shanghai)</option>
                <option value="Asia/Seoul">ソウル (Asia/Seoul)</option>
                <option value="Australia/Sydney">シドニー (Australia/Sydney)</option>
              </select>
              <p className="setting-description">
                日付と時刻の表示に使用するタイムゾーンです。
              </p>
            </div>
            <div className="setting-item">
              {showPasswordConfirm ? (
                <div className="password-confirm-section">
                  <label htmlFor="currentPassword" className="setting-label">
                    現在のパスワードを入力して確認
                  </label>
                  <input
                    type="password"
                    id="currentPassword"
                    value={currentPassword}
                    onChange={(event) => {
                      setCurrentPassword(event.target.value);
                      setAccountError(null);
                    }}
                    className="setting-input"
                    placeholder="現在のパスワード"
                    disabled={isUpdatingAccount}
                    autoFocus
                  />
                  <div className="password-confirm-actions">
                    <button
                      type="button"
                      className="setting-action-btn secondary"
                      onClick={handlePasswordConfirmCancel}
                      disabled={isUpdatingAccount}
                    >
                      キャンセル
                    </button>
                    <button
                      type="button"
                      className="setting-action-btn"
                      onClick={handleAccountSave}
                      disabled={isUpdatingAccount}
                    >
                      {isUpdatingAccount ? '保存中...' : '確認して保存'}
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="setting-action-btn"
                  onClick={handleAccountSaveClick}
                  disabled={!isLocalAuth || isUpdatingAccount}
                >
                  変更を保存
                </button>
              )}
              {!isLocalAuth ? (
                <p className="setting-description">
                  OIDC/外部認証ではアカウント情報を変更できません。
                </p>
              ) : null}
              {accountError ? (
                <p className="setting-description setting-error">{accountError}</p>
              ) : null}
              {accountSuccess ? (
                <p className="setting-description setting-success">{accountSuccess}</p>
              ) : null}
            </div>
          </div>

          <div className="settings-section">
            <h3 className="section-title">
              <FaClock />
              稼働時間
            </h3>
            <div className="setting-item">
              <label htmlFor="dailyCapacityHours" className="setting-label">
                1日の稼働時間（全曜日一括）
              </label>
              <input
                type="number"
                id="dailyCapacityHours"
                value={dailyCapacityHours}
                onChange={(event) => handleDailyCapacityChange(event.target.value)}
                className="setting-input capacity-input"
                placeholder="8"
                min="1"
                max="24"
                step="0.5"
              />
              <p className="setting-description">
                まとめて入力すると全曜日に反映されます（デフォルト: 8時間）。
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
                onChange={(event) => handleDailyBufferChange(event.target.value)}
                className="setting-input capacity-input"
                placeholder="1"
                min="0"
                max="24"
                step="0.5"
              />
              <p className="setting-description">
                稼働時間から差し引いて計算します（例: 8時間 - 1時間 = 7時間）。
              </p>
            </div>
            <div className="setting-item">
              <label htmlFor="capacityTemplate" className="setting-label">
                稼働時間テンプレート
              </label>
              <select
                id="capacityTemplate"
                value={capacityTemplateId}
                onChange={(event) => handleCapacityTemplateChange(event.target.value)}
                className="setting-select"
              >
                <option value="custom">カスタム</option>
                {CAPACITY_TEMPLATES.map(template => (
                  <option key={template.id} value={template.id}>
                    {template.label}
                  </option>
                ))}
              </select>
              <p className="setting-description">
                用途に合わせた稼働時間をまとめて設定できます。
              </p>
            </div>
            <div className="setting-item">
              <span className="setting-label">曜日別の稼働時間</span>
              <div className="weekday-grid">
                {WEEKDAY_LABELS.map((label, index) => (
                  <div
                    key={label}
                    className={`weekday-item ${index === 0 ? 'sun' : ''} ${
                      index === 6 ? 'sat' : ''
                    }`}
                  >
                    <span className="weekday-label">{label}</span>
                    <input
                      type="number"
                      value={weeklyCapacityHours[index] ?? 0}
                      onChange={(event) => handleWeeklyCapacityChange(index, event.target.value)}
                      className="setting-input capacity-input weekday-input"
                      min="0"
                      max="24"
                      step="0.5"
                    />
                  </div>
                ))}
              </div>
              <p className="setting-description">
                0時間にすると、その曜日はスケジュール対象外になります。
              </p>
            </div>
          </div>

          <div className="settings-section">
            <h3 className="section-title">
              {theme === 'dark' ? <FaMoon /> : <FaSun />}
              テーマ
            </h3>
            <div className="setting-item">
              <div className="setting-row">
                <div className="setting-label-group">
                  <span className="setting-label">ダークモード</span>
                  <p className="setting-description">
                    画面の配色をダークテーマに切り替えます。
                  </p>
                </div>
                <button
                  className={`toggle-btn ${theme === 'dark' ? 'active' : ''}`}
                  onClick={toggleTheme}
                >
                  <span className="toggle-slider"></span>
                </button>
              </div>
            </div>
          </div>


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
                  onClick={handleQuietHoursToggle}
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
                      onChange={(event) => handleQuietHoursStartChange(event.target.value)}
                      className="setting-input"
                    />
                  </div>
                  <span className="time-separator">〜</span>
                  <div className="time-input-group">
                    <label htmlFor="quietHoursEnd">終了時刻</label>
                    <input
                      type="time"
                      id="quietHoursEnd"
                      value={quietHoursEnd}
                      onChange={(event) => handleQuietHoursEndChange(event.target.value)}
                      className="setting-input"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="settings-section">
            <h3 className="section-title">
              <FaCalendarAlt />
              外部カレンダー連携
            </h3>
            <div className="setting-item">
              <div className="setting-row">
                <div className="setting-label-group">
                  <span className="setting-label">外部カレンダー連携済み</span>
                  <p className="setting-description">
                    ONにすると「今週の会議情報が追加されていません」の通知が非表示になります。
                    将来的にGoogle Calendar / Outlook連携を実装予定です。
                  </p>
                </div>
                <button
                  className={`toggle-btn ${calendarIntegrationEnabled ? 'active' : ''}`}
                  onClick={handleCalendarIntegrationToggle}
                >
                  <span className="toggle-slider"></span>
                </button>
              </div>
            </div>
          </div>

          <div className="settings-section disabled">
            <h3 className="section-title">言語設定（対応予定）</h3>
            <div className="setting-item">
              <label className="setting-label">表示言語</label>
              <select className="setting-input" disabled>
                <option>日本語</option>
                <option>English</option>
              </select>
              <p className="setting-description">
                アプリの表示言語を変更します（現在は日本語のみ）。
              </p>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
