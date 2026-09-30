import { statusLabel, statusTone, type StatusTone } from "@/lib/format";

const TONE_CLASS: Record<StatusTone, string> = {
  neutral: "badge",
  moving: "badge badge-moving",
  active: "badge badge-active",
  done: "badge badge-done",
  problem: "badge badge-problem",
};

export function Badge({ tone, children }: { tone: StatusTone; children: React.ReactNode }) {
  return <span className={TONE_CLASS[tone]}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={statusTone(status)}>{statusLabel(status)}</Badge>;
}
