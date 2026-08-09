import { useQuery } from "@tanstack/react-query";

// У фабрики два репозитория, и путать их дорого — экран обязан называть
// проект сам, а не заставлять владельца догадываться по заголовку.

const HUMAN: [string, string][] = [
  ["timafen/factory", "Фабрика"],
  ["timafen/tarser-operations", "Торговая система"],
];

function humanise(identity: string): string {
  for (const [key, name] of HUMAN) if (identity.includes(key)) return name;
  return identity.split("/").pop() ?? identity;
}

/** id репозитория -> человеческое имя проекта. */
// eslint-disable-next-line react-refresh/only-export-components
export function useProjectName(): (repoId?: string) => string {
  const repos = useQuery({
    queryKey: ["repo-names"],
    queryFn: async (): Promise<Record<string, string>> => {
      const r = await fetch("/api/v1/repositories");
      if (!r.ok) return {};
      const d = (await r.json()) as { repositories?: { id: string; remote_identity: string }[] };
      const out: Record<string, string> = {};
      for (const x of d.repositories ?? []) out[x.id] = humanise(x.remote_identity || "");
      return out;
    },
    staleTime: 600000,
  });
  return (repoId?: string) => (repoId ? (repos.data ?? {})[repoId] ?? "" : "");
}

export function ProjectTag({ name }: { name: string }) {
  if (!name) return null;
  return (
    <span
      title="Проект, к которому относится работа"
      style={{
        fontSize: 11, padding: "2px 8px", borderRadius: 999, whiteSpace: "nowrap",
        background: "#1b2436", color: "#9fc0ea", border: "1px solid #2f4568",
      }}
    >{name}</span>
  );
}
