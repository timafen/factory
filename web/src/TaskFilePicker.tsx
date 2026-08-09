import { Paperclip, X } from "lucide-react";
import React from "react";

export function TaskFilePicker({
  files,
  onChange,
  error,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  error?: string;
}) {
	const validate = (next: File[]) => {
		if (next.length > 5) return "Можно прикрепить не больше 5 файлов.";
		const oversized = next.find((file) => file.size > 10 * 1024 * 1024);
		if (oversized) return `Файл «${oversized.name}» больше 10 МБ.`;
		const executable = next.find((file) => /\.(exe|com|bat|cmd|msi|scr|ps1|sh|app|apk)$/i.test(file.name));
		if (executable) return `Файл «${executable.name}» исполняемый и не принимается.`;
		return undefined;
	};
	const [localError, setLocalError] = React.useState<string>();
  return (
    <div className="task-file-picker">
      <input
        id="task-files"
        type="file"
        multiple
        aria-label="Files"
        onChange={(event) => {
		  const next = [...files, ...Array.from(event.currentTarget.files ?? [])];
		  const problem = validate(next); setLocalError(problem);
		  if (!problem) onChange(next);
          event.currentTarget.value = "";
        }}
      />
      <span className="field-hint">Choose screenshots or files to include with this task.</span>
      {files.length > 0 && (
        <ul className="task-file-list" aria-label="Selected files">
          {files.map((file, index) => (
            <li key={`${file.name}-${file.size}-${file.lastModified}-${index}`}>
              <Paperclip size={15} aria-hidden="true" />
              <span>{file.name}</span>
              <span className="task-file-size">{formatFileSize(file.size)}</span>
              <button
                type="button"
                className="icon-button"
                aria-label={`Remove ${file.name}`}
                onClick={() => onChange(files.filter((_, candidate) => candidate !== index))}
              ><X size={15} /></button>
            </li>
          ))}
        </ul>
      )}
	  {(error || localError) && <span className="field-error">{error || localError}</span>}
    </div>
  );
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
