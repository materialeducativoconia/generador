export type SeriesStatus = 'outlining' | 'outline_ready' | 'outline_failed' | 'generating' | 'needs_attention' | 'ready'
export type LessonStatus = 'pending' | 'queued' | 'generating' | 'generated' | 'failed' | 'edited' | 'approved'
export type Genre = 'coloring_book' | 'worksheets' | 'tutorial' | 'lesson_series'
export type ApiErrorBody = { code: string; message: string }

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

/** The cover agent's output: a public image plus the palette placeholders reuse while it paints. */
export type CoverFields = {
  cover_url: string | null
  cover_status: JobStatus | null
  cover_palette: [string, string, string] | null
}

export type Design = {
  theme: 'juego' | 'cuaderno' | 'editorial' | 'metodo' | 'ciencia' | 'clasico'
  palette: [string, string, string]
  ornament: 'estrellas' | 'notas' | 'hojas' | 'puntos' | 'formas' | 'ninguno'
  rationale?: string
}

export type SeriesSummary = CoverFields & {
  design: Design | null
  id: string
  title: string | null
  topic: string
  genre: Genre | null
  status: SeriesStatus
  lesson_count: number
  done: number
  created_at: string
}

export type LessonSummary = {
  id: string
  position: number
  title: string
  objectives: string[]
  key_points: string[]
  status: LessonStatus
  last_error: ApiErrorBody | null
  content_json: { blocks: Block[] } | null
  diagrams?: Record<string, string>  // block id -> SVG drawn by the backend, same as the PDF
}

export type Source = { title: string; url: string }

export type Series = CoverFields & {
  design: Design | null
  assets: Record<string, string>
  credits: Record<string, string>
  research: { needed: boolean; facts: number; sources: Source[] } | null
  id: string
  title: string | null
  topic: string
  genre: Genre | null
  status: SeriesStatus
  version: number
  audience: { label: string }
  lessons: LessonSummary[]
  outline_error: ApiErrorBody | null
}

export type Progress = {
  status: SeriesStatus
  version: number
  counts: Record<LessonStatus | 'total', number>
  lessons: { id: string; position: number; title: string; status: LessonStatus; error: ApiErrorBody | null }[]
  latest_export: { id: string; status: ExportStatus; stale: boolean } | null
  images: { total: number; done: number; active: number; failed: number }
  poll_after_ms: number | null
}

export type ExportStatus = 'queued' | 'running' | 'succeeded' | 'failed'
export type Preflight = { rating: 'lista' | 'aceptable' | 'baja'; min_dpi: number | null; issues: string[]; vector: number }

export type Quality = {
  verdict: 'lista' | 'revisar' | 'pendiente'
  reasons: string[]
  text: { score: number | null; reviewed: number; sections: number; fixed: number; issues: { section: number; issue: string }[] }
  facts: { needed: boolean; facts: number; sources: number } | null
  art: { total: number; done: number; active: number; failed: number }
  print: (Preflight & { layout?: { fixed: string[]; issues: string[] } }) | null
}

export type Export = {
  id: string
  status: ExportStatus
  page_count: number | null
  download_url: string | null
  cover_download_url: string | null
  preflight: Preflight | null
}

export type Block =
  | { id: string; type: 'heading'; level: 2 | 3; text: string }
  | { id: string; type: 'paragraph'; text: string }
  | { id: string; type: 'list'; style: 'bullet' | 'number' | 'check'; items: string[] }
  | { id: string; type: 'callout'; variant: 'key_idea' | 'tip' | 'warning' | 'fun_fact'; title?: string | null; text: string }
  | { id: string; type: 'table'; caption?: string | null; headers: string[]; rows: string[][] }
  | { id: string; type: 'example'; title?: string | null; text: string }
  | { id: string; type: 'activity'; title: string; duration_minutes?: number | null; materials: string[]; steps: string[] }
  | {
      id: string
      type: 'exercise'
      kind: 'open' | 'multiple_choice' | 'true_false' | 'fill_blank'
      prompt: string
      options: string[]
      answer?: string | null
      explanation?: string | null
      answer_space_lines: number
    }
  | { id: string; type: 'keyboard'; start: string; octaves: number; highlight: string[]; show_labels: boolean; caption?: string | null }
  | { id: string; type: 'tracing'; text: string; repeat: number; instruction?: string | null }
  | { id: string; type: 'letter_grid'; targets: string[]; distractors: string[]; rows: number; cols: number; instruction?: string | null }
  | { id: string; type: 'image'; kind: 'line_art' | 'illustration' | 'photo' | 'diagram'; subject: string; caption?: string | null; size: 'full' | 'half' | 'small'; asset_id?: string | null }
  | { id: string; type: 'writing_lines'; lines: number; label?: string | null }
  | { id: string; type: 'page_break' }
  | { id: string; type: DiagramType; caption?: string | null }

export const DIAGRAM_TYPES = ['staff', 'timeline', 'cycle', 'bar_chart', 'number_line', 'fraction', 'clock'] as const
export type DiagramType = (typeof DIAGRAM_TYPES)[number]

export type Lesson = LessonSummary & {
  series_id: string
  assets: Record<string, string>
  credits: Record<string, string>
  content_json: { schema_version: 1; summary: string; blocks: Block[] } | null
}
