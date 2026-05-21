import type { GrowthPointDict } from "../api/types";

interface Props {
  growth_point: GrowthPointDict;
}

export function InlineCorrection({ growth_point: gp }: Props) {
  const tagColor =
    gp.tag === "vocab" ? "bg-blue-100 text-blue-800" : "bg-amber-100 text-amber-800";
  return (
    <div className="ml-4 mt-1 mb-3 border-l-2 border-slate-300 pl-3 text-sm">
      <span className={`inline-block text-xs uppercase font-semibold rounded px-1.5 py-0.5 mr-2 ${tagColor}`}>
        {gp.tag}
      </span>
      <s className="text-slate-500">{gp.user_utterance}</s>
      <span className="text-slate-400 mx-2">→</span>
      <span className="text-slate-900 font-medium">{gp.corrected_version}</span>
      <div className="text-slate-600 italic mt-1 text-xs">{gp.explanation}</div>
    </div>
  );
}
