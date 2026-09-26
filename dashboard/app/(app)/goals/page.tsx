import { GoalsClient } from "@/components/GoalsClient";
import { apiGet } from "@/lib/api";
import type { CategoryOut, GoalOut } from "@/lib/types";

export default async function GoalsPage() {
  const [goals, categories] = await Promise.all([
    apiGet<GoalOut[]>("/v1/goals"),
    apiGet<CategoryOut[]>("/v1/categories"),
  ]);

  return (
    <div>
      <h1 className="mb-6 text-lg font-semibold">Goals</h1>
      <GoalsClient initialGoals={goals} categories={categories.filter((c) => !c.is_system)} />
    </div>
  );
}
