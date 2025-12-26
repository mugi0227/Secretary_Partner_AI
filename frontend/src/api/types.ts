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
export type KpiDirection = 'up' | 'down' | 'neutral';
export type KpiStrategy = 'template' | 'ai' | 'custom';

export interface ProjectKpiMetric {
  key: string;
  label: string;
  description?: string;
  unit?: string;
  target?: number;
  current?: number;
  direction?: KpiDirection;
  source?: string;
}

export interface ProjectKpiConfig {
  strategy?: KpiStrategy;
  template_id?: string;
  metrics: ProjectKpiMetric[];
}

export interface ProjectKpiTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  metrics: ProjectKpiMetric[];
}

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
  dependency_ids: string[];
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
  dependency_ids?: string[];
  source_capture_id?: string;
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
  dependency_ids?: string[];
}

export interface TaskWithSubtasks extends Task {
  subtasks: Task[];
}

// Chat models
export interface ChatRequest {
  text?: string;
  audio_url?: string;
  image_url?: string;
  image_base64?: string;
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

export interface ChatSession {
  session_id: string;
  title?: string;
  updated_at?: string;
}

export interface ChatHistoryMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at?: string;
}

// Project models
export interface Project {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  context_summary?: string;
  context?: string;  // 詳細コンテキスト（README）
  priority: number;  // 1-10
  goals: string[];
  key_points: string[];
  kpi_config?: ProjectKpiConfig;
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
  context?: string;
  priority?: number;
  goals?: string[];
  key_points?: string[];
  kpi_config?: ProjectKpiConfig;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  status?: ProjectStatus;
  context_summary?: string;
  context?: string;
  priority?: number;
  goals?: string[];
  key_points?: string[];
  kpi_config?: ProjectKpiConfig;
}

// Top 3 response models
export interface CapacityInfo {
  feasible: boolean;
  total_minutes: number;
  capacity_minutes: number;
  overflow_minutes: number;
  capacity_usage_percent: number;
}

export interface Top3Response {
  tasks: Task[];
  capacity_info: CapacityInfo | null;
  overflow_suggestion: string;
}

export interface TodayTaskAllocation {
  task_id: string;
  allocated_minutes: number;
  total_minutes: number;
  ratio: number;
}

export interface TodayTasksResponse {
  today: string;
  today_tasks: Task[];
  today_allocations: TodayTaskAllocation[];
  top3_ids: string[];
  total_estimated_minutes: number;
  capacity_minutes: number;
  overflow_minutes: number;
  overflow: boolean;
}

export interface TaskAllocation {
  task_id: string;
  minutes: number;
}

export interface ScheduleDay {
  date: string;
  capacity_minutes: number;
  allocated_minutes: number;
  overflow_minutes: number;
  task_allocations: TaskAllocation[];
}

export interface TaskScheduleInfo {
  task_id: string;
  title: string;
  project_id?: string;
  parent_id?: string;
  parent_title?: string;
  due_date?: string;
  planned_start?: string;
  planned_end?: string;
  total_minutes: number;
  priority_score: number;
}

export interface ExcludedTask {
  task_id: string;
  title: string;
  reason: string;
  parent_id?: string;
  parent_title?: string;
}

export interface ScheduleResponse {
  start_date: string;
  days: ScheduleDay[];
  tasks: TaskScheduleInfo[];
  unscheduled_task_ids: { task_id: string; reason: string }[];
  excluded_tasks: ExcludedTask[];
}

// Capture models
export type ContentType = 'TEXT' | 'AUDIO' | 'IMAGE';

export interface Capture {
  id: string;
  user_id: string;
  content_type: ContentType;
  content_url?: string;
  raw_text?: string;
  transcription?: string;
  image_analysis?: string;
  processed: boolean;
  created_at: string;
}

export interface CaptureCreate {
  content_type: ContentType;
  content_url?: string;
  raw_text?: string;
  transcription?: string;
  image_analysis?: string;
  base64_image?: string;
}
