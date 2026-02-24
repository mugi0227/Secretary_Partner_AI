import { api } from './client';
import type { LightningLineResponse } from './types';

export const lightningLineApi = {
  get: (projectId: string, referenceDate?: string) => {
    const params = new URLSearchParams();
    if (referenceDate) {
      params.set('reference_date', referenceDate);
    }
    const suffix = params.toString();
    return api.get<LightningLineResponse>(
      `/projects/${projectId}/lightning-line${suffix ? `?${suffix}` : ''}`,
    );
  },
};
