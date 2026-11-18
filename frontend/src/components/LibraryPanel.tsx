import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown } from 'lucide-react';

import { listLibraryOptions } from '@/api/client/@tanstack/react-query.gen';
import type { EpisodeStatus, LibrarySeriesResponse } from '@/api/client';
import { StatusBadge, type StatusBadgeKind } from '@/components/StatusBadge';
import { cn } from 'cn';

function titleInitials(title: string): string {
  const words = title.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return '?';
  }
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase();
  }
  return (words[0][0] + words[1][0]).toUpperCase();
}

function countEpisodesOnDisk(seriesList: LibrarySeriesResponse[]): number {
  let count = 0;
  for (const series of seriesList) {
    for (const season of series.seasons) {
      for (const ep of season.episodes) {
        if (ep.status === 'completed') {
          count += 1;
        }
      }
    }
  }
  return count;
}

function episodeStatusBadge(
  status: EpisodeStatus,
): { kind: StatusBadgeKind; label?: string } {
  switch (status) {
    case 'downloading':
      return { kind: 'running', label: 'Téléchargement…' };
    case 'pending':
      return { kind: 'waiting' };
    case 'completed':
      return { kind: 'done', label: 'Téléchargé' };
    case 'failed':
      return { kind: 'failed' };
    case 'skipped':
      return { kind: 'skipped' };
    default: {
      const exhaustiveCheck: never = status;
      return exhaustiveCheck;
    }
  }
}

function seriesActivityBadge(
  series: LibrarySeriesResponse,
): { kind: StatusBadgeKind; label?: string } | null {
  let hasDownloading = false;
  let hasFailed = false;
  for (const season of series.seasons) {
    for (const ep of season.episodes) {
      if (ep.status === 'downloading') {
        hasDownloading = true;
      }
      if (ep.status === 'failed') {
        hasFailed = true;
      }
    }
  }
  if (hasDownloading) {
    return { kind: 'running', label: 'En cours' };
  }
  if (hasFailed) {
    return { kind: 'failed' };
  }
  return null;
}

function seriesEpisodeCount(series: LibrarySeriesResponse): number {
  return series.seasons.reduce((sum, season) => sum + season.episodes.length, 0);
}

export function LibraryPanel() {
  const libraryQuery = useQuery({
    ...listLibraryOptions(),
    refetchInterval: 4000,
  });

  const seriesList: LibrarySeriesResponse[] = libraryQuery.data ?? [];
  const [openIds, setOpenIds] = useState<Record<string, boolean>>({});
  const didInitOpen = useRef(false);

  useEffect(() => {
    if (didInitOpen.current || seriesList.length === 0) {
      return;
    }
    didInitOpen.current = true;
    setOpenIds({ [seriesList[0].id]: true });
  }, [seriesList]);

  const episodesOnDisk = countEpisodesOnDisk(seriesList);

  const toggleSeries = (id: string) => {
    setOpenIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <section className="rounded-[7px] border border-border bg-card">
      <header className="border-b border-border px-5 py-4">
        <h2 className="font-display text-lg font-bold tracking-tight text-foreground">
          Bibliothèque
        </h2>
        <p className="mt-0.5 text-sm text-ad-muted">
          {seriesList.length === 0
            ? 'Aucune série'
            : `${seriesList.length} série${seriesList.length > 1 ? 's' : ''} · ${episodesOnDisk} épisode${episodesOnDisk > 1 ? 's' : ''} sur disque`}
        </p>
      </header>

      <div className="space-y-2 px-5 py-4">
        {libraryQuery.isLoading && (
          <p className="text-sm text-ad-muted">Chargement de la bibliothèque…</p>
        )}

        {libraryQuery.isError && (
          <p className="text-sm text-ad-err-fg">Impossible de charger la bibliothèque.</p>
        )}

        {!libraryQuery.isLoading && !libraryQuery.isError && seriesList.length === 0 && (
          <div className="rounded-md border border-dashed border-border bg-ad-inset/40 px-4 py-8 text-center text-sm text-ad-muted">
            Aucune série dans la bibliothèque.
          </div>
        )}

        {seriesList.length > 0 ? (
          <ul className="space-y-2">
            {seriesList.map((series) => {
              const isOpen = openIds[series.id] ?? false;
              const activityBadge = seriesActivityBadge(series);
              const episodeCount = seriesEpisodeCount(series);
              const seasonCount = series.seasons.length;

              return (
                <li
                  key={series.id}
                  className="overflow-hidden rounded-md border border-border bg-card"
                >
                  <button
                    type="button"
                    className="flex w-full items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-ad-inset/50"
                    aria-expanded={isOpen}
                    onClick={() => toggleSeries(series.id)}
                  >
                    <span
                      className="flex size-11 shrink-0 items-center justify-center rounded-md bg-ad-tile text-sm font-semibold text-primary-foreground"
                      aria-hidden
                    >
                      {titleInitials(series.title)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-foreground">
                        {series.title}
                      </span>
                      <span className="mt-0.5 block text-xs text-ad-muted">
                        {seasonCount} saison{seasonCount > 1 ? 's' : ''} · {episodeCount}{' '}
                        épisode{episodeCount > 1 ? 's' : ''}
                      </span>
                    </span>
                    {activityBadge ? (
                      <StatusBadge
                        kind={activityBadge.kind}
                        label={activityBadge.label}
                        className="hidden sm:inline-flex"
                      />
                    ) : null}
                    <ChevronDown
                      className={cn(
                        'size-4 shrink-0 text-ad-muted transition-transform',
                        isOpen && 'rotate-180',
                      )}
                      aria-hidden
                    />
                  </button>

                  {isOpen ? (
                    <div className="border-t border-border px-3 pb-3 pt-2">
                      {series.seasons.map((season) => (
                        <div key={season.id} className="py-2 first:pt-1">
                          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ad-muted">
                            Saison {season.number}
                          </p>
                          <ul className="space-y-1">
                            {season.episodes.map((ep) => {
                              const badge = episodeStatusBadge(ep.status);
                              return (
                                <li
                                  key={ep.id}
                                  className="grid grid-cols-[64px_1fr_auto] items-start gap-x-2 gap-y-0.5 rounded-sm px-1 py-1.5 text-sm hover:bg-ad-inset/40"
                                >
                                  <span className="font-mono text-xs text-ad-muted">
                                    {String(ep.number).padStart(2, '0')}
                                  </span>
                                  <div className="min-w-0">
                                    <span className="text-foreground">
                                      {ep.title ? ep.title : `Épisode ${ep.number}`}
                                    </span>
                                    {ep.file_path ? (
                                      <p
                                        className="mt-0.5 truncate font-mono text-xs text-ad-muted"
                                        title={ep.file_path}
                                      >
                                        {ep.file_path}
                                      </p>
                                    ) : null}
                                    {ep.error_message ? (
                                      <p className="mt-0.5 text-xs text-ad-err-fg">
                                        {ep.error_message}
                                      </p>
                                    ) : null}
                                  </div>
                                  <StatusBadge kind={badge.kind} label={badge.label} />
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </section>
  );
}