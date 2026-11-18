import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { JobsPanel } from '@/components/JobsPanel';
import { LibraryPanel } from '@/components/LibraryPanel';
import { UrlDownloadForm } from '@/components/UrlDownloadForm';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 1000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-background text-foreground">
        <main className="mx-auto max-w-4xl px-4 py-8 space-y-6">
          <header className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight">Anime Downloader</h1>
            <p className="text-sm text-muted-foreground">
              Prévisualisez une saison, lancez le téléchargement et suivez votre bibliothèque.
            </p>
          </header>

          <UrlDownloadForm />
          <JobsPanel />
          <LibraryPanel />
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;
