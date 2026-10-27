export type SeriesStatus = 'outlining' | 'outline_ready' | 'outline_failed' | 'generating' | 'needs_attention' | 'ready'
export type LessonStatus = 'pending' | 'queued' | 'generating' | 'generated' | 'failed' | 'edited' | 'approved'
export type Genre = 'coloring_book' | 'worksheets' | 'tutorial' | 'lesson_series'
export type ApiErrorBody = { code: string; message: string }

export type SeriesSummary = {
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
}

export type Series = {
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
  latest_export: { id: string; status: ExportStatus } | null
  poll_after_ms: number | null
}

export type ExportStatus = 'queued' | 'running' | 'succeeded' | 'failed'
export type Export = { id: string; status: ExportStatus; page_count: number | null; download_url: string | null }

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
  | { id: string; type: 'image'; kind: 'line_art' | 'illustration' | 'photo' | 'diagram'; subject: string; caption?: string | null; size: 'full' | 'half' | 'small' }
  | { id: string; type: 'writing_lines'; lines: number; label?: string | null }
  | { id: string; type: 'page_break' }

export type Lesson = LessonSummary & {
  series_id: string
  content_json: { schema_version: 1; summary: string; blocks: Block[] } | null
}
