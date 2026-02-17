import { FaLink } from 'react-icons/fa';

interface IntegrationTabProps {
  nativeLinkCode: string;
  nativeLinkExpiresAt: string | null;
  nativeLinkExpired: boolean;
  nativeLinkRemaining: string;
  nativeLinkError: string | null;
  nativeLinkCopied: boolean;
  isGeneratingNativeLink: boolean;
  onGenerateNativeLink: () => void;
  onCopyNativeLink: () => void;
}

export function IntegrationTab({
  nativeLinkCode,
  nativeLinkExpiresAt,
  nativeLinkExpired,
  nativeLinkRemaining,
  nativeLinkError,
  nativeLinkCopied,
  isGeneratingNativeLink,
  onGenerateNativeLink,
  onCopyNativeLink,
}: IntegrationTabProps) {
  return (
    <div className="settings-section">
      <h3 className="section-title">
        <FaLink />
        ネイティブ連携
      </h3>
      <div className="setting-item">
        <span className="setting-label">ワンタイム連携コード</span>
        <p className="setting-description">
          Windowsネイティブアプリ側に貼り付けて連携します。コードは120秒で失効します。
        </p>
        <div className="native-link-actions-row">
          <button
            type="button"
            className="setting-action-btn"
            onClick={onGenerateNativeLink}
            disabled={isGeneratingNativeLink}
          >
            {isGeneratingNativeLink ? '発行中...' : 'コードを発行'}
          </button>
          <button
            type="button"
            className="setting-action-btn secondary"
            onClick={onCopyNativeLink}
            disabled={!nativeLinkCode || nativeLinkExpired}
          >
            {nativeLinkCopied ? 'コピー済み' : 'コピー'}
          </button>
        </div>
        <div className={`native-link-code-box ${nativeLinkExpired ? 'expired' : ''}`}>
          {nativeLinkCode || '未発行'}
        </div>
        {nativeLinkExpiresAt && !nativeLinkExpired ? (
          <p className="setting-description">
            期限まで {nativeLinkRemaining}
          </p>
        ) : null}
        {nativeLinkExpiresAt && nativeLinkExpired ? (
          <p className="setting-description">
            コードの期限が切れました。再発行してください。
          </p>
        ) : null}
        {nativeLinkError ? (
          <p className="setting-description setting-error">{nativeLinkError}</p>
        ) : null}
      </div>
    </div>
  );
}
