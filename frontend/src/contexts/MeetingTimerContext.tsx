/**
 * Context for managing active meeting session state across pages
 */
/* eslint-disable react-refresh/only-export-components */

import { createContext, useContext, useState, useCallback, useEffect, useRef, ReactNode } from 'react';
import type { MeetingSession } from '../types/session';
import type { MeetingAgendaItem } from '../api/types';

interface MeetingTimerState {
    session: MeetingSession | null;
    agendaItems: MeetingAgendaItem[];
    meetingTitle: string;
    meetingDate: string;
    taskId: string | null;
    projectId: string | null;
    elapsedSeconds: number;
    isPaused: boolean;
    isWidgetVisible: boolean;
    isModalVisible: boolean;
}

interface StoredTimerState {
    session: MeetingSession;
    agendaItems: MeetingAgendaItem[];
    meetingTitle: string;
    meetingDate: string;
    taskId: string | null;
    projectId: string | null;
    elapsedSeconds: number;
    isPaused: boolean;
    isWidgetVisible: boolean;
    savedAt: number; // timestamp when saved
}

const STORAGE_KEY = 'meeting-timer-state';

function loadStoredState(): Partial<MeetingTimerState> | null {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (!stored) return null;

        const parsed: StoredTimerState = JSON.parse(stored);

        // If the session is not IN_PROGRESS anymore, don't restore
        if (parsed.session.status !== 'IN_PROGRESS') {
            localStorage.removeItem(STORAGE_KEY);
            return null;
        }

        // Calculate elapsed time since save if timer was running
        const now = Date.now();
        const elapsedSinceSave = Math.floor((now - parsed.savedAt) / 1000);
        const adjustedElapsed = parsed.isPaused
            ? parsed.elapsedSeconds
            : parsed.elapsedSeconds + elapsedSinceSave;

        return {
            session: parsed.session,
            agendaItems: parsed.agendaItems,
            meetingTitle: parsed.meetingTitle,
            meetingDate: parsed.meetingDate,
            taskId: parsed.taskId,
            projectId: parsed.projectId,
            elapsedSeconds: adjustedElapsed,
            isPaused: parsed.isPaused,
            isWidgetVisible: parsed.isWidgetVisible,
            isModalVisible: false, // Don't restore modal visibility
        };
    } catch {
        return null;
    }
}

function saveState(state: MeetingTimerState): void {
    try {
        if (!state.session || state.session.status !== 'IN_PROGRESS') {
            localStorage.removeItem(STORAGE_KEY);
            return;
        }

        const toStore: StoredTimerState = {
            session: state.session,
            agendaItems: state.agendaItems,
            meetingTitle: state.meetingTitle,
            meetingDate: state.meetingDate,
            taskId: state.taskId,
            projectId: state.projectId,
            elapsedSeconds: state.elapsedSeconds,
            isPaused: state.isPaused,
            isWidgetVisible: state.isWidgetVisible,
            savedAt: Date.now(),
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore));
    } catch {
        // Ignore storage errors
    }
}

function clearStoredState(): void {
    try {
        localStorage.removeItem(STORAGE_KEY);
    } catch {
        // Ignore storage errors
    }
}

interface MeetingTimerContextType extends MeetingTimerState {
    startTimer: (
        session: MeetingSession,
        agendaItems: MeetingAgendaItem[],
        meetingTitle: string,
        meetingDate: string,
        taskId: string,
        projectId: string
    ) => void;
    stopTimer: () => void;
    pauseTimer: () => void;
    resumeTimer: () => void;
    resetTimer: () => void;
    updateSession: (session: MeetingSession) => void;
    updateAgendaItems: (agendaItems: MeetingAgendaItem[]) => void;
    showWidget: () => void;
    hideWidget: () => void;
    showModal: () => void;
    hideModal: () => void;
}

const MeetingTimerContext = createContext<MeetingTimerContextType | null>(null);

const defaultState: MeetingTimerState = {
    session: null,
    agendaItems: [],
    meetingTitle: '',
    meetingDate: '',
    taskId: null,
    projectId: null,
    elapsedSeconds: 0,
    isPaused: false,
    isWidgetVisible: false,
    isModalVisible: false,
};

function getInitialState(): MeetingTimerState {
    const stored = loadStoredState();
    if (stored && stored.session) {
        return {
            ...defaultState,
            ...stored,
        } as MeetingTimerState;
    }
    return defaultState;
}

export function MeetingTimerProvider({ children }: { children: ReactNode }) {
    const [state, setState] = useState<MeetingTimerState>(getInitialState);

    const intervalRef = useRef<NodeJS.Timeout | null>(null);

    // Save state to localStorage whenever it changes
    useEffect(() => {
        saveState(state);
    }, [state]);

    // Timer effect
    useEffect(() => {
        if (state.session && state.session.status === 'IN_PROGRESS' && !state.isPaused) {
            intervalRef.current = setInterval(() => {
                setState(prev => ({
                    ...prev,
                    elapsedSeconds: prev.elapsedSeconds + 1,
                }));
            }, 1000);
        }

        return () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
            }
        };
    }, [state.session, state.isPaused]);

    const startTimer = useCallback((
        session: MeetingSession,
        agendaItems: MeetingAgendaItem[],
        meetingTitle: string,
        meetingDate: string,
        taskId: string,
        projectId: string
    ) => {
        setState({
            session,
            agendaItems,
            meetingTitle,
            meetingDate,
            taskId,
            projectId,
            elapsedSeconds: 0,
            isPaused: false,
            isWidgetVisible: false,
            isModalVisible: true,
        });
    }, []);

    const stopTimer = useCallback(() => {
        if (intervalRef.current) {
            clearInterval(intervalRef.current);
        }
        clearStoredState();
        setState({
            session: null,
            agendaItems: [],
            meetingTitle: '',
            meetingDate: '',
            taskId: null,
            projectId: null,
            elapsedSeconds: 0,
            isPaused: false,
            isWidgetVisible: false,
            isModalVisible: false,
        });
    }, []);

    const pauseTimer = useCallback(() => {
        setState(prev => ({ ...prev, isPaused: true }));
    }, []);

    const resumeTimer = useCallback(() => {
        setState(prev => ({ ...prev, isPaused: false }));
    }, []);

    const resetTimer = useCallback(() => {
        setState(prev => ({ ...prev, elapsedSeconds: 0 }));
    }, []);

    const updateSession = useCallback((session: MeetingSession) => {
        setState(prev => ({
            ...prev,
            session,
            // Reset timer when agenda changes
            elapsedSeconds: prev.session?.current_agenda_index !== session.current_agenda_index ? 0 : prev.elapsedSeconds,
        }));
    }, []);

    const showWidget = useCallback(() => {
        setState(prev => ({ ...prev, isWidgetVisible: true }));
    }, []);

    const hideWidget = useCallback(() => {
        setState(prev => ({ ...prev, isWidgetVisible: false }));
    }, []);

    const showModal = useCallback(() => {
        setState(prev => ({ ...prev, isModalVisible: true, isWidgetVisible: false }));
    }, []);

    const hideModal = useCallback(() => {
        setState(prev => ({ ...prev, isModalVisible: false, isWidgetVisible: true }));
    }, []);

    const updateAgendaItems = useCallback((agendaItems: MeetingAgendaItem[]) => {
        setState(prev => ({ ...prev, agendaItems }));
    }, []);

    return (
        <MeetingTimerContext.Provider
            value={{
                ...state,
                startTimer,
                stopTimer,
                pauseTimer,
                resumeTimer,
                resetTimer,
                updateSession,
                updateAgendaItems,
                showWidget,
                hideWidget,
                showModal,
                hideModal,
            }}
        >
            {children}
        </MeetingTimerContext.Provider>
    );
}

export function useMeetingTimer() {
    const context = useContext(MeetingTimerContext);
    if (!context) {
        throw new Error('useMeetingTimer must be used within a MeetingTimerProvider');
    }
    return context;
}
