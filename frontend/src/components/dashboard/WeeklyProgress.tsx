import './WeeklyProgress.css';

export function WeeklyProgress() {
  // Mock data for the week
  const weekData = [
    { day: '月', height: 40 },
    { day: '火', height: 70 },
    { day: '水', height: 50 },
    { day: '木', height: 30, active: true },
    { day: '金', height: 20 },
    { day: '土', height: 10 },
    { day: '日', height: 10 },
  ];

  return (
    <div className="stats-card">
      <h3>Weekly Progress</h3>
      <div className="progress-chart-mock">
        {weekData.map((item, index) => (
          <div
            key={index}
            className={`bar ${item.active ? 'active' : ''}`}
            style={{ height: `${item.height}%` }}
            title={`${item.day}: ${item.height}%`}
          >
            <span className="bar-label">{item.day}</span>
          </div>
        ))}
      </div>
      <div className="stats-summary">
        <div className="stat-item">
          <span className="stat-value">12</span>
          <span className="stat-label">Done</span>
        </div>
        <div className="stat-item">
          <span className="stat-value">5</span>
          <span className="stat-label">Pending</span>
        </div>
      </div>
    </div>
  );
}
