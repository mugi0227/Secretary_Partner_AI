import { useState } from 'react';
import { useCaptures } from '../../hooks/useCaptures';
import { useTasks } from '../../hooks/useTasks';
import { TaskFormModal } from '../tasks/TaskFormModal';
import './InboxWidget.css';
import type { TaskCreate } from '../../api/types';

export function InboxWidget() {
    const { unprocessedCaptures: allCaptures, isLoading, error, deleteCapture, processCapture, analyzeCapture, isAnalyzing } = useCaptures();
    const { createTask } = useTasks();

    const [isFormOpen, setIsFormOpen] = useState(false);
    const [analyzedTask, setAnalyzedTask] = useState<TaskCreate | undefined>(undefined);
    const [analyzingId, setAnalyzingId] = useState<string | null>(null);
    const [processedSourceId, setProcessedSourceId] = useState<string | null>(null);

    const handleAnalyze = async (captureId: string) => {
        setAnalyzingId(captureId);
        try {
            const result = await analyzeCapture(captureId);
            setAnalyzedTask(result);
            setProcessedSourceId(captureId);
            setIsFormOpen(true);
        } catch (e) {
            console.error(e);
            alert('解析に失敗しました');
        } finally {
            setAnalyzingId(null);
        }
    };

    const handleSubmit = async (data: TaskCreate) => {
        await createTask({
            ...data,
            source_capture_id: processedSourceId || undefined
        });

        // Mark capture as processed after successful task creation
        if (processedSourceId) {
            processCapture(processedSourceId);
        }

        setIsFormOpen(false);
        setAnalyzedTask(undefined);
        setProcessedSourceId(null);
    };

    // Filter out regular chat messages, only show Extension captures
    const unprocessedCaptures = allCaptures.filter(c => {
        if (c.content_type === 'IMAGE') return true;
        if (c.content_type === 'TEXT' && c.raw_text) {
            try {
                const data = JSON.parse(c.raw_text);
                return data.type === 'EXT_CAPTURE';
            } catch {
                return false;
            }
        }
        return false;
    });

    if (isLoading) {
        return <div className="inbox-widget loading">Loading inbox...</div>;
    }

    if (error) {
        return <div className="inbox-widget error">Failed to load inbox</div>;
    }

    if (unprocessedCaptures.length === 0) {
        // Don't show anything if empty (Clean Dashboard Philosophy)
        return null;
    }

    return (
        <div className="inbox-widget">
            <div className="widget-header">
                <h3>Inbox (Unprocessed)</h3>
                <span className="badge">{unprocessedCaptures.length}</span>
            </div>

            <div className="capture-list">
                {unprocessedCaptures.map((capture) => (
                    <div key={capture.id} className="capture-item">
                        <div className="capture-icon">
                            {capture.content_type === 'IMAGE' ? '📸' : '📝'}
                        </div>

                        <div className="capture-content">
                            <div className="capture-meta">
                                {new Date(capture.created_at).toLocaleString('ja-JP', {
                                    month: 'numeric',
                                    day: 'numeric',
                                    hour: '2-digit',
                                    minute: '2-digit'
                                })}
                            </div>
                            <div className="capture-text">
                                {getDisplayText(capture)}
                            </div>
                        </div>

                        <div className="capture-actions">
                            <button
                                className="action-btn process"
                                onClick={() => handleAnalyze(capture.id)}
                                disabled={isAnalyzing && analyzingId === capture.id}
                                title="タスク化 (AI解析)"
                            >
                                {isAnalyzing && analyzingId === capture.id ? '⏳' : '✨'}
                            </button>
                            <button
                                className="action-btn delete"
                                onClick={() => deleteCapture(capture.id)}
                                title="削除"
                            >
                                ×
                            </button>
                        </div>
                    </div>
                ))}
            </div>

            {isFormOpen && (
                <TaskFormModal
                    task={undefined} // Creating new task
                    initialData={analyzedTask} // Pass analyzed data as initial values (requires modifying Modal to accept this)
                    allTasks={[]} // Context for dependency selection (optional)
                    onClose={() => setIsFormOpen(false)}
                    onSubmit={handleSubmit as any} // Type mismatch workaround if needed
                    isSubmitting={false}
                />
            )}
        </div>
    );
}

function getDisplayText(capture: any) {
    if (capture.content_type === 'TEXT') {
        try {
            // Chrome Extension sends JSON in raw_text
            const data = JSON.parse(capture.raw_text);
            return data.title || data.url || capture.raw_text;
        } catch {
            return capture.raw_text;
        }
    }
    return capture.content_url || 'Captured Item';
}
