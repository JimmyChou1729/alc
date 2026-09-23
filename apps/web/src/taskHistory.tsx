export type HistoryJob = {
  id: string;
  display_title: string;
  source_label: string;
  source_type?: string;
  external?: boolean;
  created: number;
  completed?: number | null;
  spec: { title?: string };
};

const collator = new Intl.Collator("zh-CN", {
  numeric: true,
  sensitivity: "base",
});

export function selectHistory<T extends HistoryJob>(
  jobs: T[],
  query: string,
  origin: string,
  inputType: string,
  sort: string,
): T[] {
  const needle = query.trim().toLocaleLowerCase();
  const [field, direction] = sort.split(":");
  const sign = direction === "asc" ? 1 : -1;
  return jobs
    .filter((job) => {
      const text = [job.display_title, job.source_label, job.spec.title]
        .filter(Boolean)
        .join("\n")
        .toLocaleLowerCase();
      return (
        (!needle || text.includes(needle)) &&
        (origin === "all" || (job.external ? "agent" : "web") === origin) &&
        (inputType === "all" ||
          (job.source_type && !["unknown", "file"].includes(job.source_type)
            ? job.source_type
            : "other") === inputType)
      );
    })
    .sort((a, b) => {
      let order = 0;
      if (field === "name") {
        order = collator.compare(
          a.display_title || a.spec.title || "",
          b.display_title || b.spec.title || "",
        );
      } else if (field === "completed") {
        const aTime = a.completed,
          bTime = b.completed;
        if (aTime == null || bTime == null) {
          if (aTime != null) return -1;
          if (bTime != null) return 1;
        } else order = aTime - bTime;
      } else order = a.created - b.created;
      return sign * order || b.created - a.created || a.id.localeCompare(b.id);
    });
}
