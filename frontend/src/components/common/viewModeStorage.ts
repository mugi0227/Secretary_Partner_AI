export type ViewMode = 'normal' | 'compact';

const STORAGE_KEY = 'kanbanViewMode';

export function getStoredViewMode(): ViewMode {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === 'compact' ? 'compact' : 'normal';
}

export function setStoredViewMode(mode: ViewMode) {
  localStorage.setItem(STORAGE_KEY, mode);
}
