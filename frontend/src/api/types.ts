/**
 * TypeScript types - Mirror backend Pydantic models
 */

// Enums
export type TaskStatus = 'TODO' | 'IN_PROGRESS' | 'WAITING' | 'DONE';
export type Priority = 'HIGH' | 'MEDIUM' | 'LOW';
export type EnergyLevel = 'HIGH' | 'MEDIUM' | 'LOW';
export type CreatedBy = 'USER' | 'AGENT';
export type ChatMode = 'dump' | 'consult' | 'breakdown';
export type ProjectStatus = 'ACTIVE' | 'COMPLETED' | 'ARCHIVED';
export type ProjectVisibility = 'PRIVATE' | 'TEAM';
export type PhaseStatus = 'PLANNED' | 'ACTIVE' | 'COMPLETED' | 'ARCHIVED';
export type MilestoneStatus = 'ACTIVE' | 'COMPLETED' | 'ARCHIVED';
export type ProjectRole = 'OWNER' | 'ADMIN' | 'MEMBER';
export type BlockerStatus = 'OPEN' | 'RESOLVED';
export type CheckinType = 'weekly' | 'issue' | 'general';

// V2 Check-in types (Structured)
export type CheckinItemCategory = 'blocker' | 'discussion' | 'update' | 'request';
export type CheckinItemUrgency = 'high' | 'medium' | 'low';
export type CheckinMood = 'good' | 'okay' | 'struggling';
export type InvitationStatus = 'PENDING' | 'ACCEPTED' | 'REVOKED' | 'EXPIRED';
export type KpiDirection = 'up' | 'down' | 'neutral';
export type KpiStrategy = 'template' | 'ai' | 'custom';
export type MemoryScope = 'USER' | 'PROJECT' | 'WORK';
export type MemoryType = 'FACT' | 'PREFERENCE' | 'PATTERN' | 'RULE';

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
  purpose?: string;
  project_id?: string;
  phase_id?: string;
  status: TaskStatus;
  importance: Priority;
  urgency: Priority;
  energy_level: EnergyLevel;
  estimated_minutes?: number;
  due_date?: string;
  start_not_before?: string;
  pinned_date?: string;
  parent_id?: string;
  order_in_parent?: number;
  dependency_ids: string[];
  same_day_allowed: boolean;
  min_gap_days: number;
  source_capture_id?: string;
  created_by: CreatedBy;
  created_at: string;
  updated_at: string;

  // Progress tracking (0-100)
  progress?: number;

  // Meeting/Fixed-time event fields
  start_time?: string;
  end_time?: string;
  is_fixed_time: boolean;
  is_all_day: boolean;
  location?: string;
  attendees: string[];
  meeting_notes?: string;
  recurring_meeting_id?: string;
  recurring_task_id?: string;
  milestone_id?: string;
  touchpoint_count?: number;
  touchpoint_minutes?: number;
  touchpoint_gap_days: number;
  touchpoint_steps: TouchpointStep[];

  // Subtask guide field
  guide?: string;

  // Completion fields
  completion_note?: string;
  completed_at?: string;
  completed_by?: string;

  // Multi-member completion
  requires_all_completion: boolean;
}

export interface TouchpointStep {
  title: string;
  guide?: string;
  estimated_minutes?: number;
}

export interface TaskCreate {
  title: string;
  description?: string;
  purpose?: string;
  project_id?: string;
  phase_id?: string;
  importance?: Priority;
  urgency?: Priority;
  energy_level?: EnergyLevel;
  estimated_minutes?: number;
  due_date?: string;
  start_not_before?: string;
  parent_id?: string;
  order_in_parent?: number;
  dependency_ids?: string[];
  same_day_allowed?: boolean;
  min_gap_days?: number;
  source_capture_id?: string;
  // Meeting/Fixed-time event fields
  start_time?: string;
  end_time?: string;
  is_fixed_time?: boolean;
  is_all_day?: boolean;
  location?: string;
  attendees?: string[];
  meeting_notes?: string;
  milestone_id?: string;
  touchpoint_count?: number;
  touchpoint_minutes?: number;
  touchpoint_gap_days?: number;
  touchpoint_steps?: TouchpointStep[];

  // Subtask guide field
  guide?: string;

  // Multi-member completion
  requires_all_completion?: boolean;
}

export interface TaskUpdate {
  title?: string;
  description?: string;
  purpose?: string;
  project_id?: string;
  phase_id?: string;
  status?: TaskStatus;
  importance?: Priority;
  urgency?: Priority;
  energy_level?: EnergyLevel;
  estimated_minutes?: number;
  due_date?: string;
  start_not_before?: string;
  pinned_date?: string;
  parent_id?: string;
  order_in_parent?: number;
  dependency_ids?: string[];
  same_day_allowed?: boolean;
  min_gap_days?: number;
  progress?: number;
  // Meeting fields
  start_time?: string;
  end_time?: string;
  is_fixed_time?: boolean;
  is_all_day?: boolean;
  location?: string;
  attendees?: string[];
  meeting_notes?: string;
  milestone_id?: string;
  touchpoint_count?: number;
  touchpoint_minutes?: number;
  touchpoint_gap_days?: number;
  touchpoint_steps?: TouchpointStep[];

  // Subtask guide field
  guide?: string;

  // Completion fields
  completion_note?: string;

  // Multi-member completion
  requires_all_completion?: boolean;
}

export interface CompletionCheckResponse {
  task: Task;
  checked_count: number;
  total_count: number;
}

export interface TaskWithSubtasks extends Task {
  subtasks: Task[];
}

// Postpone / Do-Today models
export interface PostponeRequest {
  to_date: string;
  pin?: boolean;
  reason?: string;
}

export interface DoTodayRequest {
  pin?: boolean;
}

export interface TimeBlockMoveRequest {
  task_id: string;
  original_date: string;
  new_start: string;
  new_end: string;
}

// Chat models
export type ToolApprovalMode = 'manual' | 'auto';

export interface ChatRequest {
  text?: string;
  audio_url?: string;
  audio_base64?: string;
  audio_mime_type?: string;
  audio_language?: string;
  image_url?: string;
  image_base64?: string;
  mode?: ChatMode;
  session_id?: string;
  context?: Record<string, unknown>;
  approval_mode?: ToolApprovalMode;
  proposal_mode?: boolean;
  model?: string;
}

export interface AudioTranscriptionRequest {
  audio_base64: string;
  audio_mime_type?: string;
  audio_language?: string;
}

export interface AudioTranscriptionResponse {
  transcription: string;
}

export interface AvailableModel {
  id: string;
  name: string;
}

export interface AvailableModelsResponse {
  provider: string;
  default_model_id: string;
  models: AvailableModel[];
}

export interface SuggestedAction {
  action_type: string;
  label: string;
  payload: Record<string, unknown>;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd?: number;
  model?: string;
}

export interface ChatResponse {
  assistant_message: string;
  related_tasks: string[];
  suggested_actions: SuggestedAction[];
  session_id: string;
  capture_id?: string;
  usage?: TokenUsage;
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

// Memory models
export interface Memory {
  id: string;
  user_id: string;
  content: string;
  scope: MemoryScope;
  memory_type: MemoryType;
  project_id?: string;
  tags: string[];
  source: string;
  created_at: string;
  updated_at: string;
}

export interface MemoryCreate {
  content: string;
  scope: MemoryScope;
  memory_type: MemoryType;
  project_id?: string;
  tags?: string[];
}

export interface MemoryUpdate {
  content?: string;
  memory_type?: MemoryType;
  tags?: string[];
}

export interface MemorySearchResult {
  memory: Memory;
  relevance_score: number;
}

// Project models
export interface Project {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  visibility: ProjectVisibility;
  context_summary?: string;
  context?: string;
  priority: number;  // 1-10
  goals: string[];
  key_points: string[];
  kpi_config?: ProjectKpiConfig;
  parent_project_id?: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface ProjectWithTaskCount extends Project {
  total_tasks: number;
  completed_tasks: number;
  in_progress_tasks: number;
  unassigned_tasks: number;
  child_project_count: number;
  aggregated_total_tasks: number;
  aggregated_completed_tasks: number;
  aggregated_in_progress_tasks: number;
  aggregated_unassigned_tasks: number;
}

export type ProjectLinkRequestStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface ProjectLinkRequest {
  id: string;
  child_project_id: string;
  parent_project_id: string;
  requested_by: string;
  status: ProjectLinkRequestStatus;
  member_ids_to_add: string[];
  parent_approved: boolean;
  child_approved: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectLinkRequestCreate {
  child_project_id: string;
  parent_project_id: string;
  member_ids_to_add?: string[];
}

// Phase models
export interface Phase {
  id: string;
  user_id: string;
  project_id: string;
  name: string;
  description?: string;
  status: PhaseStatus;
  order_in_project: number;
  start_date?: string;
  end_date?: string;
  fixed_buffer_minutes?: number;
  created_at: string;
  updated_at: string;
}

export interface PhaseWithTaskCount extends Phase {
  total_tasks: number;
  completed_tasks: number;
  in_progress_tasks: number;
}

export interface PhaseCreate {
  project_id: string;
  name: string;
  description?: string;
  order_in_project?: number;
  start_date?: string;
  end_date?: string;
  fixed_buffer_minutes?: number;
}

export interface PhaseUpdate {
  name?: string;
  description?: string;
  status?: PhaseStatus;
  order_in_project?: number;
  start_date?: string;
  end_date?: string;
  fixed_buffer_minutes?: number;
}

// Milestone models
export interface Milestone {
  id: string;
  user_id: string;
  project_id: string;
  phase_id: string;
  title: string;
  description?: string;
  status: MilestoneStatus;
  order_in_phase: number;
  due_date?: string;
  created_at: string;
  updated_at: string;
}

export interface MilestoneCreate {
  project_id: string;
  phase_id: string;
  title: string;
  description?: string;
  order_in_phase?: number;
  due_date?: string;
}

export interface MilestoneUpdate {
  title?: string;
  description?: string;
  status?: MilestoneStatus;
  order_in_phase?: number;
  due_date?: string;
}

// Phase AI breakdown models
export interface MilestoneSuggestion {
  title: string;
  description?: string;
  due_date?: string | null;
}

export interface PhaseSuggestion {
  name: string;
  description?: string;
  milestones: MilestoneSuggestion[];
}

export interface PhaseBreakdownProposal {
  project_id: string;
  instruction?: string;
  create_milestones?: boolean;
  phases: PhaseSuggestion[];
}

export interface ProjectCreate {
  name: string;
  description?: string;
  visibility?: ProjectVisibility;
  context_summary?: string;
  context?: string;
  priority?: number;
  goals?: string[];
  key_points?: string[];
  kpi_config?: ProjectKpiConfig;
  parent_project_id?: string;
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  status?: ProjectStatus;
  visibility?: ProjectVisibility;
  context_summary?: string;
  context?: string;
  priority?: number;
  goals?: string[];
  key_points?: string[];
  kpi_config?: ProjectKpiConfig;
  parent_project_id?: string | null;
}

export interface ProjectMember {
  id: string;
  user_id: string;
  project_id: string;
  member_user_id: string;
  member_display_name?: string;
  role: ProjectRole;
  capacity_hours?: number;
  timezone?: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectMemberCreate {
  member_user_id: string;
  role?: ProjectRole;
  capacity_hours?: number;
  timezone?: string;
}

export interface ProjectMemberUpdate {
  role?: ProjectRole;
  capacity_hours?: number;
  timezone?: string;
}

export interface TaskAssignment {
  id: string;
  user_id: string;
  task_id: string;
  assignee_id: string;
  status?: TaskStatus;
  progress?: number;
  created_at: string;
  updated_at: string;
}

export interface TaskAssignmentCreate {
  assignee_id: string;
  status?: TaskStatus;
  progress?: number;
}

export interface TaskAssignmentUpdate {
  assignee_id?: string;
  status?: TaskStatus;
  progress?: number;
}

export interface TaskAssignmentsCreate {
  assignee_ids: string[];
}

export interface TaskAssignmentProposal {
  task_id: string;
  assignee_ids: string[];
}

export interface Checkin {
  id: string;
  user_id: string;
  project_id: string;
  member_user_id: string;
  checkin_date: string;
  checkin_type: CheckinType;
  summary_text?: string;
  raw_text: string;
  created_at: string;
}

export interface CheckinSummary {
  project_id: string;
  start_date?: string;
  end_date?: string;
  checkin_count: number;
  summary_text?: string;
  summary_error?: string;
  summary_error_detail?: string;
  summary_debug_prompt?: string;
  summary_debug_output?: string;
}

export interface CheckinSummarySave {
  summary_text: string;
  start_date?: string;
  end_date?: string;
  checkin_count: number;
}

export interface CheckinCreate {
  member_user_id: string;
  checkin_date: string;
  checkin_type: CheckinType;
  raw_text: string;
}

// =============================================================================
// V2 Check-in Models (Structured)
// =============================================================================

export interface CheckinItem {
  category: CheckinItemCategory;
  content: string;
  related_task_id?: string;
  urgency?: CheckinItemUrgency;
}

export interface CheckinItemResponse extends CheckinItem {
  id: string;
  related_task_title?: string;
}

export interface CheckinCreateV2 {
  member_user_id: string;
  checkin_date: string;
  items?: CheckinItem[];
  mood?: CheckinMood;
  must_discuss_in_next_meeting?: string;
  free_comment?: string;
  // Legacy fields (for backward compatibility)
  checkin_type?: CheckinType;
  raw_text?: string;
}

export interface CheckinV2 {
  id: string;
  user_id: string;
  project_id: string;
  member_user_id: string;
  checkin_date: string;
  items: CheckinItemResponse[];
  mood?: CheckinMood;
  must_discuss_in_next_meeting?: string;
  free_comment?: string;
  // Legacy fields
  checkin_type?: CheckinType;
  summary_text?: string;
  raw_text?: string;
  created_at: string;
}

export interface CheckinUpdateV2 {
  items?: CheckinItem[];
  mood?: CheckinMood;
  must_discuss_in_next_meeting?: string;
  free_comment?: string;
}

export interface CheckinAgendaItems {
  project_id: string;
  start_date?: string;
  end_date?: string;
  blockers: Array<{
    member: string;
    content: string;
    urgency: CheckinItemUrgency;
    related_task_id?: string;
    date: string;
  }>;
  discussions: Array<{
    member: string;
    content: string;
    urgency: CheckinItemUrgency;
    related_task_id?: string;
    date: string;
  }>;
  requests: Array<{
    member: string;
    content: string;
    urgency: CheckinItemUrgency;
    related_task_id?: string;
    date: string;
  }>;
  updates: Array<{
    member: string;
    content: string;
    urgency: CheckinItemUrgency;
    related_task_id?: string;
    date: string;
  }>;
  member_moods: Record<string, CheckinMood>;
  must_discuss_items: Array<{
    member: string;
    content: string;
    date: string;
  }>;
}

export type RecurrenceFrequency = 'weekly' | 'biweekly';

export interface RecurringMeeting {
  id: string;
  user_id: string;
  title: string;
  project_id?: string;
  frequency: RecurrenceFrequency;
  weekday: number;
  start_time: string;
  duration_minutes: number;
  location?: string;
  attendees: string[];
  agenda_window_days: number;
  anchor_date: string;
  last_occurrence?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RecurringMeetingCreate {
  title: string;
  project_id?: string;
  frequency: RecurrenceFrequency;
  weekday: number;
  start_time: string;
  duration_minutes: number;
  location?: string;
  attendees?: string[];
  agenda_window_days?: number;
  anchor_date?: string;
  is_active?: boolean;
}

export interface RecurringMeetingUpdate {
  title?: string;
  project_id?: string;
  frequency?: RecurrenceFrequency;
  weekday?: number;
  start_time?: string;
  duration_minutes?: number;
  location?: string;
  attendees?: string[];
  agenda_window_days?: number;
  anchor_date?: string;
  last_occurrence?: string;
  is_active?: boolean;
}

// Recurring Task models
export type RecurringTaskFrequency = 'daily' | 'weekly' | 'biweekly' | 'monthly' | 'bimonthly' | 'custom';

export interface RecurringTask {
  id: string;
  user_id: string;
  title: string;
  description?: string;
  purpose?: string;
  project_id?: string;
  phase_id?: string;
  frequency: RecurringTaskFrequency;
  weekday?: number;
  weekdays?: number[];
  day_of_month?: number;
  custom_interval_days?: number;
  start_time?: string;
  estimated_minutes?: number;
  importance: Priority;
  urgency: Priority;
  energy_level: EnergyLevel;
  is_active: boolean;
  anchor_date: string;
  last_generated_date?: string;
  created_at: string;
  updated_at: string;
}

export interface RecurringTaskCreate {
  title: string;
  description?: string;
  purpose?: string;
  project_id?: string;
  phase_id?: string;
  frequency: RecurringTaskFrequency;
  weekday?: number;
  weekdays?: number[];
  day_of_month?: number;
  custom_interval_days?: number;
  start_time?: string;
  estimated_minutes?: number;
  importance?: Priority;
  urgency?: Priority;
  energy_level?: EnergyLevel;
  anchor_date?: string;
  is_active?: boolean;
}

export interface RecurringTaskUpdate {
  title?: string;
  description?: string;
  purpose?: string;
  project_id?: string;
  phase_id?: string;
  frequency?: RecurringTaskFrequency;
  weekday?: number;
  weekdays?: number[];
  day_of_month?: number;
  custom_interval_days?: number;
  start_time?: string;
  estimated_minutes?: number;
  importance?: Priority;
  urgency?: Priority;
  energy_level?: EnergyLevel;
  anchor_date?: string;
  is_active?: boolean;
}

export interface Blocker {
  id: string;
  user_id: string;
  task_id: string;
  created_by: string;
  status: BlockerStatus;
  reason: string;
  resolved_by?: string;
  created_at: string;
  resolved_at?: string;
}

export interface BlockerCreate {
  created_by: string;
  reason: string;
}

export interface BlockerUpdate {
  status?: BlockerStatus;
  resolved_by?: string;
}

export interface ProjectInvitation {
  id: string;
  user_id: string;
  project_id: string;
  email: string;
  role: ProjectRole;
  status: InvitationStatus;
  invited_by: string;
  accepted_by?: string;
  token?: string;
  created_at: string;
  updated_at: string;
  expires_at?: string;
  accepted_at?: string;
}

export interface ProjectInvitationCreate {
  email: string;
  role?: ProjectRole;
}

export interface ProjectInvitationUpdate {
  status: InvitationStatus;
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
  meeting_minutes: number;
  overflow_minutes: number;
  overflow: boolean;
}

export interface TaskAllocation {
  task_id: string;
  minutes: number;
}

export interface WorkBreak {
  start: string;
  end: string;
}

export interface WorkdayHours {
  enabled: boolean;
  start: string;
  end: string;
  breaks: WorkBreak[];
}

export interface ScheduleSettings {
  user_id: string;
  weekly_work_hours: WorkdayHours[];
  buffer_hours: number;
  break_after_task_minutes: number;
  created_at: string;
  updated_at: string;
}

export interface ScheduleSettingsUpdate {
  weekly_work_hours?: WorkdayHours[];
  buffer_hours?: number;
  break_after_task_minutes?: number;
}

export interface ScheduleDay {
  date: string;
  capacity_minutes: number;
  allocated_minutes: number;
  overflow_minutes: number;
  task_allocations: TaskAllocation[];
  meeting_minutes: number;
  available_minutes: number;
}

export interface TaskScheduleInfo {
  task_id: string;
  title: string;
  project_id?: string;
  parent_id?: string;
  parent_title?: string;
  order_in_parent?: number;
  due_date?: string;
  planned_start?: string;
  planned_end?: string;
  total_minutes: number;
  priority_score: number;
  status?: string;
  pinned_date?: string;
  is_fixed_time?: boolean;
  start_time?: string;
  end_time?: string;
}

export interface ExcludedTask {
  task_id: string;
  title: string;
  reason: string;
  parent_id?: string;
  parent_title?: string;
}

export interface PendingChange {
  task_id: string;
  title: string;
  change_type: 'new' | 'updated' | 'removed';
}

export interface ScheduleTimeBlock {
  task_id: string;
  start: string;
  end: string;
  kind: 'meeting' | 'auto';
  status?: TaskStatus;
  pinned_date?: string;
}

export interface ScheduleResponse {
  start_date: string;
  days: ScheduleDay[];
  tasks: TaskScheduleInfo[];
  unscheduled_task_ids: { task_id: string; reason: string }[];
  excluded_tasks: ExcludedTask[];
  plan_state?: 'planned' | 'stale' | 'forecast';
  plan_group_id?: string;
  plan_generated_at?: string;
  pending_changes?: PendingChange[];
  time_blocks?: ScheduleTimeBlock[];
  pinned_overflow_task_ids?: string[];
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

// Proposal models (AI謠先｡域価隲ｾ讖溯・)
export type ProposalType =
  'create_task'
  | 'create_project'
  | 'create_work_memory'
  | 'assign_task'
  | 'phase_breakdown'
  | 'tool_action';

export interface ToolActionProposalPayload {
  tool_name: string;
  args: Record<string, unknown>;
}

export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'expired';

export interface Proposal {
  id: string;
  user_id: string;
  session_id: string;
  proposal_type: ProposalType;
  status: ProposalStatus;
  payload: TaskCreate | ProjectCreate | MemoryCreate | TaskAssignmentProposal | PhaseBreakdownProposal | ToolActionProposalPayload; // The data for proposals
  description: string; // AI-generated explanation
  created_at: string;
  expires_at: string;
}

export interface ProposalResponse {
  proposal_id: string;
  proposal_type: ProposalType;
  description: string;
  payload: TaskCreate | ProjectCreate | MemoryCreate | TaskAssignmentProposal | PhaseBreakdownProposal | ToolActionProposalPayload;
}

// ===========================================
// Meeting Agenda Models
export interface MeetingAgendaItem {
  id: string;
  meeting_id?: string;  // For RecurringMeeting (optional since task_id can be used instead)
  task_id?: string;     // For standalone meeting tasks
  user_id: string;
  title: string;
  description?: string;
  duration_minutes?: number;
  order_index: number;
  is_completed: boolean;
  event_date?: string;
  created_at: string;
  updated_at: string;
}

export interface MeetingAgendaItemCreate {
  title: string;
  description?: string;
  duration_minutes?: number;
  order_index?: number;
  event_date?: string;
  task_id?: string;  // For standalone meeting tasks
}

export interface MeetingAgendaItemUpdate {
  title?: string;
  description?: string;
  duration_minutes?: number;
  order_index?: number;
  is_completed?: boolean;
  event_date?: string;
  task_id?: string;
}


// ===========================================
// Issue Models (Feature Requests / Bug Reports)
// ===========================================

export type IssueStatus = 'OPEN' | 'UNDER_REVIEW' | 'PLANNED' | 'IN_PROGRESS' | 'COMPLETED' | 'WONT_FIX';
export type IssueCategory = 'FEATURE_REQUEST' | 'BUG_REPORT' | 'IMPROVEMENT' | 'QUESTION';

export interface Issue {
  id: string;
  user_id: string;
  display_name?: string;
  title: string;
  content: string;
  category: IssueCategory;
  status: IssueStatus;
  like_count: number;
  liked_by_me: boolean;
  admin_response?: string;
  created_at: string;
  updated_at: string;
}

export interface IssueCreate {
  title: string;
  content: string;
  category: IssueCategory;
}

export interface IssueUpdate {
  title?: string;
  content?: string;
  category?: IssueCategory;
}

export interface IssueStatusUpdate {
  status: IssueStatus;
  admin_response?: string;
}

export interface IssueListResponse {
  items: Issue[];
  total: number;
}

export interface IssueComment {
  id: string;
  issue_id: string;
  user_id: string;
  display_name?: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface IssueCommentCreate {
  content: string;
}

export interface IssueCommentListResponse {
  comments: IssueComment[];
  total: number;
}

export interface IssueChatRequest {
  message: string;
  session_id?: string;
}

export interface IssueChatChunk {
  chunk_type: 'session' | 'text' | 'tool_start' | 'tool_end' | 'questions' | 'done' | 'error';
  session_id?: string;
  content?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  tool_result?: unknown;
  questions?: PendingQuestion[];
  questions_context?: string;
}

// User Questions (ask_user_questions tool)
export interface PendingQuestion {
  id: string;
  question: string;
  options: string[];
  allow_multiple: boolean;
  placeholder?: string;
}

export interface PendingQuestions {
  questions: PendingQuestion[];
  context?: string;
}

export interface QuestionAnswer {
  question_id: string;
  selected_options: string[];
  other_text?: string;
}

// ===========================================
// Achievement Models
// ===========================================

export type GenerationType = 'AUTO' | 'MANUAL';

export interface SkillExperience {
  category: string;
  experience_count: number;
  percentage: number;
}

export interface SkillAnalysis {
  domain_skills: SkillExperience[];
  soft_skills: SkillExperience[];
  work_types: SkillExperience[];
  strengths: string[];
  growth_areas: string[];
}

export interface Achievement {
  id: string;
  user_id: string;
  period_start: string;
  period_end: string;
  period_label?: string;
  summary: string;
  weekly_activities: string[];
  growth_points: string[];
  skill_analysis: SkillAnalysis;
  next_suggestions: string[];
  task_count: number;
  project_ids: string[];
  task_snapshots: CompletedTaskPreview[];
  append_note?: string;
  share_token?: string;
  generation_type: GenerationType;
  created_at: string;
  updated_at: string;
}

export interface ShareLinkResponse {
  share_token: string;
  share_url: string;
}

export interface SharedAchievement {
  id: string;
  period_start: string;
  period_end: string;
  period_label?: string;
  summary: string;
  weekly_activities: string[];
  growth_points: string[];
  skill_analysis: SkillAnalysis;
  next_suggestions: string[];
  task_count: number;
  created_at: string;
}

export interface AchievementCreate {
  period_start: string;
  period_end: string;
  period_label?: string;
}

export interface AchievementUpdate {
  summary?: string;
  weekly_activities?: string[];
  growth_points?: string[];
  next_suggestions?: string[];
  strengths?: string[];
  growth_areas?: string[];
  append_note?: string;
}

export interface AchievementListResponse {
  achievements: Achievement[];
  total: number;
}

export interface CompletedTaskPreview {
  id: string;
  title: string;
  description?: string;
  project_id?: string;
  completed_at: string;
  completion_note?: string;
}

export interface CompletedTasksPreviewResponse {
  task_count: number;
  tasks: CompletedTaskPreview[];
}

// ===========================================
// Notification Models
// ===========================================

export type NotificationType =
  | 'achievement_personal'
  | 'achievement_project'
  | 'task_assigned'
  | 'project_invited'
  | 'milestone_reached'
  | 'checkin_created'
  | 'checkin_updated'
  | 'issue_new'
  | 'issue_edited'
  | 'issue_liked'
  | 'issue_commented'
  | 'issue_status_changed'
  | 'heartbeat';

export interface Notification {
  id: string;
  user_id: string;
  type: NotificationType;
  title: string;
  message: string;
  link_type?: string;
  link_id?: string;
  project_id?: string;
  project_name?: string;
  is_read: boolean;
  read_at?: string;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: Notification[];
  unread_count: number;
  total: number;
}

export interface UnreadCountResponse {
  count: number;
}

export interface HeartbeatUnreadCountResponse {
  count: number;
}

export type HeartbeatRiskSeverity = 'critical' | 'high' | 'medium' | 'low';

export interface HeartbeatRiskTask {
  task_id: string;
  title: string;
  severity: HeartbeatRiskSeverity;
  risk_score: number;
  days_remaining?: number;
  required_days?: number;
  slack_days?: number;
  due_date?: string;
}

export interface HeartbeatStatusResponse {
  evaluated: number;
  risk_level: 'low' | 'medium' | 'high';
  top_risks: HeartbeatRiskTask[];
  evaluated_at: string;
  sent_today: number;
  limit: number;
}

export type HeartbeatIntensity = 'gentle' | 'standard' | 'firm';

export interface HeartbeatSettingsResponse {
  user_id: string;
  enabled: boolean;
  notification_limit_per_day: number;
  notification_window_start: string;
  notification_window_end: string;
  heartbeat_intensity: HeartbeatIntensity;
  daily_capacity_per_task_minutes: number;
  cooldown_hours_per_task: number;
  created_at: string;
  updated_at: string;
}

export interface HeartbeatSettingsUpdate {
  enabled?: boolean;
  notification_limit_per_day?: number;
  notification_window_start?: string;
  notification_window_end?: string;
  heartbeat_intensity?: HeartbeatIntensity;
  daily_capacity_per_task_minutes?: number;
  cooldown_hours_per_task?: number;
}

// ===========================================
// Project Achievement Models
// ===========================================

export interface MemberContribution {
  user_id: string;
  display_name: string;
  task_count: number;
  main_areas: string[];
  task_titles: string[];
}

export interface ProjectAchievement {
  id: string;
  project_id: string;
  period_start: string;
  period_end: string;
  period_label?: string;
  summary: string;
  team_highlights: string[];
  challenges: string[];
  learnings: string[];
  member_contributions: MemberContribution[];
  total_task_count: number;
  remaining_tasks_count: number;
  open_issues: string[];
  append_note?: string;
  generation_type: GenerationType;
  created_at: string;
  updated_at: string;
}

export interface ProjectAchievementCreate {
  period_start: string;
  period_end: string;
  period_label?: string;
}

export interface ProjectAchievementUpdate {
  summary?: string;
  team_highlights?: string[];
  challenges?: string[];
  learnings?: string[];
  open_issues?: string[];
  append_note?: string;
}

export interface ProjectAchievementListResponse {
  achievements: ProjectAchievement[];
  total: number;
}

