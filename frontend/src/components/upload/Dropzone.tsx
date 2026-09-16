import { FileText, UploadCloud, X } from 'lucide-react'
import type { DragEvent } from 'react'
import { Face } from './Face'

const fmtSize = (bytes: number) =>
  bytes < 1_000_000 ? `${Math.round(bytes / 1000)} kB` : `${(bytes / 1_000_000).toFixed(1)} MB`

type DropzoneProps = {
  files: File[]
  dragging: boolean
  busy: boolean
  onDragStage: (dragging: boolean) => void
  onPick: (files: File[]) => void
  onRemove: (file: File) => void
}

// Path 3: your own PDF(s). The <label> makes the whole area click-to-open the hidden input;
// dropping or picking again appends (dedup by name+size lives in UploadView), it never replaces.
export function Dropzone({ files, dragging, busy, onDragStage, onPick, onRemove }: DropzoneProps) {
  return (
    <Face label="Upload PDF" hint="parsed locally, nothing leaves this machine">
      <label
        htmlFor="pdf"
        onDragOver={(e: DragEvent<HTMLLabelElement>) => {
          e.preventDefault()
          onDragStage(true)
        }}
        onDragLeave={() => onDragStage(false)}
        onDrop={(e) => {
          e.preventDefault()
          onDragStage(false)
          onPick(Array.from(e.dataTransfer.files))
        }}
        className={`flex flex-1 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-10 text-center transition-colors ${
          dragging ? 'border-ring bg-primary/10' : 'border-border hover:bg-muted/40'
        } ${busy ? 'pointer-events-none opacity-60' : ''}`}
      >
        {files.length > 0 ? (
          <>
            <FileText className="size-6 text-primary" />
            <span className="text-sm font-medium">
              {files.length} file{files.length === 1 ? '' : 's'} selected
            </span>
            <span className="text-xs text-muted-foreground">click or drop to add more</span>
          </>
        ) : (
          <>
            <UploadCloud className={`size-6 ${dragging ? 'text-primary' : 'text-muted-foreground'}`} />
            <span className="text-sm font-medium">…or upload your own annual report PDF</span>
            <span className="text-xs text-muted-foreground">drop it here or click to browse</span>
          </>
        )}
        <input
          id="pdf"
          type="file"
          accept="application/pdf"
          multiple
          className="sr-only"
          disabled={busy}
          onChange={(e) => {
            onPick(Array.from(e.target.files ?? []))
            e.target.value = ''
          }}
        />
      </label>
      {files.length > 0 && (
        <ul className="max-h-40 space-y-1 overflow-y-auto pr-0.5">
          {files.map((f) => (
            <li
              key={`${f.name}:${f.size}`}
              className="flex items-center gap-2 rounded-lg border border-border bg-background/50 px-2.5 py-1.5 text-sm"
            >
              <span className="min-w-0 flex-1 truncate">{f.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground">{fmtSize(f.size)}</span>
              <button
                type="button"
                aria-label={`Remove ${f.name}`}
                disabled={busy}
                onClick={() => onRemove(f)}
                className="shrink-0 rounded-sm hover:bg-muted"
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Face>
  )
}
