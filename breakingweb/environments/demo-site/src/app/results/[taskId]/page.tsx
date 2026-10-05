import fs from "fs";
import path from "path";
import TrajectoryPage from "./TrajectoryPage";

export const dynamicParams = false;

export async function generateStaticParams() {
  try {
    const taskIds = new Set<string>();

    const summaryPath = path.join(process.cwd(), "public", "results", "summary.json");
    if (fs.existsSync(summaryPath)) {
      const summary = JSON.parse(fs.readFileSync(summaryPath, "utf-8"));
      for (const task of summary.tasks || []) {
        if (task?.task_id) {
          taskIds.add(task.task_id);
        }
      }
    }

    const fixturesManifestPath = path.join(process.cwd(), "public", "fixtures", "gmail", "_manifest.json");
    if (fs.existsSync(fixturesManifestPath)) {
      const manifest = JSON.parse(fs.readFileSync(fixturesManifestPath, "utf-8"));
      for (const task of manifest || []) {
        if (task?.task_id) {
          taskIds.add(task.task_id);
        }
      }
    }

    return Array.from(taskIds).sort().map((taskId) => ({ taskId }));
  } catch {
    return [];
  }
}

export default async function Page({ params }: { params: Promise<{ taskId: string }> }) {
  const { taskId } = await params;
  return <TrajectoryPage taskId={taskId} />;
}
