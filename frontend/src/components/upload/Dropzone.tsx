import { FileText, UploadCloud } from 'lucide-react'
import type { DragEvent } from 'react'
import { Face } from './Face'

const fmtSize = (bytes: number) =>
  bytes < 1_000_000 ? `${Math.round(bytes / 1000)} kB` : `${(bytes / 1_000_000).toFixed(1)} MB`

type DropzoneProps = {
  file: File | null
  dragging: boolean
  busy: boolean
  onDragStage: (dragging: boolean) => void
  onPick: (file: File | undefined) => void
}

// Path 3: your own PDF. The <label> makes the whole area click-to-open the hidden input.
export function Dropzone({ file, dragging, busy, onDragStage, onPick }: DropzoneProps) {
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
          onPick(e.dataTransfer.files[0])
        }}
        className={`flex flex-1 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-10 text-center transition-colors ${
          dragging ? 'border-ring bg-primary/10' : 'border-border hover:bg-muted/40'
        } ${busy ? 'pointer-events-none opacity-60' : ''}`}
      >
        {file ? (
          <>
            <FileText className="size-6 text-primary" />
            <span className="max-w-full truncate text-sm font-medium">{file.name}</span>
            <span className="text-xs text-muted-foreground">{fmtSize(file.size)} · click or drop to replace</span>
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
          className="sr-only"
          disabled={busy}
          onChange={(e) => onPick(e.target.files?.[0])}
        />
      </label>
    </Face>
  )
}
