export const DEFAULT_DAILY_CAPACITY_HOURS = 8;
export const DEFAULT_DAILY_BUFFER_HOURS = 1;

const parseNumber = (value: string | null, fallback: number) => {
  if (value === null) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export const getCapacitySettings = () => {
  const capacityHours = parseNumber(
    localStorage.getItem('dailyCapacityHours'),
    DEFAULT_DAILY_CAPACITY_HOURS
  );
  const bufferHours = parseNumber(
    localStorage.getItem('dailyBufferHours'),
    DEFAULT_DAILY_BUFFER_HOURS
  );

  return { capacityHours, bufferHours };
};
