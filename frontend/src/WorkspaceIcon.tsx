const paths: Record<string, string> = {
  dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  intake: 'M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5',
  evidence: 'M19 8a7 7 0 1 1-14 0 7 7 0 0 1 14 0 M8 14l-2 8 6-3 6 3-2-8',
  experiences: 'M3 7h18v14H3z M8 7V3h8v4 M3 12h18 M10 12v3h4v-3',
  projects: 'M3 6h7l2 3h9v12H3z M3 6V3h7l2 3',
  skills: 'm13 2-9 12h7l-1 8 10-13h-8z',
  archive: 'M3 3h18v5H3z M5 8v13h14V8 M9 12h6',
  jobs: 'M4 5h16v16H4z M8 5V3h8v2 M8 10h8 M8 14h8 M8 18h5',
  resumes: 'M5 3h10l4 4v14H5z M14 3v5h5 M9 12h6 M9 16h6',
  applications: 'M3 12 21 3l-7 18-3-8z M11 13 21 3',
  profile: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 21v-3a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v3',
  settings: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2',
  arrow: 'M5 12h14 m-5-5 5 5-5 5',
}

export default function WorkspaceIcon({ name, className = '' }: { name: string; className?: string }) {
  return <svg className={`workspace-icon ${className}`} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] ?? paths.resumes} /></svg>
}
