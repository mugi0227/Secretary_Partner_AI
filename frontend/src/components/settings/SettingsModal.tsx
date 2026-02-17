import { useEffect, useMemo, useState } from 'react';
import {
  FaTimes,
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
import { GeneralTab } from './tabs/GeneralTab';
import { WorkHoursTab } from './tabs/WorkHoursTab';
import { NotificationTab } from './tabs/NotificationTab';
import { IntegrationTab } from './tabs/IntegrationTab';
import './SettingsModal.css';

type SettingsTab = 'general' | 'workHours' | 'notifications' | 'integration';

const SETTINGS_TABS: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
  { id: 'general', label: '一般', icon: <FaUser /> },
  { id: 'workHours', label: '勤務時間', icon: <FaClock /> },
  { id: 'notifications', label: '通知設定', icon: <FaBell /> },
  { id: 'integration', label: '連携', icon: <FaLink /> },
];

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

  // Tab state
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');

  // Account state
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

  // Work hours state
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

  // Notification state
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

  // Heartbeat state
  const [heartbeatEnabled, setHeartbeatEnabled] = useState(true);
  const [heartbeatLimit, setHeartbeatLimit] = useState(2);
  const [heartbeatWindowStart, setHeartbeatWindowStart] = useState('09:00');
  const [heartbeatWindowEnd, setHeartbeatWindowEnd] = useState('21:00');
  const [heartbeatIntensity, setHeartbeatIntensity] = useState<HeartbeatIntensity>('standard');
  const [heartbeatDailyCapacity, setHeartbeatDailyCapacity] = useState(60);
  const [heartbeatCooldownHours, setHeartbeatCooldownHours] = useState(24);
  const [dailyCapacityEnabled, setDailyCapacityEnabled] = useState(
    () => userStorage.get('dailyCapacityEnabled') === 'true'
  );

  // Sync flags
  const [hasSyncedScheduleSettings, setHasSyncedScheduleSettings] = useState(false);
  const [hasSyncedHeartbeatSettings, setHasSyncedHeartbeatSettings] = useState(false);

  // Native link state
  const [nativeLinkCode, setNativeLinkCode] = useState('');
  const [nativeLinkExpiresAt, setNativeLinkExpiresAt] = useState<string | null>(null);
  const [nativeLinkError, setNativeLinkError] = useState<string | null>(null);
  const [isGeneratingNativeLink, setIsGeneratingNativeLink] = useState(false);
  const [nativeLinkCopied, setNativeLinkCopied] = useState(false);
  const [nativeLinkTick, setNativeLinkTick] = useState(() => Date.now());

  // --- Sync effects ---

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

  // --- Auto-save effects ---

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

  // --- Handlers: Account ---

  const clearAccountMessages = () => {
    setAccountError(null);
    setAccountSuccess(null);
  };

  const handleUserNameChange = (value: string) => {
    setUserName(value);
    clearAccountMessages();
  };

  const handleUserLastNameChange = (value: string) => {
    setUserLastName(value);
    clearAccountMessages();
  };

  const handleUserFirstNameChange = (value: string) => {
    setUserFirstName(value);
    clearAccountMessages();
  };

  const handleUserEmailChange = (value: string) => {
    setUserEmail(value);
    clearAccountMessages();
  };

  const handleUserTimezoneChange = (value: string) => {
    setUserTimezone(value);
    clearAccountMessages();
  };

  const handleNewPasswordChange = (value: string) => {
    setNewPassword(value);
    clearAccountMessages();
  };

  const handleCurrentPasswordChange = (value: string) => {
    setCurrentPassword(value);
    setAccountError(null);
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
    clearAccountMessages();
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
    clearAccountMessages();
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

    if (nextUserName && nextUserName !== currentUserName) payload.username = nextUserName;
    if (nextLastName !== currentUserLastName) payload.last_name = nextLastName;
    if (nextFirstName !== currentUserFirstName) payload.first_name = nextFirstName;
    if (nextEmail && nextEmail !== currentUserEmail) payload.email = nextEmail;
    if (newPassword.trim()) payload.new_password = newPassword.trim();
    if (userTimezone && userTimezone !== currentUserTimezone) payload.timezone = userTimezone;
    if (enableWeeklyMeetingReminder !== currentEnableWeeklyMeetingReminder) {
      payload.enable_weekly_meeting_reminder = enableWeeklyMeetingReminder;
    }

    setIsUpdatingAccount(true);
    try {
      await usersApi.updateCredentials(payload);
      if (payload.timezone) setStoredTimezone(payload.timezone);
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

  // --- Handlers: Work Hours ---

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
      return cloneWorkday(updater(day));
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
    if (!template) return;
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

  const handleDailyCapacityEnabledChange = (value: boolean) => {
    setDailyCapacityEnabled(value);
    userStorage.set('dailyCapacityEnabled', String(value));
  };

  // --- Handlers: Notifications ---

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
    clearAccountMessages();
  };

  // --- Handlers: Native link ---

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

  // --- Render ---

  const renderTabContent = () => {
    switch (activeTab) {
      case 'general':
        return (
          <GeneralTab
            userName={userName}
            userLastName={userLastName}
            userFirstName={userFirstName}
            userEmail={userEmail}
            userTimezone={userTimezone}
            newPassword={newPassword}
            currentPassword={currentPassword}
            accountError={accountError}
            accountSuccess={accountSuccess}
            isUpdatingAccount={isUpdatingAccount}
            showPasswordConfirm={showPasswordConfirm}
            isLocalAuth={isLocalAuth}
            onUserNameChange={handleUserNameChange}
            onUserLastNameChange={handleUserLastNameChange}
            onUserFirstNameChange={handleUserFirstNameChange}
            onUserEmailChange={handleUserEmailChange}
            onUserTimezoneChange={handleUserTimezoneChange}
            onNewPasswordChange={handleNewPasswordChange}
            onCurrentPasswordChange={handleCurrentPasswordChange}
            onAccountSaveClick={handleAccountSaveClick}
            onPasswordConfirmCancel={handlePasswordConfirmCancel}
            onAccountSave={handleAccountSave}
            theme={theme}
            onToggleTheme={toggleTheme}
          />
        );
      case 'workHours':
        return (
          <WorkHoursTab
            workHoursTemplateId={workHoursTemplateId}
            workHoursTemplates={WORK_HOURS_TEMPLATES}
            onWorkHoursTemplateChange={handleWorkHoursTemplateChange}
            bulkTarget={bulkTarget}
            bulkEnabled={bulkEnabled}
            bulkStart={bulkStart}
            bulkEnd={bulkEnd}
            bulkBreakEnabled={bulkBreakEnabled}
            bulkBreakStart={bulkBreakStart}
            bulkBreakEnd={bulkBreakEnd}
            onBulkTargetChange={setBulkTarget}
            onBulkEnabledChange={setBulkEnabled}
            onBulkStartChange={setBulkStart}
            onBulkEndChange={setBulkEnd}
            onBulkBreakEnabledChange={setBulkBreakEnabled}
            onBulkBreakStartChange={setBulkBreakStart}
            onBulkBreakEndChange={setBulkBreakEnd}
            onBulkApply={handleBulkApply}
            weeklyWorkHours={weeklyWorkHours}
            onWorkdayToggle={handleWorkdayToggle}
            onWorkdayTimeChange={handleWorkdayTimeChange}
            onBreakTimeChange={handleBreakTimeChange}
            onAddBreak={handleAddBreak}
            onRemoveBreak={handleRemoveBreak}
            dailyBufferHours={dailyBufferHours}
            breakAfterTaskMinutes={breakAfterTaskMinutes}
            onDailyBufferChange={handleDailyBufferChange}
            onBreakAfterTaskMinutesChange={handleBreakAfterTaskMinutesChange}
            dailyCapacityEnabled={dailyCapacityEnabled}
            heartbeatDailyCapacity={heartbeatDailyCapacity}
            onDailyCapacityEnabledChange={handleDailyCapacityEnabledChange}
            onHeartbeatDailyCapacityChange={handleHeartbeatDailyCapacityChange}
          />
        );
      case 'notifications':
        return (
          <NotificationTab
            quietHoursEnabled={quietHoursEnabled}
            quietHoursStart={quietHoursStart}
            quietHoursEnd={quietHoursEnd}
            onQuietHoursToggle={handleQuietHoursToggle}
            onQuietHoursStartChange={handleQuietHoursStartChange}
            onQuietHoursEndChange={handleQuietHoursEndChange}
            heartbeatEnabled={heartbeatEnabled}
            heartbeatLimit={heartbeatLimit}
            heartbeatWindowStart={heartbeatWindowStart}
            heartbeatWindowEnd={heartbeatWindowEnd}
            heartbeatIntensity={heartbeatIntensity}
            heartbeatCooldownHours={heartbeatCooldownHours}
            onHeartbeatEnabledToggle={() => setHeartbeatEnabled(prev => !prev)}
            onHeartbeatLimitChange={handleHeartbeatLimitChange}
            onHeartbeatWindowStartChange={setHeartbeatWindowStart}
            onHeartbeatWindowEndChange={setHeartbeatWindowEnd}
            onHeartbeatIntensityChange={setHeartbeatIntensity}
            onHeartbeatCooldownChange={handleHeartbeatCooldownChange}
            enableWeeklyMeetingReminder={enableWeeklyMeetingReminder}
            onWeeklyMeetingReminderToggle={handleWeeklyMeetingReminderToggle}
            isLocalAuth={isLocalAuth}
            isUpdatingAccount={isUpdatingAccount}
          />
        );
      case 'integration':
        return (
          <IntegrationTab
            nativeLinkCode={nativeLinkCode}
            nativeLinkExpiresAt={nativeLinkExpiresAt}
            nativeLinkExpired={nativeLinkExpired}
            nativeLinkRemaining={nativeLinkRemaining}
            nativeLinkError={nativeLinkError}
            nativeLinkCopied={nativeLinkCopied}
            isGeneratingNativeLink={isGeneratingNativeLink}
            onGenerateNativeLink={handleGenerateNativeLink}
            onCopyNativeLink={handleCopyNativeLink}
          />
        );
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

        <div className="settings-modal-body">
          <nav className="settings-sidebar">
            {SETTINGS_TABS.map(tab => (
              <button
                key={tab.id}
                className={`settings-sidebar-item ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                <span className="settings-sidebar-icon">{tab.icon}</span>
                <span className="settings-sidebar-label">{tab.label}</span>
              </button>
            ))}
          </nav>

          <div className="settings-modal-content">
            {renderTabContent()}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
