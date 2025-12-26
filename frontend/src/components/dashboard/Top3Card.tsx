import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTop3 } from "../../hooks/useTop3";
import { useTasks } from "../../hooks/useTasks";
import { AnimatePresence } from "framer-motion";
import { TaskItem } from "./TaskItem";
import { TaskDetailModal } from "../tasks/TaskDetailModal";
import { TaskFormModal } from "../tasks/TaskFormModal";
import { tasksApi } from "../../api/tasks";
import type { Task, TaskCreate, TaskUpdate } from "../../api/types";
import "./Top3Card.css";

const TEXT = {
  title: "Focus for Today",
  tag: "Top 3",
  loading: "読み込み中...",
  error: "タスクの取得に失敗しました。バックエンドサーバーが起動しているか確認してください。",
  emptyTitle: "タスクがありません",
  emptyHint: "新しいタスクを追加するか、チャットで話しかけてみましょう",
  dependencyAlert: "このタスクを完了するには、先に依存しているタスクを完了してください。",
  dependencyPrefix: "依存: ",
  dependencyMissing: "依存タスクを取得できません",
};

export function Top3Card() {
  const { data: top3Response, isLoading, error } = useTop3();
  const { updateTask, createTask, isCreating, isUpdating } = useTasks();
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [openedParentTask, setOpenedParentTask] = useState<Task | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [taskToEdit, setTaskToEdit] = useState<Task | undefined>(undefined);
  const [removingTaskIds, setRemovingTaskIds] = useState<Set<string>>(new Set());
  const [pendingDoneTasks, setPendingDoneTasks] = useState<Map<string, Task>>(new Map());
  const [dependencyCache, setDependencyCache] = useState<Record<string, Task>>({});

  const tasks = top3Response?.tasks || [];
  const allTasks = useMemo(() => {
    const merged = [...tasks];
    pendingDoneTasks.forEach((task, taskId) => {
      if (!merged.find(t => t.id === taskId)) {
        merged.push(task);
      }
    });
    return merged;
  }, [tasks, pendingDoneTasks]);

  const { data: subtasks = [] } = useQuery({
    queryKey: ["subtasks", selectedTask?.id || openedParentTask?.id],
    queryFn: () => {
      const targetId = openedParentTask?.id || selectedTask?.id;
      return targetId ? tasksApi.getSubtasks(targetId) : Promise.resolve([]);
    },
    enabled: !!(selectedTask || openedParentTask),
  });

  useEffect(() => {
    const knownIds = new Set<string>([
      ...allTasks.map(task => task.id),
      ...Object.keys(dependencyCache),
    ]);
    const missingIds = new Set<string>();
    allTasks.forEach(task => {
      (task.dependency_ids || []).forEach(depId => {
        if (!knownIds.has(depId)) {
          missingIds.add(depId);
        }
      });
    });
    if (missingIds.size === 0) return;
    Promise.all(
      Array.from(missingIds).map(depId =>
        tasksApi.getById(depId).catch(() => null)
      )
    ).then(results => {
      const updates: Record<string, Task> = {};
      results.forEach(task => {
        if (task) updates[task.id] = task;
      });
      if (Object.keys(updates).length) {
        setDependencyCache(prev => ({ ...prev, ...updates }));
      }
    });
  }, [allTasks, dependencyCache]);

  const dependencyStatusByTaskId = useMemo(() => {
    const map = new Map<string, { blocked: boolean; reason?: string }>();
    const taskMap = new Map<string, Task>([
      ...allTasks.map(task => [task.id, task]),
      ...Object.values(dependencyCache).map(task => [task.id, task]),
    ]);
    allTasks.forEach(task => {
      if (!task.dependency_ids || task.dependency_ids.length === 0) return;
      const blockingTitles: string[] = [];
      let hasMissing = false;
      task.dependency_ids.forEach(depId => {
        const depTask = taskMap.get(depId);
        if (!depTask) {
          hasMissing = true;
          return;
        }
        if (depTask.status !== "DONE") {
          blockingTitles.push(depTask.title);
        }
      });
      if (hasMissing || blockingTitles.length > 0) {
        const reason = blockingTitles.length > 0
          ? `${TEXT.dependencyPrefix}${blockingTitles.join(", ")}`
          : TEXT.dependencyMissing;
        map.set(task.id, { blocked: true, reason });
      }
    });
    return map;
  }, [allTasks, dependencyCache]);

  const handleTaskClick = (task: Task) => {
    if (task.parent_id) {
      const parent = allTasks.find(t => t.id === task.parent_id);
      if (parent) {
        setOpenedParentTask(parent);
        setSelectedTask(task);
      } else {
        tasksApi.getById(task.parent_id).then(parentTask => {
          setOpenedParentTask(parentTask);
          setSelectedTask(task);
        }).catch(err => {
          console.error("Failed to fetch parent task:", err);
          setSelectedTask(task);
        });
      }
    } else {
      setSelectedTask(task);
      setOpenedParentTask(null);
    }
  };

  const handleCloseModal = () => {
    setSelectedTask(null);
    setOpenedParentTask(null);
  };

  const handleCloseForm = () => {
    setIsFormOpen(false);
    setTaskToEdit(undefined);
  };

  const handleSubmitForm = (data: TaskCreate | TaskUpdate) => {
    if (taskToEdit) {
      updateTask(taskToEdit.id, data as TaskUpdate);
    } else {
      createTask(data as TaskCreate);
    }
    handleCloseForm();
  };

  const handleTaskCheck = (taskId: string) => {
    const blockedStatus = dependencyStatusByTaskId.get(taskId);
    if (blockedStatus?.blocked) {
      alert(TEXT.dependencyAlert);
      return;
    }

    const taskToKeep = tasks.find(t => t.id === taskId);
    if (taskToKeep) {
      setPendingDoneTasks(prev => new Map(prev).set(taskId, { ...taskToKeep, status: "DONE" }));
    }

    updateTask(taskId, { status: "DONE" });

    setTimeout(() => {
      setRemovingTaskIds(prev => new Set(prev).add(taskId));

      setTimeout(() => {
        setPendingDoneTasks(prev => {
          const newMap = new Map(prev);
          newMap.delete(taskId);
          return newMap;
        });

        setRemovingTaskIds(prev => {
          const newSet = new Set(prev);
          newSet.delete(taskId);
          return newSet;
        });
      }, 600);
    }, 1500);
  };

  if (error) {
    return (
      <div className="top3-card">
        <div className="card-header">
          <h3>{TEXT.title}</h3>
          <span className="tag high-priority">{TEXT.tag}</span>
        </div>
        <div className="error-message">
          {TEXT.error}
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="top3-card">
        <div className="card-header">
          <h3>{TEXT.title}</h3>
          <span className="tag high-priority">{TEXT.tag}</span>
        </div>
        <div className="loading-state">{TEXT.loading}</div>
      </div>
    );
  }

  const activeTaskCount = allTasks.filter(task => !removingTaskIds.has(task.id)).length;
  const isEmpty = activeTaskCount === 0 && removingTaskIds.size === 0;

  return (
    <div className="top3-card">
      <div className="card-header">
        <h3>{TEXT.title}</h3>
        <span className="tag high-priority">{TEXT.tag}</span>
      </div>

      <div className="task-list">
        {isEmpty ? (
          <div className="empty-state">
            <p>{TEXT.emptyTitle}</p>
            <p className="empty-hint">{TEXT.emptyHint}</p>
          </div>
        ) : (
          allTasks.map((task) => {
            const dependencyStatus = dependencyStatusByTaskId.get(task.id);
            return (
              <TaskItem
                key={task.id}
                task={task}
                onClick={handleTaskClick}
                onCheck={handleTaskCheck}
                isRemoving={removingTaskIds.has(task.id)}
                isBlocked={dependencyStatus?.blocked}
                blockedReason={dependencyStatus?.reason}
              />
            );
          })
        )}
      </div>

      <AnimatePresence>
        {selectedTask && (
          <TaskDetailModal
            task={openedParentTask || selectedTask}
            subtasks={subtasks}
            allTasks={allTasks}
            initialSubtask={openedParentTask ? selectedTask : null}
            onClose={handleCloseModal}
            onEdit={(task) => {
              setTaskToEdit(task);
              setIsFormOpen(true);
              handleCloseModal();
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isFormOpen && (
          <TaskFormModal
            task={taskToEdit}
            allTasks={allTasks}
            onClose={handleCloseForm}
            onSubmit={handleSubmitForm}
            isSubmitting={isCreating || isUpdating}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
