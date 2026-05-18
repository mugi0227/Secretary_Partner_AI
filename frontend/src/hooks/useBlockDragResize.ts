/**
 * Custom hook for drag-to-move and resize-to-extend schedule blocks.
 *
 * Uses native pointer events for precise grid snapping (15-min intervals)
 * and cross-day column detection via data-day-key attributes.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

const SNAP_MINUTES = 15;
const DRAG_THRESHOLD_PX = 4;

export type InteractionType = 'drag' | 'resize';

export interface GhostPosition {
  dayKey: string;
  startMinutes: number;
  endMinutes: number;
}

export interface BlockInfo {
  id: string;
  taskId: string;
  dayKey: string;
  startMinutes: number;
  endMinutes: number;
  kind: 'meeting' | 'auto';
}

interface DragState {
  block: BlockInfo;
  type: InteractionType;
  startClientX: number;
  startClientY: number;
  /** Offset from pointer Y to block top in minutes */
  offsetMinutes: number;
  hasMoved: boolean;
}

export interface UseBlockDragResizeOptions {
  /** Pixels per hour on the grid */
  hourHeight: number;
  /** First visible hour (e.g. 8 = 08:00) */
  startBoundHour: number;
  /** Last visible hour (e.g. 20 = 20:00) */
  endBoundHour: number;
  /** Called when a block is dropped at a new position */
  onDrop: (
    block: BlockInfo,
    target: GhostPosition,
    type: InteractionType,
  ) => void;
  /** Called when a block is clicked (pointerdown+up without drag) */
  onClick?: (block: BlockInfo) => void;
}

export function useBlockDragResize({
  hourHeight,
  startBoundHour,
  endBoundHour,
  onDrop,
  onClick,
}: UseBlockDragResizeOptions) {
  const [ghost, setGhost] = useState<GhostPosition | null>(null);
  const [activeBlockId, setActiveBlockId] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<DragState | null>(null);
  // Use a ref for onClick to avoid stale closures in document event listeners
  const onClickRef = useRef(onClick);
  const onDropRef = useRef(onDrop);

  useEffect(() => {
    onClickRef.current = onClick;
  }, [onClick]);

  useEffect(() => {
    onDropRef.current = onDrop;
  }, [onDrop]);

  const snapToGrid = (minutes: number) =>
    Math.round(minutes / SNAP_MINUTES) * SNAP_MINUTES;

  const clientYToMinutes = useCallback(
    (clientY: number, columnEl: Element) => {
      const rect = columnEl.getBoundingClientRect();
      const offsetY = clientY - rect.top;
      const rawMinutes = startBoundHour * 60 + (offsetY / hourHeight) * 60;
      return snapToGrid(rawMinutes);
    },
    [hourHeight, startBoundHour],
  );

  /** Find the day column element under the pointer */
  const findDayColumn = useCallback((clientX: number, clientY: number) => {
    const elements = document.elementsFromPoint(clientX, clientY);
    for (const el of elements) {
      if (el instanceof HTMLElement && el.dataset.dayKey) {
        return el;
      }
    }
    return null;
  }, []);

  const handlePointerMove = useCallback(
    (e: PointerEvent) => {
      const state = dragRef.current;
      if (!state) return;

      const dx = e.clientX - state.startClientX;
      const dy = e.clientY - state.startClientY;

      // Check drag threshold before starting visual feedback
      if (!state.hasMoved) {
        if (Math.abs(dx) < DRAG_THRESHOLD_PX && Math.abs(dy) < DRAG_THRESHOLD_PX) {
          return;
        }
        state.hasMoved = true;
        setIsDragging(true);
      }

      const column = findDayColumn(e.clientX, e.clientY);
      if (!column) return;

      const dayKey = (column as HTMLElement).dataset.dayKey!;
      const minuteAtPointer = clientYToMinutes(e.clientY, column);
      const startBound = startBoundHour * 60;
      const endBound = endBoundHour * 60;
      const blockDuration = state.block.endMinutes - state.block.startMinutes;

      let startMinutes: number;
      let endMinutes: number;

      if (state.type === 'drag') {
        startMinutes = snapToGrid(minuteAtPointer - state.offsetMinutes);
        endMinutes = startMinutes + blockDuration;
        // Clamp within visible bounds
        if (startMinutes < startBound) {
          startMinutes = startBound;
          endMinutes = startMinutes + blockDuration;
        }
        if (endMinutes > endBound) {
          endMinutes = endBound;
          startMinutes = endMinutes - blockDuration;
        }
      } else {
        // resize: only change end time
        startMinutes = state.block.startMinutes;
        endMinutes = Math.max(
          startMinutes + SNAP_MINUTES,
          snapToGrid(minuteAtPointer),
        );
        if (endMinutes > endBound) {
          endMinutes = endBound;
        }
      }

      setGhost({ dayKey, startMinutes, endMinutes });
    },
    [clientYToMinutes, findDayColumn, startBoundHour, endBoundHour],
  );

  const handlePointerUp = useCallback(
    (e: PointerEvent) => {
      const state = dragRef.current;
      document.removeEventListener('pointermove', handlePointerMove);
      dragRef.current = null;
      setActiveBlockId(null);
      setIsDragging(false);
      setGhost(null);

      if (!state) return;
      if (!state.hasMoved) {
        // No drag occurred — treat as a click
        onClickRef.current?.(state.block);
        return;
      }

      const column = findDayColumn(e.clientX, e.clientY);
      if (!column) return;

      const dayKey = (column as HTMLElement).dataset.dayKey!;
      const minuteAtPointer = clientYToMinutes(e.clientY, column);
      const startBound = startBoundHour * 60;
      const endBound = endBoundHour * 60;
      const blockDuration = state.block.endMinutes - state.block.startMinutes;

      let startMinutes: number;
      let endMinutes: number;

      if (state.type === 'drag') {
        startMinutes = snapToGrid(minuteAtPointer - state.offsetMinutes);
        endMinutes = startMinutes + blockDuration;
        if (startMinutes < startBound) {
          startMinutes = startBound;
          endMinutes = startMinutes + blockDuration;
        }
        if (endMinutes > endBound) {
          endMinutes = endBound;
          startMinutes = endMinutes - blockDuration;
        }
      } else {
        startMinutes = state.block.startMinutes;
        endMinutes = Math.max(
          startMinutes + SNAP_MINUTES,
          snapToGrid(minuteAtPointer),
        );
        if (endMinutes > endBound) endMinutes = endBound;
      }

      // Only fire if position actually changed
      const moved =
        dayKey !== state.block.dayKey ||
        startMinutes !== state.block.startMinutes ||
        endMinutes !== state.block.endMinutes;

      if (moved) {
        onDropRef.current(state.block, { dayKey, startMinutes, endMinutes }, state.type);
      }
    },
    [
      handlePointerMove,
      findDayColumn,
      clientYToMinutes,
      startBoundHour,
      endBoundHour,
    ],
  );

  /** Attach to a block element's onPointerDown for dragging */
  const startInteraction = useCallback(
    (e: React.PointerEvent, block: BlockInfo, type: InteractionType) => {
      e.preventDefault();
      e.stopPropagation();

      const column = findDayColumn(e.clientX, e.clientY);
      const offsetMinutes = type === 'drag' && column
        ? clientYToMinutes(e.clientY, column) - block.startMinutes
        : 0;

      dragRef.current = {
        block,
        type,
        startClientX: e.clientX,
        startClientY: e.clientY,
        offsetMinutes,
        hasMoved: false,
      };

      setActiveBlockId(block.id);
      setIsDragging(false);
      document.addEventListener('pointermove', handlePointerMove);
      document.addEventListener('pointerup', handlePointerUp, { once: true });
    },
    [findDayColumn, clientYToMinutes, handlePointerMove, handlePointerUp],
  );

  return {
    ghost,
    activeBlockId,
    isDragging,
    startInteraction,
  };
}
