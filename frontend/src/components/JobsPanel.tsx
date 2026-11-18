import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CircleAlert, X } from 'lucide-react';

import { formatApiError } from '@/api/errors';
import {
  dismissCompletedJobsMutation,
  dismissJobMutation,
  listJobsOptions,
  listJobsQueryKey,
  listLibraryQueryKey,
  retryFailedEpisodesMutation,
} from '@/api/client/@tanstack/react-query.gen';
import type { JobResponse, JobStatus } from '@/api/client';
import { StatusBadge, type StatusBadgeKind } from '@/components/StatusBadge';
import { Button } from '@/components/ui/button';
import { cn } from 'cn';

function getHttpStatusFromApiError(error: unknown): number | undefined {
  if (!error || typeof error !== 'object') {
    return undefined;
  }
  if ('status' in error && typeof error.status === 'number') {
    return error.status;
  }
  if ('response' in error) {
    const response = (error as { response?: { status?: number } }).response;
    if (response && typeof response.status === 'number') {
      return response.status;
    }
  }
  return undefined;
}

function formatDismissJobError(error: unknown): string {
  const status = getHttpStatusFromApiError(error);
  if (status === 409) {
    return 'Impossible de fermer une tâche en cours.';
  }
  if (status === 404) {
    return 'Tâche introuvable.';
  }
  const detail = formatApiError(error, '');
  if (/cannot dismiss/i.test(detail)) {
    return 'Impossible de fermer une tâche en cours.';
  }
  if (/job not found/i.test(detail)) {
    return 'Tâche introuvable.';
  }
  return formatApiError(error, 'Impossible de fermer la tâche.');
}

function jobStatusBadge(job: JobResponse): { kind: StatusBadgeKind; label?: string } {
  switch (job.status) {
    case 'completed':
      return { kind: 'done', label: 'Terminé' };
    case 'running':
      return { kind: 'running', label: 'En cours' };
    case 'pending':
      return { kind: 'waiting', label: 'En attente' };
    case 'failed': {
      const isPartial = job.completed_episodes > 0 && job.failed_episodes > 0;
      return { kind: 'failed', label: isPartial ? 'Échec partiel' : 'Échec' };
    }
    default: {
      const exhaustiveCheck: never = job.status;
      return exhaustiveCheck;
    }
  }
}

function canDismissJob(status: JobStatus): boolean {
  switch (status) {
    case 'completed':
    case 'failed':
      return true;
    case 'pending':
    case 'running':
      return false;
    default: {
      const exhaustiveCheck: never = status;
      return exhaustiveCheck;
    }
  }
}

function parseJobSeasonLabel(sourceUrl: string): { title: string; season: string | null } {
  try {
    const { pathname } = new URL(sourceUrl);
    const match = pathname.match(/\/season\/([^/]+)\/(\d+)/i);
    if (match) {
      const title = match[1].replace(/-/g, ' ');
      return { title, season: match[2] };
    }
  } catch {
    // fall through
  }
  return { title: sourceUrl, season: null };
}

function ErrorStrip({ children }: { children: ReactNode }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2.5 rounded-md bg-ad-err-bg px-3.5 py-3 text-sm leading-snug text-ad-err-fg"
    >
      <CircleAlert className="mt-0.5 size-4 shrink-0 text-ad-err-fg" aria-hidden />
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  );
}

export function JobsPanel() {
  const queryClient = useQueryClient();
  const [retryError, setRetryError] = useState<string | null>(null);
  const [dismissError, setDismissError] = useState<string | null>(null);

  const jobsQuery = useQuery({
    ...listJobsOptions(),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      const hasActive = jobs.some(
        (job) => job.status === 'pending' || job.status === 'running',
      );
      return hasActive ? 1500 : 5000;
    },
  });

  const dismissMutation = useMutation({
    ...dismissJobMutation(),
    onSuccess: async () => {
      setDismissError(null);
      await queryClient.invalidateQueries({ queryKey: listJobsQueryKey() });
    },
    onError: (error) => {
      setDismissError(formatDismissJobError(error));
    },
  });

  const dismissCompletedMutation = useMutation({
    ...dismissCompletedJobsMutation(),
    onSuccess: async () => {
      setDismissError(null);
      await queryClient.invalidateQueries({ queryKey: listJobsQueryKey() });
    },
    onError: (error) => {
      setDismissError(formatDismissJobError(error));
    },
  });

  const retryMutation = useMutation({
    ...retryFailedEpisodesMutation(),
    onSuccess: async () => {
      setRetryError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: listJobsQueryKey() }),
        queryClient.invalidateQueries({ queryKey: listLibraryQueryKey() }),
      ]);
    },
    onError: (error) => {
      setRetryError(formatApiError(error, 'Impossible de relancer les épisodes échoués.'));
    },
  });

  const jobs: JobResponse[] = jobsQuery.data ?? [];
  const hasCompleted = jobs.some((job) => job.status === 'completed');
  const dismissBusy = dismissMutation.isPending || dismissCompletedMutation.isPending;

  return (
    <section className="rounded-[7px] border border-border bg-card">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <h2 className="font-display text-lg font-bold tracking-tight text-foreground">
            Tâches
          </h2>
          <p className="mt-0.5 text-sm text-ad-muted">
            {jobs.length === 0
              ? 'Aucune tâche active'
              : `${jobs.length} tâche${jobs.length > 1 ? 's' : ''}`}
          </p>
        </div>
        {hasCompleted ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="shrink-0 text-ad-soft"
            disabled={dismissBusy}
            onClick={() => dismissCompletedMutation.mutate({})}
          >
            Fermer les terminées
          </Button>
        ) : null}
      </header>

      <div className="space-y-3 px-5 py-4">
        {jobsQuery.isLoading && (
          <p className="text-sm text-ad-muted">Chargement des tâches…</p>
        )}

        {jobsQuery.isError && (
          <p className="text-sm text-ad-err-fg">
            Impossible de charger les tâches de téléchargement.
          </p>
        )}

        {dismissError ? <ErrorStrip>{dismissError}</ErrorStrip> : null}
        {retryError ? <ErrorStrip>{retryError}</ErrorStrip> : null}

        {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length === 0 && (
          <div className="rounded-md border border-dashed border-border bg-ad-inset/40 px-4 py-8 text-center text-sm text-ad-muted">
            Aucune tâche pour le moment.
          </div>
        )}

        {jobs.length > 0 ? (
          <ul className="space-y-3">
            {jobs.map((job) => {
              const badge = jobStatusBadge(job);
              const { title, season } = parseJobSeasonLabel(job.source_url);
              const seasonProgressPct =
                job.total_episodes > 0
                  ? Math.round((job.completed_episodes / job.total_episodes) * 100)
                  : 0;
              const episodePercent =
                typeof job.episode_progress_percent === 'number'
                  ? Math.max(0, Math.min(100, Math.round(job.episode_progress_percent)))
                  : null;
              const showEpisodeProgress =
                job.status === 'running' && job.current_episode_number != null;
              const canRetry =
                Boolean(job.season_id) &&
                job.failed_episodes > 0 &&
                job.status !== 'pending' &&
                job.status !== 'running';
              const showDismiss = canDismissJob(job.status);

              return (
                <li
                  key={job.id}
                  className="rounded-md border border-border bg-card p-4 text-sm"
                >
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <p className="font-medium text-foreground">
                          {title}
                          {season != null ? (
                            <span className="text-ad-muted"> · Saison {season}</span>
                          ) : null}
                        </p>
                        <StatusBadge kind={badge.kind} label={badge.label} />
                      </div>

                      <p
                        className="truncate font-mono text-xs text-ad-muted"
                        title={job.source_url}
                      >
                        {job.source_url}
                      </p>

                      <div className="flex items-center justify-between gap-2 text-xs text-ad-muted">
                        <span>Saison</span>
                        <span className="font-mono text-foreground">
                          {job.completed_episodes}/{job.total_episodes}
                          <span className="ml-2 text-ad-muted">{seasonProgressPct}%</span>
                        </span>
                      </div>
                      <div className="h-1 w-full overflow-hidden rounded-full bg-ad-track">
                        <div
                          className="h-full bg-ad-live transition-all"
                          style={{ width: `${seasonProgressPct}%` }}
                        />
                      </div>

                      {showEpisodeProgress ? (
                        <div className="space-y-1 pt-0.5">
                          <div className="flex items-center justify-between gap-2 text-xs text-ad-muted">
                            <span>
                              Épisode {job.current_episode_number}
                              {episodePercent == null ? '…' : ''}
                            </span>
                            <span className="font-mono">
                              {episodePercent == null ? '…' : `${episodePercent}%`}
                            </span>
                          </div>
                          <div className="h-1 w-full overflow-hidden rounded-full bg-ad-track">
                            {episodePercent == null ? (
                              <div className="h-full w-1/3 rounded-full bg-ad-live/80 ad-pulse" />
                            ) : (
                              <div
                                className="h-full bg-ad-live transition-all"
                                style={{ width: `${episodePercent}%` }}
                              />
                            )}
                          </div>
                        </div>
                      ) : null}

                      {(job.failed_episodes > 0 || job.error_message) && (
                        <div
                          className={cn(
                            'mt-2 flex flex-wrap items-center justify-between gap-2 rounded-md bg-ad-err-bg px-3 py-2.5 text-xs text-ad-err-fg',
                          )}
                        >
                          <p className="min-w-0 flex-1">
                            {job.failed_episodes > 0
                              ? `${job.failed_episodes} épisode(s) en échec`
                              : ''}
                            {job.failed_episodes > 0 && job.error_message ? ' — ' : ''}
                            {job.error_message ?? ''}
                          </p>
                          {canRetry && job.season_id ? (
                            <Button
                              type="button"
                              size="xs"
                              variant="outline"
                              className="border-ad-err-fg/30 bg-transparent text-ad-err-fg hover:bg-ad-err-bg"
                              disabled={retryMutation.isPending}
                              onClick={() => {
                                const seasonId = job.season_id;
                                if (seasonId) {
                                  retryMutation.mutate({ body: { season_id: seasonId } });
                                }
                              }}
                            >
                              Réessayer
                            </Button>
                          ) : null}
                        </div>
                      )}

                      <p className="text-xs text-ad-muted">
                        Adaptateur :{' '}
                        <span className="font-mono text-ad-soft">{job.adapter_id}</span>
                      </p>
                    </div>

                    {showDismiss ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        className="shrink-0 text-ad-muted hover:text-foreground"
                        disabled={dismissBusy}
                        aria-label="Fermer la tâche"
                        onClick={() =>
                          dismissMutation.mutate({ path: { id: job.id } })
                        }
                      >
                        <X className="size-3.5" />
                      </Button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </section>
  );
}