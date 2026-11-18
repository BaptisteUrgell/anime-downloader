import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { formatApiError } from '@/api/errors';
import {
  listJobsOptions,
  listJobsQueryKey,
  listLibraryQueryKey,
  retryFailedEpisodesMutation,
} from '@/api/client/@tanstack/react-query.gen';
import type { JobResponse, JobStatus } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

function getJobStatusBadge(status: JobStatus): { label: string; className: string } {
  switch (status) {
    case 'pending':
      return {
        label: 'En attente',
        className: 'bg-muted text-muted-foreground',
      };
    case 'running':
      return {
        label: 'En cours',
        className: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
      };
    case 'completed':
      return {
        label: 'Terminé',
        className: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
      };
    case 'failed':
      return {
        label: 'Échec',
        className: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
      };
    default: {
      const exhaustiveCheck: never = status;
      return exhaustiveCheck;
    }
  }
}

export function JobsPanel() {
  const queryClient = useQueryClient();
  const [retryError, setRetryError] = useState<string | null>(null);

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

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tâches de téléchargement</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {jobsQuery.isLoading && (
          <p className="text-sm text-muted-foreground">Chargement des tâches…</p>
        )}

        {jobsQuery.isError && (
          <p className="text-sm text-destructive">
            Impossible de charger les tâches de téléchargement.
          </p>
        )}

        {retryError && <p className="text-sm text-destructive">{retryError}</p>}

        {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Aucune tâche pour le moment.
          </p>
        )}

        {jobs.length > 0 && (
          <ul className="space-y-2">
            {jobs.map((job) => {
              const badge = getJobStatusBadge(job.status);
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

              return (
                <li
                  key={job.id}
                  className="rounded-lg border p-3 text-sm space-y-2"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium" title={job.source_url}>
                        {job.source_url}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Adaptateur : {job.adapter_id}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-medium">
                        {job.completed_episodes}/{job.total_episodes}
                      </span>
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}
                      >
                        {badge.label}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>Saison</span>
                      <span className="font-mono">{seasonProgressPct}%</span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                      <div
                        className="h-full bg-primary transition-all"
                        style={{ width: `${seasonProgressPct}%` }}
                      />
                    </div>
                  </div>

                  {showEpisodeProgress && (
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>
                          Épisode {job.current_episode_number}
                          {episodePercent == null ? '…' : ''}
                        </span>
                        <span className="font-mono">
                          {episodePercent == null ? '…' : `${episodePercent}%`}
                        </span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                        {episodePercent == null ? (
                          <div className="h-full w-1/3 animate-pulse rounded-full bg-sky-500/80" />
                        ) : (
                          <div
                            className="h-full bg-sky-500 transition-all"
                            style={{ width: `${episodePercent}%` }}
                          />
                        )}
                      </div>
                    </div>
                  )}

                  {(job.failed_episodes > 0 || job.error_message) && (
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-xs text-destructive">
                        {job.failed_episodes > 0
                          ? `${job.failed_episodes} épisode(s) en échec`
                          : ''}
                        {job.failed_episodes > 0 && job.error_message ? ' — ' : ''}
                        {job.error_message ?? ''}
                      </p>
                      {canRetry && job.season_id && (
                        <Button
                          type="button"
                          size="xs"
                          variant="outline"
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
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
