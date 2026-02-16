import { useEffect, useMemo, useState } from 'react';
import {
  FaTimes,
  FaMoon,
  FaSun,
  FaBell,
  FaUser,
  FaClock,
  FaCog,
  FaLink,
} from 'react-icons/fa';
import { motion } from 'framer-motion';
import { useQueryClient } from '@tanstack/react-query';
import { useTheme } from '../../context/ThemeContext';
import {
  DEFAULT_BREAK_END,
  DEFAULT_BREAK_START,
  DEFAULT_BREAK_AFTER_TASK_MINUTES,
  DEFAULT_DAILY_BUFFER_HOURS,
  DEFAULT_WEEKLY_WORK_HOURS,
  DEFAULT_WORKDAY_END,
  DEFAULT_WORKDAY_START,
  computeWorkdayCapacityHours,
  parseWeeklyWorkHours,
  type WorkBreak,
  type WorkdayHours,
} from '../../utils/capacitySettings';
import { getStoredTimezone, setStoredTimezone } from '../../utils/dateTime';
import { userStorage } from '../../utils/userStorage';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { usersApi } from '../../api/users';
import { scheduleSettingsApi } from '../../api/scheduleSettings';
import { heartbeatApi } from '../../api/heartbeat';
import type { HeartbeatIntensity } from '../../api/types';
import { ApiError } from '../../api/client';
import { authApi } from '../../api/authApi';
import { useScheduleSettings } from '../../hooks/useScheduleSettings';
import { useHeartbeatSettings } from '../../hooks/useHeartbeatSettings';
import './SettingsModal.css';

const WEEKDAY_LABELS = ['日', '月', '火', '水', '木', '金', '土'];

const createWorkday = (value: Partial<WorkdayHours>) => ({
  enabled: value.enabled ?? true,
  start: value.start ?? DEFAULT_WORKDAY_START,
  end: value.end ?? DEFAULT_WORKDAY_END,
  breaks: value.breaks ? value.breaks.map(item => ({ ...item })) : [
    { start: DEFAULT_BREAK_START, end: DEFAULT_BREAK_END },
  ],
});

const cloneWorkday = (value: WorkdayHours) => ({
  ...value,
  breaks: value.breaks.map(item => ({ ...item })),
});

const buildWeeklyWorkHours = (weekday: WorkdayHours, weekend: WorkdayHours) => (
  Array.from({ length: 7 }, (_, index) => {
    const source = (index === 0 || index === 6) ? weekend : weekday;
    return cloneWorkday(source);
  })
);

const STANDARD_WORKDAY = createWorkday({});
const OFF_WORKDAY = createWorkday({ enabled: false, breaks: [] });

const WORK_HOURS_TEMPLATES = [
  {
    id: 'weekday-standard',
    label: '平日 9:00-18:00 / 週末休み',
    hours: buildWeeklyWorkHours(STANDARD_WORKDAY, OFF_WORKDAY),
  },
  {
    id: 'weekday-late',
    label: '平日 10:00-19:00 / 週末休み',
    hours: buildWeeklyWorkHours(
      createWorkday({ start: '10:00', end: '19:00' }),
      OFF_WORKDAY
    ),
  },
  {
    id: 'weekday-short',
    label: '平日 10:00-17:00 / 週末休み',
    hours: buildWeeklyWorkHours(
      createWorkday({ start: '10:00', end: '17:00' }),
      OFF_WORKDAY
    ),
  },
  {
    id: 'everyday-standard',
    label: '毎日 9:00-18:00',
    hours: buildWeeklyWorkHours(STANDARD_WORKDAY, STANDARD_WORKDAY),
  },
];

const parseStoredNumber = (value: string | null, fallback: number) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const clampNumber = (value: number, min: number, max: number) => (
  Math.min(max, Math.max(min, value))
);

const formatCapacityHours = (hours: number) => {
  const rounded = Math.round(hours * 10) / 10;
  return `${rounded}h`;
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

const formatLinkRemaining = (expiresAt: string | null, nowTick: number): string => {
  if (!expiresAt) {
    return '';
  }
  void nowTick;
  const expiresAtMs = new Date(expiresAt).getTime();
  if (Number.isNaN(expiresAtMs)) {
    return '';
  }
  const remaining = Math.max(0, Math.floor((expiresAtMs - Date.now()) / 1000));
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

interface SettingsModalProps {
  onClose: () => void;
}

export function SettingsModal({ onClose }: SettingsModalProps) {
  const { theme, toggleTheme } = useTheme();
  const queryClient = useQueryClient();
  const { data: currentUser } = useCurrentUser();
  const { data: scheduleSettings } = useScheduleSettings();
  const { data: heartbeatSettings } = useHeartbeatSettings();
  const authMode = (import.meta.env.VITE_AUTH_MODE as string | undefined)?.toLowerCase() || '';
  const isLocalAuth = authMode === 'local';
  const [userName, setUserName] = useState('');
  const [userLastName, setUserLastName] = useState('');
  const [userFirstName, setUserFirstName] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [userTimezone, setUserTimezone] = useState(() => getStoredTimezone());
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [accountError, setAccountError] = useState<string | null>(null);
  const [accountSuccess, setAccountSuccess] = useState<string | null>(null);
  const [isUpdatingAccount, setIsUpdatingAccount] = useState(false);
  const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);
  const [dailyBufferHours, setDailyBufferHours] = useState(() =>
    parseStoredNumber(userStorage.get('dailyBufferHours'), DEFAULT_DAILY_BUFFER_HOURS)
  );
  const [breakAfterTaskMinutes, setBreakAfterTaskMinutes] = useState(() =>
    parseStoredNumber(userStorage.get('breakAfterTaskMinutes'), DEFAULT_BREAK_AFTER_TASK_MINUTES)
  );
  const [weeklyWorkHours, setWeeklyWorkHours] = useState(() =>
    parseWeeklyWorkHours(userStorage.get('weeklyWorkHours'), DEFAULT_WEEKLY_WORK_HOURS)
  );
  const [workHoursTemplateId, setWorkHoursTemplateId] = useState(
    () => userStorage.get('workHoursTemplateId') || 'custom'
  );
  const [bulkTarget, setBulkTarget] = useState<'all' | 'weekdays' | 'weekends'>('weekdays');
  const [bulkEnabled, setBulkEnabled] = useState(true);
  const [bulkStart, setBulkStart] = useState(DEFAULT_WORKDAY_START);
  const [bulkEnd, setBulkEnd] = useState(DEFAULT_WORKDAY_END);
  const [bulkBreakEnabled, setBulkBreakEnabled] = useState(true);
  const [bulkBreakStart, setBulkBreakStart] = useState(DEFAULT_BREAK_START);
  const [bulkBreakEnd, setBulkBreakEnd] = useState(DEFAULT_BREAK_END);
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(
    () => userStorage.get('quietHoursEnabled') === 'true'
  );
  const [quietHoursStart, setQuietHoursStart] = useState(
    () => userStorage.get('quietHoursStart') || '22:00'
  );
  const [quietHoursEnd, setQuietHoursEnd] = useState(
    () => userStorage.get('quietHoursEnd') || '07:00'
  );
  const [enableWeeklyMeetingReminder, setEnableWeeklyMeetingReminder] = useState(false);
  const [hasSyncedScheduleSettings, setHasSyncedScheduleSettings] = useState(false);
  const [heartbeatEnabled, setHeartbeatEnabled] = useState(true);
  const [heartbeatLimit, setHeartbeatLimit] = useState(2);
  const [heartbeatWindowStart, setHeartbeatWindowStart] = useState('09:00');
  const [heartbeatWindowEnd, setHeartbeatWindowEnd] = useState('21:00');
  const [heartbeatIntensity, setHeartbeatIntensity] = useState<HeartbeatIntensity>('standard');
  const [heartbeatDailyCapacity, setHeartbeatDailyCapacity] = useState(60);
  const [heartbeatCooldownHours, setHeartbeatCooldownHours] = useState(24);
  const [hasSyncedHeartbeatSettings, setHasSyncedHeartbeatSettings] = useState(false);
  const [nativeLinkCode, setNativeLinkCode] = useState('');
  const [nativeLinkExpiresAt, setNativeLinkExpiresAt] = useState<string | null>(null);
  const [nativeLinkError, setNativeLinkError] = useState<string | null>(null);
  const [isGeneratingNativeLink, setIsGeneratingNativeLink] = useState(false);
  const [nativeLinkCopied, setNativeLinkCopied] = useState(false);
  const [nativeLinkTick, setNativeLinkTick] = useState(() => Date.now());

  useEffect(() => {
    if (!currentUser) return;
    setUserName(currentUser.username || currentUser.display_name || '');
    setUserLastName(currentUser.last_name || '');
    setUserFirstName(currentUser.first_name || '');
    setUserEmail(currentUser.email || '');
    const resolvedTimezone = currentUser.timezone || getStoredTimezone();
    setUserTimezone(resolvedTimezone);
    setStoredTimezone(resolvedTimezone);
    setEnableWeeklyMeetingReminder(currentUser.enable_weekly_meeting_reminder ?? false);
  }, [currentUser]);

  useEffect(() => {
    if (!scheduleSettings || hasSyncedScheduleSettings) return;
    setHasSyncedScheduleSettings(true);
    setDailyBufferHours(scheduleSettings.buffer_hours);
    setBreakAfterTaskMinutes(scheduleSettings.break_after_task_minutes);
    setWeeklyWorkHours(scheduleSettings.weekly_work_hours);
    userStorage.set('dailyBufferHours', String(scheduleSettings.buffer_hours));
    userStorage.set('breakAfterTaskMinutes', String(scheduleSettings.break_after_task_minutes));
    userStorage.set('weeklyWorkHours', JSON.stringify(scheduleSettings.weekly_work_hours));
    const derivedWeekly = scheduleSettings.weekly_work_hours.map(computeWorkdayCapacityHours);
    userStorage.set('weeklyCapacityHours', JSON.stringify(derivedWeekly));
    window.dispatchEvent(new Event('capacity-settings-updated'));
  }, [scheduleSettings, hasSyncedScheduleSettings]);

  useEffect(() => {
    if (!heartbeatSettings || hasSyncedHeartbeatSettings) return;
    setHasSyncedHeartbeatSettings(true);
    setHeartbeatEnabled(heartbeatSettings.enabled);
    setHeartbeatLimit(heartbeatSettings.notification_limit_per_day);
    setHeartbeatWindowStart(heartbeatSettings.notification_window_start);
    setHeartbeatWindowEnd(heartbeatSettings.notification_window_end);
    setHeartbeatIntensity(heartbeatSettings.heartbeat_intensity);
    setHeartbeatDailyCapacity(heartbeatSettings.daily_capacity_per_task_minutes);
    setHeartbeatCooldownHours(heartbeatSettings.cooldown_hours_per_task);
  }, [heartbeatSettings, hasSyncedHeartbeatSettings]);

  useEffect(() => {
    if (!hasSyncedScheduleSettings) return;
    const handle = window.setTimeout(() => {
      scheduleSettingsApi.update({
        weekly_work_hours: weeklyWorkHours,
        buffer_hours: dailyBufferHours,
        break_after_task_minutes: breakAfterTaskMinutes,
      }).then((updated) => {
        queryClient.setQueryData(['schedule-settings'], updated);
      }).catch(() => {
        return;
      });
    }, 500);
    return () => window.clearTimeout(handle);
  }, [weeklyWorkHours, dailyBufferHours, breakAfterTaskMinutes, hasSyncedScheduleSettings, queryClient]);

  useEffect(() => {
    if (!hasSyncedHeartbeatSettings) return;
    const handle = window.setTimeout(() => {
      heartbeatApi.updateSettings({
        enabled: heartbeatEnabled,
        notification_limit_per_day: heartbeatLimit,
        notification_window_start: heartbeatWindowStart,
        notification_window_end: heartbeatWindowEnd,
        heartbeat_intensity: heartbeatIntensity,
        daily_capacity_per_task_minutes: heartbeatDailyCapacity,
        cooldown_hours_per_task: heartbeatCooldownHours,
      }).then((updated) => {
        queryClient.setQueryData(['heartbeat-settings'], updated);
      }).catch(() => {
        return;
      });
    }, 500);
    return () => window.clearTimeout(handle);
  }, [
    heartbeatEnabled,
    heartbeatLimit,
    heartbeatWindowStart,
    heartbeatWindowEnd,
    heartbeatIntensity,
    heartbeatDailyCapacity,
    heartbeatCooldownHours,
    hasSyncedHeartbeatSettings,
    queryClient,
  ]);

  useEffect(() => {
    if (!nativeLinkExpiresAt) return;
    const timer = window.setInterval(() => {
      setNativeLinkTick(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, [nativeLinkExpiresAt]);

  const handleUserNameChange = (value: string) => {
    setUserName(value);
    setAccountError(null);
    setAccountSuccess(null);
  };

  const persistWeeklyWorkHours = (next: WorkdayHours[]) => {
    setWeeklyWorkHours(next);
    userStorage.set('weeklyWorkHours', JSON.stringify(next));
    const derivedWeekly = next.map(day => computeWorkdayCapacityHours(day));
    userStorage.set('weeklyCapacityHours', JSON.stringify(derivedWeekly));
    window.dispatchEvent(new Event('capacity-settings-updated'));
  };

  const markWorkHoursCustom = () => {
    setWorkHoursTemplateId('custom');
    userStorage.set('workHoursTemplateId', 'custom');
  };

  const updateWorkday = (index: number, updater: (value: WorkdayHours) => WorkdayHours) => {
    const next = weeklyWorkHours.map((day, dayIndex) => {
      if (dayIndex !== index) return day;
      const updated = updater(day);
      return cloneWorkday(updated);
    });
    persistWeeklyWorkHours(next);
    markWorkHoursCustom();
  };

  const handleWorkdayToggle = (index: number) => {
    updateWorkday(index, day => ({ ...day, enabled: !day.enabled }));
  };

  const handleWorkdayTimeChange = (index: number, field: 'start' | 'end', value: string) => {
    updateWorkday(index, day => ({ ...day, [field]: value }));
  };

  const handleBreakTimeChange = (index: number, field: 'start' | 'end', value: string) => {
    updateWorkday(index, day => {
      const nextBreaks = day.breaks.length > 0
        ? [{ ...day.breaks[0], [field]: value } as WorkBreak]
        : [{ start: DEFAULT_BREAK_START, end: DEFAULT_BREAK_END }];
      return { ...day, breaks: nextBreaks };
    });
  };

  const handleAddBreak = (index: number) => {
    updateWorkday(index, day => {
      if (day.breaks.length > 0) return day;
      return { ...day, breaks: [{ start: DEFAULT_BREAK_START, end: DEFAULT_BREAK_END }] };
    });
  };

  const handleRemoveBreak = (index: number) => {
    updateWorkday(index, day => ({ ...day, breaks: [] }));
  };

  const handleDailyBufferChange = (value: string) => {
    const hours = parseFloat(value);
    if (!isNaN(hours) && hours >= 0 && hours <= 24) {
      setDailyBufferHours(hours);
      userStorage.set('dailyBufferHours', String(hours));
      window.dispatchEvent(new Event('capacity-settings-updated'));
    }
  };

  const handleBreakAfterTaskMinutesChange = (value: string) => {
    const minutes = Number(value);
    if (!Number.isFinite(minutes)) return;
    const clamped = Math.min(60, Math.max(0, Math.round(minutes)));
    setBreakAfterTaskMinutes(clamped);
    userStorage.set('breakAfterTaskMinutes', String(clamped));
    window.dispatchEvent(new Event('capacity-settings-updated'));
  };

  const handleWorkHoursTemplateChange = (templateId: string) => {
    setWorkHoursTemplateId(templateId);
    userStorage.set('workHoursTemplateId', templateId);
    const template = WORK_HOURS_TEMPLATES.find(item => item.id === templateId);
    if (!template) {
      return;
    }
    persistWeeklyWorkHours(template.hours);
  };

  const handleBulkApply = () => {
    const targetIndices = bulkTarget === 'all'
      ? [0, 1, 2, 3, 4, 5, 6]
      : bulkTarget === 'weekdays'
        ? [1, 2, 3, 4, 5]
        : [0, 6];
    const nextBreaks = bulkEnabled && bulkBreakEnabled
      ? [{ start: bulkBreakStart, end: bulkBreakEnd }]
      : [];
    const next = weeklyWorkHours.map((day, index) => {
      if (!targetIndices.includes(index)) return day;
      return {
        ...day,
        enabled: bulkEnabled,
        start: bulkStart,
        end: bulkEnd,
        breaks: nextBreaks.map(item => ({ ...item })),
      };
    });
    persistWeeklyWorkHours(next);
    markWorkHoursCustom();
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

  const handleHeartbeatLimitChange = (value: string) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return;
    setHeartbeatLimit(clampNumber(Math.round(parsed), 1, 3));
  };

  const handleHeartbeatDailyCapacityChange = (value: string) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return;
    setHeartbeatDailyCapacity(clampNumber(Math.round(parsed), 15, 480));
  };

  const handleHeartbeatCooldownChange = (value: string) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return;
    setHeartbeatCooldownHours(clampNumber(Math.round(parsed), 1, 168));
  };

  const handleWeeklyMeetingReminderToggle = () => {
    const newValue = !enableWeeklyMeetingReminder;
    setEnableWeeklyMeetingReminder(newValue);
    setAccountError(null);
    setAccountSuccess(null);
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
    const currentUserTimezone = currentUser?.timezone || getStoredTimezone();
    const currentEnableWeeklyMeetingReminder = currentUser?.enable_weekly_meeting_reminder ?? false;

    return (
      (nextUserName && nextUserName !== currentUserName) ||
      (nextLastName !== currentUserLastName) ||
      (nextFirstName !== currentUserFirstName) ||
      (nextEmail && nextEmail !== currentUserEmail) ||
      newPassword.trim() ||
      (userTimezone && userTimezone !== currentUserTimezone) ||
      (enableWeeklyMeetingReminder !== currentEnableWeeklyMeetingReminder)
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
      enable_weekly_meeting_reminder?: boolean;
    } = { current_password: currentPassword };

    const nextUserName = userName.trim();
    const nextFirstName = userFirstName.trim();
    const nextLastName = userLastName.trim();
    const nextEmail = userEmail.trim();
    const currentUserName = currentUser?.username || currentUser?.display_name || '';
    const currentUserFirstName = currentUser?.first_name || '';
    const currentUserLastName = currentUser?.last_name || '';
    const currentUserEmail = currentUser?.email || '';
    const currentUserTimezone = currentUser?.timezone || getStoredTimezone();
    const currentEnableWeeklyMeetingReminder = currentUser?.enable_weekly_meeting_reminder ?? false;

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
    if (enableWeeklyMeetingReminder !== currentEnableWeeklyMeetingReminder) {
      payload.enable_weekly_meeting_reminder = enableWeeklyMeetingReminder;
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

  const handleGenerateNativeLink = async () => {
    setNativeLinkError(null);
    setNativeLinkCopied(false);
    setIsGeneratingNativeLink(true);
    try {
      const response = await authApi.startNativeLink();
      setNativeLinkCode(response.code);
      setNativeLinkExpiresAt(response.expires_at);
      setNativeLinkTick(Date.now());
    } catch (error) {
      setNativeLinkError(getErrorMessage(error, '連携コードの発行に失敗しました'));
    } finally {
      setIsGeneratingNativeLink(false);
    }
  };

  const handleCopyNativeLink = async () => {
    if (!nativeLinkCode) return;
    try {
      await navigator.clipboard.writeText(nativeLinkCode);
      setNativeLinkCopied(true);
      window.setTimeout(() => setNativeLinkCopied(false), 1500);
    } catch {
      setNativeLinkCopied(false);
      setNativeLinkError('クリップボードへのコピーに失敗しました');
    }
  };

  const nativeLinkExpired = useMemo(() => {
    if (!nativeLinkExpiresAt) return false;
    void nativeLinkTick;
    const expiresAtMs = new Date(nativeLinkExpiresAt).getTime();
    if (Number.isNaN(expiresAtMs)) return false;
    return expiresAtMs <= Date.now();
  }, [nativeLinkExpiresAt, nativeLinkTick]);

  const nativeLinkRemaining = useMemo(
    () => formatLinkRemaining(nativeLinkExpiresAt, nativeLinkTick),
    [nativeLinkExpiresAt, nativeLinkTick],
  );

  const heartbeatControlsDisabled = !heartbeatEnabled;

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
                  onClick={handleGenerateNativeLink}
                  disabled={isGeneratingNativeLink}
                >
                  {isGeneratingNativeLink ? '発行中...' : 'コードを発行'}
                </button>
                <button
                  type="button"
                  className="setting-action-btn secondary"
                  onClick={handleCopyNativeLink}
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
                onChange={(event) => handleWorkHoursTemplateChange(event.target.value)}
                className="setting-select"
              >
                <option value="custom">カスタム</option>
                {WORK_HOURS_TEMPLATES.map(template => (
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
                    onChange={(event) => setBulkTarget(event.target.value as 'all' | 'weekdays' | 'weekends')}
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
                      onChange={(event) => setBulkEnabled(event.target.checked)}
                    />
                    稼働する
                  </label>
                </div>
                <div className="workhours-bulk-row">
                  <div className="workhours-time-range">
                    <input
                      type="time"
                      value={bulkStart}
                      onChange={(event) => setBulkStart(event.target.value)}
                      className="setting-input workhours-time-input"
                      disabled={!bulkEnabled}
                    />
                    <span className="workhours-separator">-</span>
                    <input
                      type="time"
                      value={bulkEnd}
                      onChange={(event) => setBulkEnd(event.target.value)}
                      className="setting-input workhours-time-input"
                      disabled={!bulkEnabled}
                    />
                  </div>
                  <label className="workhours-toggle">
                    <input
                      type="checkbox"
                      checked={bulkBreakEnabled}
                      onChange={(event) => setBulkBreakEnabled(event.target.checked)}
                      disabled={!bulkEnabled}
                    />
                    休憩
                  </label>
                  <div className="workhours-time-range">
                    <input
                      type="time"
                      value={bulkBreakStart}
                      onChange={(event) => setBulkBreakStart(event.target.value)}
                      className="setting-input workhours-time-input"
                      disabled={!bulkEnabled || !bulkBreakEnabled}
                    />
                    <span className="workhours-separator">-</span>
                    <input
                      type="time"
                      value={bulkBreakEnd}
                      onChange={(event) => setBulkBreakEnd(event.target.value)}
                      className="setting-input workhours-time-input"
                      disabled={!bulkEnabled || !bulkBreakEnabled}
                    />
                  </div>
                  <button
                    type="button"
                    className="setting-action-btn secondary workhours-apply-btn"
                    onClick={handleBulkApply}
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
                            onChange={() => handleWorkdayToggle(index)}
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
                          onChange={(event) => handleWorkdayTimeChange(index, 'start', event.target.value)}
                          className="setting-input workhours-time-input"
                          disabled={!day.enabled}
                        />
                        <span className="workhours-separator">-</span>
                        <input
                          type="time"
                          value={day.end}
                          onChange={(event) => handleWorkdayTimeChange(index, 'end', event.target.value)}
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
                                onChange={(event) => handleBreakTimeChange(index, 'start', event.target.value)}
                                className="setting-input workhours-time-input"
                                disabled={!day.enabled}
                              />
                              <span className="workhours-separator">-</span>
                              <input
                                type="time"
                                value={day.breaks[0].end}
                                onChange={(event) => handleBreakTimeChange(index, 'end', event.target.value)}
                                className="setting-input workhours-time-input"
                                disabled={!day.enabled}
                              />
                            </div>
                            <button
                              type="button"
                              className="workhours-link-btn"
                              onClick={() => handleRemoveBreak(index)}
                              disabled={!day.enabled}
                            >
                              休憩なし
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            className="workhours-link-btn"
                            onClick={() => handleAddBreak(index)}
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
                onChange={(event) => handleDailyBufferChange(event.target.value)}
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
                {'\u30bf\u30b9\u30af\u9593\u4f11\u61a9\uff08\u5206\uff09'}
              </label>
              <input
                type="number"
                id="breakAfterTaskMinutes"
                value={breakAfterTaskMinutes}
                onChange={(event) => handleBreakAfterTaskMinutesChange(event.target.value)}
                className="setting-input capacity-input"
                placeholder="5"
                min="0"
                max="60"
                step="1"
              />
              <p className="setting-description">
                {'\u30bf\u30b9\u30af\u7d42\u4e86\u3054\u3068\u306b\u6307\u5b9a\u5206\u306e\u7a7a\u767d\u3092\u5165\u308c\u307e\u3059'}
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
                  onClick={() => setHeartbeatEnabled((prev) => !prev)}
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
                onChange={(event) => handleHeartbeatLimitChange(event.target.value)}
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
                    onChange={(event) => setHeartbeatWindowStart(event.target.value)}
                    className="setting-input"
                    disabled={heartbeatControlsDisabled}
                  />
                </div>
                <span className="time-separator">〜</span>
                <div className="time-input-group">
                  <label htmlFor="heartbeatWindowEnd">終了時刻</label>
                  <input
                    type="time"
                    id="heartbeatWindowEnd"
                    value={heartbeatWindowEnd}
                    onChange={(event) => setHeartbeatWindowEnd(event.target.value)}
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
                  setHeartbeatIntensity(event.target.value as HeartbeatIntensity);
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
              <label htmlFor="heartbeatDailyCapacity" className="setting-label">
                1タスクあたりの1日作業目安（分）
              </label>
              <input
                type="number"
                id="heartbeatDailyCapacity"
                value={heartbeatDailyCapacity}
                onChange={(event) => handleHeartbeatDailyCapacityChange(event.target.value)}
                className="setting-input capacity-input"
                min="15"
                max="480"
                step="5"
                disabled={heartbeatControlsDisabled}
              />
              <p className="setting-description">
                期限までに必要な日数の目安計算に使います。
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
                onChange={(event) => handleHeartbeatCooldownChange(event.target.value)}
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
                  onClick={handleWeeklyMeetingReminderToggle}
                  disabled={!isLocalAuth || isUpdatingAccount}
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
