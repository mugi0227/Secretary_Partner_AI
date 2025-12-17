/**
 * TypeScript types - Mirror backend Pydantic models
 */

// Enums
export type TaskStatus = 'TODO' | 'IN_PROGRESS' | 'WAITING' | 'DONE';
export type Priority = 'HIGH' | 'MEDIUM' | 'LOW';
export type EnergyLevel = 'HIGH' | 'LOW';
export type CreatedBy = 'USER' | 'AGENT';
export type ChatMode = 'dump' | 'consult' | 'breakdown';
export type ProjectStatus = 'ACTIVE' | 'COMPLETED' | 'ARCHIVED';

// Task models
export interface Task {
  id: string;
  user_id: string;
  title: string;
  description?: string;
  project_id?: string;
  status: TaskStatus;
  importance: Priority;
  urgency: Priority;
  energy_level: EnergyLevel;
  estimated_minutes?: number;
  due_date?: string;
  parent_id?: string;
  source_capture_id?: string;
  created_by: CreatedBy;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  title: string;
  description?: string;
  project_id?: string;
  importance?: Priority;
  urgency?: Priority;
  energy_level?: EnergyLevel;
  estimated_minutes?: number;
  due_date?: string;
  parent_id?: string;
}

export interface TaskUpdate {
  title?: string;
  description?: string;
  project_id?: string;
  status?: TaskStatus;
  importance?: Priority;
  urgency?: Priority;
  energy_level?: EnergyLevel;
  estimated_minutes?: number;
  due_date?: string;
  parent_id?: string;
}

export interface TaskWithSubtasks extends Task {
  subtasks: Task[];
}

// Chat models
export interface ChatRequest {
  text?: string;
  audio_url?: string;
  image_url?: string;
  mode?: ChatMode;
  session_id?: string;
  context?: Record<string, unknown>;
}

export interface SuggestedAction {
  action_type: string;
  label: string;
  payload: Record<string, unknown>;
}

export interface ChatResponse {
  assistant_message: string;
  related_tasks: string[];
  suggested_actions: SuggestedAction[];
  session_id: string;
  capture_id?: string;
}

// Project models
export interface Project {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  context_summary?: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface ProjectWithTaskCount extends Project {
  total_tasks: number;
  completed_tasks: number;
  in_progress_tasks: number;
}

export interface ProjectCreate {
  name: string;
  description?: string;
  context_summary?: string;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  status?: ProjectStatus;
  context_summary?: string;
}
