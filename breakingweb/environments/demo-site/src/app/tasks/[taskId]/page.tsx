import fs from "fs";
import path from "path";
import { TaskDetailClient } from "@/components/tasks/TaskDetailClient";

export const dynamicParams = false;

export async function generateStaticParams() {
  try {
    const fixturesDir = path.join(process.cwd(), "public", "fixtures", "gmail");
    const fixtureTaskIds = fs
      .readdirSync(fixturesDir)
      .filter((name: string) => name.endsWith(".json") && name !== "_manifest.json")
      .map((name: string) => name.replace(/\.json$/, ""));

    if (fixtureTaskIds.length > 0) {
      return fixtureTaskIds.map((taskId: string) => ({ taskId }));
    }

    const manifestPath = path.join(fixturesDir, "_manifest.json");
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    return manifest.map((t: { task_id: string }) => ({ taskId: t.task_id }));
  } catch {
    return [];
  }
}

export default async function TaskDetailPage({ params }: { params: Promise<{ taskId: string }> }) {
  const { taskId } = await params;
  return <TaskDetailClient taskId={taskId} />;
}
