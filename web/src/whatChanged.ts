const EMPTY_CHANGELOG = "Проверка прошла, подробностей исполнитель не оставил.";

// Only lines whose format is owned by the delivery protocol belong here. Unknown
// lines stay visible: losing a useful sentence is worse than showing extra detail.
const INTERNAL_REPORT_LINES = [
  /^\s*(?:[-*]\s*)?(?:BRANCH|HEAD|PUSHED|TRY):\s*\S.*$/i,
  /^\s*(?:PASS|APPROVE|REQUEST CHANGES)\s*[.!]?\s*$/i,
];

export function whatChanged(verdict?: string, result?: string, error?: string) {
  const source = verdict?.trim() || result?.trim() || error?.trim();
  if (!source) return "";
  const visible = source
    .split(/\r?\n/)
    .filter((line) => !INTERNAL_REPORT_LINES.some((pattern) => pattern.test(line)))
    .join("\n")
    .trim();
  return visible || EMPTY_CHANGELOG;
}
