import { useState } from 'react';
import { motion } from 'framer-motion';
import { AgentCard } from '../components/dashboard/AgentCard';
import { DailyBriefingCard } from '../components/dashboard/DailyBriefingCard';
import { TodayTasksCard } from '../components/dashboard/TodayTasksCard';
import { OverdueCheckinCard } from '../components/dashboard/OverdueCheckinCard';
import { ScheduleOverviewCard } from '../components/dashboard/ScheduleOverviewCard';
import { WeeklyMeetingsCard } from '../components/dashboard/WeeklyMeetingsCard';
import { WeeklyMeetingNotificationBanner } from '../components/dashboard/WeeklyMeetingNotificationBanner';
import { useTaskModal } from '../hooks/useTaskModal';
import { useTasks } from '../hooks/useTasks';
import './DashboardPage.css';

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { y: 20, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: {
      type: "spring" as const,
      stiffness: 300,
      damping: 24
    }
  }
};

export function DashboardPage() {
  const [isBriefingOpen, setIsBriefingOpen] = useState(false);
  const [isClosing, setIsClosing] = useState(false);
  const { tasks, refetch: refetchTasks } = useTasks();

  // Use the unified task modal hook
  const taskModal = useTaskModal({
    tasks,
    onRefetch: refetchTasks,
  });

  const handleCloseBriefing = () => {
    setIsClosing(true);
    setTimeout(() => {
      setIsBriefingOpen(false);
      setIsClosing(false);
    }, 300);
  };

  return (
    <motion.div
      className="dashboard-page"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      <motion.div
        variants={itemVariants}
      >
        <AgentCard onOpenDailyBriefing={() => setIsBriefingOpen(true)} />
      </motion.div>

      <motion.div variants={itemVariants}>
        <WeeklyMeetingNotificationBanner />
      </motion.div>

      <motion.div variants={itemVariants}>
        <TodayTasksCard onTaskClick={taskModal.openTaskDetail} />
      </motion.div>

      <motion.div variants={itemVariants}>
        <OverdueCheckinCard />
      </motion.div>

      <motion.div
        variants={itemVariants}
        className="dashboard-bottom-section"
      >
        <ScheduleOverviewCard onTaskClick={taskModal.openTaskDetailById} />
        <WeeklyMeetingsCard />
      </motion.div>

      {isBriefingOpen && (
        <div
          className={`daily-briefing-modal ${isClosing ? 'closing' : ''}`}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="daily-briefing-backdrop"
            onClick={handleCloseBriefing}
          />
          <div className="daily-briefing-panel">
            <button
              type="button"
              className="daily-briefing-close"
              onClick={handleCloseBriefing}
              aria-label="Close"
            >
              X
            </button>
            <DailyBriefingCard onFinish={handleCloseBriefing} />
          </div>
        </div>
      )}

      {taskModal.renderModals()}
    </motion.div>
  );
}
