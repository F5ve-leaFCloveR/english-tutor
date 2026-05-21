interface Props {
  role: "user" | "assistant";
  text: string;
  isSpeaking?: boolean;
}

export function MessageBubble({ role, text, isSpeaking }: Props) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={
          `max-w-[75%] md:max-w-[60%] px-4 py-2 rounded-2xl text-sm leading-relaxed ` +
          (isUser
            ? "bg-blue-600 text-white rounded-br-sm"
            : "bg-white border border-slate-200 text-slate-900 rounded-bl-sm")
        }
      >
        <div className={`text-xs mb-0.5 ${isUser ? "text-blue-100" : "text-slate-500"}`}>
          {isUser ? "you" : "interviewer"}
          {isSpeaking && <span className="ml-2">📢</span>}
        </div>
        <div>{text}</div>
      </div>
    </div>
  );
}
