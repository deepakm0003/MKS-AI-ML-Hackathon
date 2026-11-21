import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { Badge, Card, ErrorState, Skeleton } from "../components/ui";

const TOPIC_LABEL: Record<string, string> = {
  outlook: "Outlook", market: "Market", mix: "Mix", ev_shift: "EV shift", capacity: "Capacity",
  procurement: "Procurement", segmentation: "Segmentation", macro_risk: "Macro risk", actions: "Actions",
};

/** Executive briefing - sentences assembled by the backend from computed facts (no LLM), each with its sources. */
export function BriefingPanel({ filtered }: { filtered: boolean }) {
  const st = useApi((s) => api.briefing(s), []);
  return (
    <Card
      title="Planning briefing"
      subtitle="Generated from computed facts - every sentence lists the datasets it was built from"
      actions={filtered ? <Badge tone="neutral" icon="info">Company-wide</Badge> : undefined}
    >
      {st.status === "loading" && <Skeleton lines={7} />}
      {st.status === "error" && <ErrorState error={st.error} onRetry={st.retry} />}
      {st.status === "success" && (
        <ul className="briefing">
          {st.data.briefing.map((b) => (
            <li key={b.topic} className="briefing__item">
              <span className="briefing__topic">{TOPIC_LABEL[b.topic] ?? b.topic}</span>
              <p>{b.text}</p>
              <span className="briefing__src mono">{b.sources.join(" · ")}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
