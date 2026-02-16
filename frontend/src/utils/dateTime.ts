import { DateTime } from 'luxon';
import { userStorage } from './userStorage';

const TIMEZONE_STORAGE_KEY = 'userTimezone';
const DEFAULT_TIMEZONE = 'UTC';

export const getBrowserTimezone = () => {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (!timezone) return DEFAULT_TIMEZONE;
  try {
    Intl.DateTimeFormat('en-US', { timeZone: timezone }).format(new Date());
    return timezone;
  } catch {
    return DEFAULT_TIMEZONE;
  }
};

const isValidTimezone = (timezone: string) => {
  if (!timezone) return false;
  try {
    Intl.DateTimeFormat('en-US', { timeZone: timezone }).format(new Date());
    return true;
  } catch {
    return false;
  }
};

const isDateOnly = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value);
const hasTimezoneInfo = (value: string) => /([zZ]|[+-]\d{2}:?\d{2})$/.test(value);

export const getStoredTimezone = () => {
  const stored = userStorage.get(TIMEZONE_STORAGE_KEY);
  if (stored && isValidTimezone(stored)) {
    return stored;
  }
  return getBrowserTimezone();
};

export const setStoredTimezone = (timezone: string) => {
  if (!timezone || !isValidTimezone(timezone)) return;
  userStorage.set(TIMEZONE_STORAGE_KEY, timezone);
};

export const toDateTime = (value: string | Date, timezone = getStoredTimezone()) => {
  if (value instanceof Date) {
    return DateTime.fromJSDate(value).setZone(timezone);
  }
  if (isDateOnly(value)) {
    return DateTime.fromISO(value, { zone: timezone });
  }
  if (hasTimezoneInfo(value)) {
    return DateTime.fromISO(value, { setZone: true }).setZone(timezone);
  }
  // バックエンドからのタイムゾーン情報なしの日時はユーザーのローカル時間として解釈
  // （定例会議の開始時刻などはローカル時間で保存されているため）
  return DateTime.fromISO(value, { zone: timezone });
};

export const toDateKey = (value: string | Date, timezone?: string) => {
  const dt = toDateTime(value, timezone ?? getStoredTimezone());
  return dt.isValid ? dt.toISODate() ?? '' : '';
};

export const formatDate = (
  value: string | Date,
  options: Intl.DateTimeFormatOptions,
  timezone?: string,
  locale = 'ja-JP',
) => {
  const dt = toDateTime(value, timezone ?? getStoredTimezone());
  if (!dt.isValid) {
    return typeof value === 'string' ? value : '';
  }
  return dt.setLocale(locale).toLocaleString(options);
};

export const startOfDay = (value: string | Date, timezone?: string) => {
  return toDateTime(value, timezone ?? getStoredTimezone()).startOf('day');
};

export const todayInTimezone = (timezone?: string) => {
  return DateTime.now().setZone(timezone ?? getStoredTimezone()).startOf('day');
};

export const nowInTimezone = (timezone?: string) => {
  return DateTime.now().setZone(timezone ?? getStoredTimezone());
};

export const toDateTimeLocalValue = (value?: string | null, timezone?: string) => {
  if (!value) return '';
  const dt = toDateTime(value, timezone ?? getStoredTimezone());
  return dt.isValid ? dt.toFormat("yyyy-LL-dd'T'HH:mm") : '';
};

export const toUtcIsoString = (value?: string | null, timezone?: string) => {
  if (!value) return undefined;
  const dt = DateTime.fromISO(value, { zone: timezone ?? getStoredTimezone() });
  return dt.isValid ? dt.toUTC().toISO() ?? undefined : undefined;
};

/** Calculate deadline status for a task based on due_date relative to today */
export const getDeadlineStatus = (
  dueDateStr: string | undefined | null,
  status: string,
  timezone?: string,
): 'overdue' | 'approaching' | null => {
  if (!dueDateStr || status === 'DONE') return null;
  const tz = timezone ?? getStoredTimezone();
  const dueDate = toDateTime(dueDateStr, tz).startOf('day');
  if (!dueDate.isValid) return null;
  const today = todayInTimezone(tz);
  const diffDays = dueDate.diff(today, 'days').days;
  if (diffDays < 0) return 'overdue';
  if (diffDays <= 3) return 'approaching';
  return null;
};
