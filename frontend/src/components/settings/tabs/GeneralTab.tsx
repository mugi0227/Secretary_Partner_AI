import { FaUser, FaMoon, FaSun } from 'react-icons/fa';

interface GeneralTabProps {
  // User account
  userName: string;
  userLastName: string;
  userFirstName: string;
  userEmail: string;
  userTimezone: string;
  newPassword: string;
  currentPassword: string;
  accountError: string | null;
  accountSuccess: string | null;
  isUpdatingAccount: boolean;
  showPasswordConfirm: boolean;
  isLocalAuth: boolean;
  onUserNameChange: (value: string) => void;
  onUserLastNameChange: (value: string) => void;
  onUserFirstNameChange: (value: string) => void;
  onUserEmailChange: (value: string) => void;
  onUserTimezoneChange: (value: string) => void;
  onNewPasswordChange: (value: string) => void;
  onCurrentPasswordChange: (value: string) => void;
  onAccountSaveClick: () => void;
  onPasswordConfirmCancel: () => void;
  onAccountSave: () => void;
  // Theme
  theme: string;
  onToggleTheme: () => void;
}

export function GeneralTab({
  userName,
  userLastName,
  userFirstName,
  userEmail,
  userTimezone,
  newPassword,
  currentPassword,
  accountError,
  accountSuccess,
  isUpdatingAccount,
  showPasswordConfirm,
  isLocalAuth,
  onUserNameChange,
  onUserLastNameChange,
  onUserFirstNameChange,
  onUserEmailChange,
  onUserTimezoneChange,
  onNewPasswordChange,
  onCurrentPasswordChange,
  onAccountSaveClick,
  onPasswordConfirmCancel,
  onAccountSave,
  theme,
  onToggleTheme,
}: GeneralTabProps) {
  return (
    <>
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
            onChange={(event) => onUserNameChange(event.target.value)}
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
            onChange={(event) => onUserLastNameChange(event.target.value)}
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
            onChange={(event) => onUserFirstNameChange(event.target.value)}
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
            onChange={(event) => onUserEmailChange(event.target.value)}
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
            onChange={(event) => onNewPasswordChange(event.target.value)}
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
            onChange={(event) => onUserTimezoneChange(event.target.value)}
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
                onChange={(event) => onCurrentPasswordChange(event.target.value)}
                className="setting-input"
                placeholder="現在のパスワード"
                disabled={isUpdatingAccount}
                autoFocus
              />
              <div className="password-confirm-actions">
                <button
                  type="button"
                  className="setting-action-btn secondary"
                  onClick={onPasswordConfirmCancel}
                  disabled={isUpdatingAccount}
                >
                  キャンセル
                </button>
                <button
                  type="button"
                  className="setting-action-btn"
                  onClick={onAccountSave}
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
              onClick={onAccountSaveClick}
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
              onClick={onToggleTheme}
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
    </>
  );
}
