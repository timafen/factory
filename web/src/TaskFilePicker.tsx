import { Paperclip, X } from "lucide-react";

export function TaskFilePicker({
  files,
  onChange,
  error,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  error?: string;
}) {
  return (
    <div className="task-file-picker">
      <input
        id="task-files"
        type="file"
        multiple
        aria-label="Files"
        onChange={(event) => {
          onChange([...files, ...Array.from(event.currentTarget.files ?? [])]);
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
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
