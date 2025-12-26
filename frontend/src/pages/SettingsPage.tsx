import { useState, useEffect } from 'react';
import { FaCog, FaMoon, FaSun, FaBell, FaUser, FaClock } from 'react-icons/fa';
import { useTheme } from '../context/ThemeContext';
import { DEFAULT_DAILY_BUFFER_HOURS } from '../utils/capacitySettings';
import './SettingsPage.css';

export function SettingsPage() {
  const { theme, toggleTheme } = useTheme();
  const [userName, setUserName] = useState('');
  const [dailyCapacityHours, setDailyCapacityHours] = useState(8);
  const [dailyBufferHours, setDailyBufferHours] = useState(DEFAULT_DAILY_BUFFER_HOURS);
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(false);
  const [quietHoursStart, setQuietHoursStart] = useState('22:00');
  const [quietHoursEnd, setQuietHoursEnd] = useState('07:00');

  // Load settings from localStorage
  useEffect(() => {
    const savedUserName = localStorage.getItem('userName') || 'Shuhei';
    const savedDailyCapacityHours = parseFloat(localStorage.getItem('dailyCapacityHours') || '8');
    const savedDailyBufferHours = parseFloat(
      localStorage.getItem('dailyBufferHours') || String(DEFAULT_DAILY_BUFFER_HOURS)
    );
    const savedQuietHoursEnabled = localStorage.getItem('quietHoursEnabled') === 'true';
    const savedQuietHoursStart = localStorage.getItem('quietHoursStart') || '22:00';
    const savedQuietHoursEnd = localStorage.getItem('quietHoursEnd') || '07:00';

    setUserName(savedUserName);
    setDailyCapacityHours(savedDailyCapacityHours);
    setDailyBufferHours(savedDailyBufferHours);
    setQuietHoursEnabled(savedQuietHoursEnabled);
    setQuietHoursStart(savedQuietHoursStart);
    setQuietHoursEnd(savedQuietHoursEnd);
  }, []);

  const handleUserNameChange = (value: string) => {
    setUserName(value);
    localStorage.setItem('userName', value);
  };

  const handleDailyCapacityChange = (value: string) => {
    const hours = parseFloat(value);
    if (!isNaN(hours) && hours > 0 && hours <= 24) {
      setDailyCapacityHours(hours);
      localStorage.setItem('dailyCapacityHours', String(hours));
      window.dispatchEvent(new Event('capacity-settings-updated'));
    }
  };

  const handleDailyBufferChange = (value: string) => {
    const hours = parseFloat(value);
    if (!isNaN(hours) && hours >= 0 && hours <= 24) {
      setDailyBufferHours(hours);
      localStorage.setItem('dailyBufferHours', String(hours));
      window.dispatchEvent(new Event('capacity-settings-updated'));
    }
  };

  const handleQuietHoursToggle = () => {
    const newValue = !quietHoursEnabled;
    setQuietHoursEnabled(newValue);
    localStorage.setItem('quietHoursEnabled', String(newValue));
  };

  const handleQuietHoursStartChange = (value: string) => {
    setQuietHoursStart(value);
    localStorage.setItem('quietHoursStart', value);
  };

  const handleQuietHoursEndChange = (value: string) => {
    setQuietHoursEnd(value);
    localStorage.setItem('quietHoursEnd', value);
  };

  return (
    <div className="settings-page">
      <div className="page-header">
        <div className="header-left">
          <FaCog className="page-icon" />
          <h2 className="page-title">設定</h2>
        </div>
      </div>

      <div className="settings-content">
        {/* User Settings */}
        <div className="settings-section">
          <h3 className="section-title">
            <FaUser />
            ユーザー情報
          </h3>
          <div className="setting-item">
            <label htmlFor="userName" className="setting-label">
              ユーザー名
            </label>
            <input
              type="text"
              id="userName"
              value={userName}
              onChange={(e) => handleUserNameChange(e.target.value)}
              className="setting-input"
              placeholder="名前を入力"
            />
            <p className="setting-description">
              AgentCardなどで表示される名前を設定します
            </p>
          </div>
        </div>

        {/* Daily Capacity Settings */}
        <div className="settings-section">
          <h3 className="section-title">
            <FaClock />
            稼働時間
          </h3>
          <div className="setting-item">
            <label htmlFor="dailyCapacityHours" className="setting-label">
              1日の稼働時間（時間）
            </label>
            <input
              type="number"
              id="dailyCapacityHours"
              value={dailyCapacityHours}
              onChange={(e) => handleDailyCapacityChange(e.target.value)}
              className="setting-input capacity-input"
              placeholder="8"
              min="1"
              max="24"
              step="0.5"
            />
            <p className="setting-description">
              スケジューリング計算に使用する1日の作業可能時間を設定します（デフォルト: 8時間）
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
              onChange={(e) => handleDailyBufferChange(e.target.value)}
              className="setting-input capacity-input"
              placeholder="1"
              min="0"
              max="24"
              step="0.5"
            />
            <p className="setting-description">
              稼働時間から差し引いて計算します（例: 8時間 - 1時間 = 7時間）
            </p>
          </div>
        </div>

        {/* Theme Settings */}
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
                  画面の配色をダークテーマに切り替えます
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

        {/* Notification Settings */}
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
                  指定した時間帯は通知やリマインダーを無効化します
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
                    onChange={(e) => handleQuietHoursStartChange(e.target.value)}
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
                    onChange={(e) => handleQuietHoursEndChange(e.target.value)}
                    className="setting-input"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Future: Language Settings */}
        <div className="settings-section disabled">
          <h3 className="section-title">言語設定（将来対応予定）</h3>
          <div className="setting-item">
            <label className="setting-label">表示言語</label>
            <select className="setting-input" disabled>
              <option>日本語</option>
              <option>English</option>
            </select>
            <p className="setting-description">
              アプリの表示言語を変更します（現在は日本語のみ）
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
