import { FaRobot, FaPlay } from 'react-icons/fa6';
import './AgentCard.css';

export function AgentCard() {
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good Morning';
    if (hour < 18) return 'Good Afternoon';
    return 'Good Evening';
  };

  const getAdviceMessage = () => {
    const hour = new Date().getHours();
    if (hour < 12) {
      return 'タスクのエネルギーレベルに合わせて優先順位を調整しています。';
    }
    return 'タスクのエネルギーレベルに合わせて優先順位を調整しています。';
  };

  return (
    <div className="agent-card">
      <div className="agent-status">
        <div className="agent-avatar">
          <div className="pulse-ring"></div>
          <FaRobot />
        </div>
        <div className="agent-message">
          <h2>{getGreeting()}, Shuhei!</h2>
          <p>{getAdviceMessage()}</p>
        </div>
      </div>
      <div className="agent-actions">
        <button className="secondary-btn">
          <FaPlay />
          <span>朝のブリーフィング</span>
        </button>
      </div>
    </div>
  );
}
