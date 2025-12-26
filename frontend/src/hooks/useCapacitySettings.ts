import { useEffect, useState } from 'react';
import { getCapacitySettings } from '../utils/capacitySettings';

export function useCapacitySettings() {
  const [settings, setSettings] = useState(getCapacitySettings());

  useEffect(() => {
    const handleUpdate = () => setSettings(getCapacitySettings());
    window.addEventListener('storage', handleUpdate);
    window.addEventListener('capacity-settings-updated', handleUpdate);
    return () => {
      window.removeEventListener('storage', handleUpdate);
      window.removeEventListener('capacity-settings-updated', handleUpdate);
    };
  }, []);

  return settings;
}
