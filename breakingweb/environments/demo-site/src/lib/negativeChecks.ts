export interface NegativeCheckEntry {
  task_id: string;
  task_title: string;
  difficulty: string;
  desc: string;
  penalty: number;
  triggered: boolean;
}

export interface NegativeChecksData {
  total_tasks_with_negatives: number;
  total_negative_checks: number;
  triggered_count: number;
  checks: NegativeCheckEntry[];
}

export async function fetchNegativeChecks(): Promise<NegativeChecksData | null> {
  try {
    const res = await fetch("/results/negative-checks.json");
    if (!res.ok) return null;
    return (await res.json()) as NegativeChecksData;
  } catch {
    return null;
  }
}
