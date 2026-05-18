import { useCallback, useState } from 'react';
import type { CallBackProps } from 'react-joyride';
import { ACTIONS, EVENTS, STATUS } from 'react-joyride';
import { tourStorage } from '../utils/tourStorage';
import { tourRegistry } from '../tours';
import type { TourStep } from '../tours/types';

interface UsePageTourReturn {
  run: boolean;
  steps: TourStep[];
  stepIndex: number;
  handleCallback: (data: CallBackProps) => void;
  startTour: () => void;
}

export function usePageTour(pageKey: string): UsePageTourReturn {
  const steps = tourRegistry[pageKey] ?? [];
  const [run, setRun] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);

  const handleCallback = useCallback(
    (data: CallBackProps) => {
      const { status, action, index, type } = data;

      // Tour finished or skipped
      if (status === STATUS.FINISHED || status === STATUS.SKIPPED) {
        setRun(false);
        setStepIndex(0);
        tourStorage.markCompleted(pageKey);
        return;
      }

      // Advance/retreat steps
      if (type === EVENTS.STEP_AFTER || type === EVENTS.TARGET_NOT_FOUND) {
        setStepIndex(index + (action === ACTIONS.PREV ? -1 : 1));
      }
    },
    [pageKey],
  );

  // Replay function for help button
  const startTour = useCallback(() => {
    setStepIndex(0);
    setRun(true);
  }, []);

  return { run, steps, stepIndex, handleCallback, startTour };
}
