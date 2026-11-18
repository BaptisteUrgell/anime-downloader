import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AppHeader } from '@/components/AppHeader';
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
      <div className="min-h-screen bg-background text-foreground font-sans">
        <AppHeader />
        <main className="mx-auto flex max-w-[1160px] flex-col gap-8 px-6 py-10 pb-16">
          <UrlDownloadForm />
          <div className="flex flex-wrap items-start gap-8">
            <div className="min-w-0 flex-1 basis-[360px]">
              <JobsPanel />
            </div>
            <div className="min-w-0 flex-[999_1_560px]">
              <LibraryPanel />
            </div>
          </div>
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;