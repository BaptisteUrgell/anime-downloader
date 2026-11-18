import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';

import { listJobsOptions } from '@/api/client/@tanstack/react-query.gen';
import type { JobStatus } from '@/api/client';
import { ThemeToggle } from '@/components/ThemeToggle';

function isActiveJobStatus(status: JobStatus): boolean {
  switch (status) {
    case 'pending':
    case 'running':
      return true;
    case 'completed':
    case 'failed':
      return false;
    default: {
      const exhaustiveCheck: never = status;
      return exhaustiveCheck;
    }
  }
}

export function AppHeader() {
  const jobsQuery = useQuery({
    ...listJobsOptions(),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      const hasActive = jobs.some((job) => isActiveJobStatus(job.status));
      return hasActive ? 1500 : 5000;
    },
  });

  const jobs = jobsQuery.data ?? [];
  const showLive = jobs.some((job) => isActiveJobStatus(job.status));

  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex max-w-[1160px] items-center justify-between gap-4 px-6 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <div
            className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground"
            aria-hidden
          >
            <Download className="size-[18px]" strokeWidth={2.25} />
          </div>
          <h1 className="font-display text-lg font-bold tracking-tight text-foreground">
            Anime Downloader
          </h1>
        </div>
        <div className="flex items-center gap-3">
          {showLive ? (
            <div
              className="flex items-center gap-2 text-sm text-ad-live"
              role="status"
              aria-live="polite"
            >
              <span className="size-2 shrink-0 rounded-full bg-ad-live ad-pulse" aria-hidden />
              <span className="hidden sm:inline">Actualisation en direct</span>
            </div>
          ) : null}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}