const STATUS_CONFIG = {
  connected: {
    color: "bg-green-400",
    label: "Live",
    textColor: "text-green-600 dark:text-green-400",
  },
  connecting: {
    color: "bg-yellow-400",
    label: "Connecting",
    textColor: "text-yellow-600 dark:text-yellow-400",
  },
  disconnected: {
    color: "bg-gray-400",
    label: "Polling",
    textColor: "text-gray-500 dark:text-gray-400",
  },
};

export default function WebSocketStatus({ status }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.disconnected;

  return (
    <div className="flex items-center gap-1.5">
      <span
        className={`w-2 h-2 rounded-full ${config.color} ${
          status === "connecting" ? "animate-pulse" : ""
        }`}
      />
      <span className={`text-xs font-medium ${config.textColor}`}>
        {config.label}
      </span>
    </div>
  );
}
