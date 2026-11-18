import { useQuery } from '@tanstack/react-query';

import { listLibraryOptions } from '@/api/client/@tanstack/react-query.gen';
import type { EpisodeStatus, LibrarySeriesResponse } from '@/api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

function getEpisodeStatusLabel(status: EpisodeStatus): { label: string; className: string } {
  switch (status) {
    case 'pending':
      return { label: 'En attente', className: 'text-muted-foreground' };
    case 'downloading':
      return { label: 'Téléchargement…', className: 'text-blue-600 dark:text-blue-400' };
    case 'completed':
      return { label: 'Téléchargé', className: 'text-emerald-700 dark:text-emerald-400' };
    case 'failed':
      return { label: 'Échec', className: 'text-destructive' };
    case 'skipped':
      return { label: 'Ignoré', className: 'text-muted-foreground' };
    default: {
      const exhaustiveCheck: never = status;
      return exhaustiveCheck;
    }
  }
}

export function LibraryPanel() {
  const libraryQuery = useQuery({
    ...listLibraryOptions(),
    refetchInterval: 4000,
  });

  const seriesList: LibrarySeriesResponse[] = libraryQuery.data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bibliothèque</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {libraryQuery.isLoading && (
          <p className="text-sm text-muted-foreground">Chargement de la bibliothèque…</p>
        )}

        {libraryQuery.isError && (
          <p className="text-sm text-destructive">
            Impossible de charger la bibliothèque.
          </p>
        )}

        {!libraryQuery.isLoading && !libraryQuery.isError && seriesList.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Aucune série dans la bibliothèque.
          </p>
        )}

        {seriesList.length > 0 && (
          <div className="space-y-4">
            {seriesList.map((series) => (
              <div key={series.id} className="space-y-2">
                <h3 className="text-base font-semibold">{series.title}</h3>
                <div className="ml-3 border-l pl-4 space-y-3">
                  {series.seasons.map((season) => (
                    <div key={season.id} className="space-y-1.5">
                      <h4 className="text-sm font-medium text-muted-foreground">
                        Saison {season.number} ({season.episodes.length} épisodes)
                      </h4>
                      <ul className="ml-2 border-l pl-3 space-y-1">
                        {season.episodes.map((ep) => {
                          const statusInfo = getEpisodeStatusLabel(ep.status);
                          return (
                            <li
                              key={ep.id}
                              className="flex flex-wrap items-center justify-between gap-2 text-sm py-0.5"
                            >
                              <div className="min-w-0 flex-1">
                                <span>
                                  Épisode {String(ep.number).padStart(2, '0')}
                                  {ep.title ? ` — ${ep.title}` : ''}
                                </span>
                                {ep.file_path && (
                                  <span
                                    className="ml-2 text-xs text-muted-foreground font-mono"
                                    title={ep.file_path}
                                  >
                                    {ep.file_path}
                                  </span>
                                )}
                                {ep.error_message && (
                                  <span className="ml-2 text-xs text-destructive">
                                    ({ep.error_message})
                                  </span>
                                )}
                              </div>
                              <span className={`text-xs font-medium ${statusInfo.className}`}>
                                {statusInfo.label}
                              </span>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
