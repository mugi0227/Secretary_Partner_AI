import { motion } from 'framer-motion';
import { AgentCard } from '../components/dashboard/AgentCard';
import { TodayTasksCard } from '../components/dashboard/TodayTasksCard';
import { ScheduleOverviewCard } from '../components/dashboard/ScheduleOverviewCard';
import { WeeklyProgress } from '../components/dashboard/WeeklyProgress';
import { InboxWidget } from '../components/dashboard/InboxWidget';
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
        <AgentCard />
      </motion.div>

      <div className="dashboard-grid">
        <motion.div
          variants={itemVariants}
          className="grid-main"
        >
          <InboxWidget />
          <TodayTasksCard />
          <ScheduleOverviewCard />
        </motion.div>

        <motion.div
          variants={itemVariants}
          className="grid-side"
        >
          <WeeklyProgress />
        </motion.div>
      </div>
    </motion.div>
  );
}
