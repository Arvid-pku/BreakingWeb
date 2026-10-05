export interface TaskMeta {
  task_id: string;
  title: string;
  difficulty: string;
  primary_primitives: string[];
  secondary_primitives: string[];
  expected_steps: number;
  time_limit_seconds: number;
}

export interface TaskDetail extends TaskMeta {
  instruction: string;
  eval_check_descriptions: string[];
  start_path?: string;
  state: Record<string, unknown>;
}

interface RawTaskShape {
  task_id: string;
  title: string;
  difficulty: string;
  primary_primitives?: string[];
  secondary_primitives?: string[];
  primitives?: string[];
  expected_steps?: number;
  time_limit_seconds?: number;
  time_limit?: number;
  instruction?: string;
  eval_check_descriptions?: string[];
  start_path?: string;
  state?: Record<string, unknown>;
}

function normalizeTaskMeta(raw: RawTaskShape): TaskMeta {
  return {
    task_id: raw.task_id,
    title: raw.title,
    difficulty: raw.difficulty,
    primary_primitives: raw.primary_primitives ?? raw.primitives ?? [],
    secondary_primitives: raw.secondary_primitives ?? [],
    expected_steps: raw.expected_steps ?? 0,
    time_limit_seconds: raw.time_limit_seconds ?? raw.time_limit ?? 0,
  };
}

function normalizeTaskDetail(raw: RawTaskShape): TaskDetail {
  return {
    ...normalizeTaskMeta(raw),
    instruction: raw.instruction ?? "",
    eval_check_descriptions: raw.eval_check_descriptions ?? [],
    start_path: raw.start_path,
    state: raw.state ?? {},
  };
}

export async function loadTaskManifest(): Promise<TaskMeta[]> {
  try {
    const res = await fetch("/fixtures/gmail/_manifest.json");
    if (!res.ok) return [];
    const data = (await res.json()) as RawTaskShape[];
    return data.map(normalizeTaskMeta);
  } catch {
    return [];
  }
}

export async function loadTaskDetail(taskId: string): Promise<TaskDetail | null> {
  try {
    const res = await fetch(`/fixtures/gmail/${taskId}.json`);
    if (!res.ok) return null;
    const data = (await res.json()) as RawTaskShape;
    return normalizeTaskDetail(data);
  } catch {
    return null;
  }
}
