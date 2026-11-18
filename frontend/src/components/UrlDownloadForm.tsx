import { useState, type ReactNode } from 'react';
import { useForm } from '@tanstack/react-form';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CircleAlert, CircleCheck } from 'lucide-react';
import { z } from 'zod';

import { formatApiError, formatZodError } from '@/api/errors';
import {
  createJobMutation,
  listJobsQueryKey,
  listLibraryQueryKey,
  previewSeasonMutation,
} from '@/api/client/@tanstack/react-query.gen';
import type { SeasonPreviewResponse } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from 'cn';

const urlSchema = z.string().trim().url('Veuillez saisir une URL valide.');

const formSchema = z.object({
  url: urlSchema,
});

type PreviewState =
  | { status: 'idle' }
  | { status: 'ok'; url: string; preview: SeasonPreviewResponse }
  | { status: 'error'; url: string; message: string };

function StatusStrip({
  variant,
  children,
  className,
}: {
  variant: 'success' | 'error';
  children: ReactNode;
  className?: string;
}) {
  const Icon = variant === 'success' ? CircleCheck : CircleAlert;
  return (
    <div
      role={variant === 'error' ? 'alert' : 'status'}
      className={cn(
        'flex items-start gap-2.5 rounded-md px-3.5 py-3 text-sm leading-snug',
        variant === 'success' && 'bg-ad-inset text-foreground',
        variant === 'error' && 'bg-ad-err-bg text-ad-err-fg',
        className,
      )}
    >
      <Icon
        className={cn(
          'mt-0.5 size-4 shrink-0',
          variant === 'success' ? 'text-ad-ok-fg' : 'text-ad-err-fg',
        )}
        aria-hidden
      />
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  );
}

export function UrlDownloadForm() {
  const queryClient = useQueryClient();
  const [previewState, setPreviewState] = useState<PreviewState>({ status: 'idle' });
  const [submitError, setSubmitError] = useState<string | null>(null);

  const previewMutation = useMutation({
    ...previewSeasonMutation(),
    onSuccess: (preview, variables) => {
      const url = variables.body.url;
      setPreviewState({
        status: 'ok',
        url,
        preview,
      });
    },
    onError: (error, variables) => {
      setPreviewState({
        status: 'error',
        url: variables.body.url,
        message: formatApiError(error, 'Impossible de prévisualiser cette URL.'),
      });
    },
  });

  const createJob = useMutation({
    ...createJobMutation(),
    onSuccess: async () => {
      setSubmitError(null);
      setPreviewState({ status: 'idle' });
      form.reset();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: listJobsQueryKey() }),
        queryClient.invalidateQueries({ queryKey: listLibraryQueryKey() }),
      ]);
    },
    onError: (error) => {
      setSubmitError(formatApiError(error, 'Impossible de démarrer le téléchargement.'));
    },
  });

  const form = useForm({
    defaultValues: {
      url: '',
    },
    validators: {
      onSubmit: formSchema,
    },
    onSubmit: async ({ value }) => {
      const trimmed = value.url.trim();
      if (previewState.status !== 'ok' || previewState.url !== trimmed) {
        return;
      }
      setSubmitError(null);
      await createJob.mutateAsync({ body: { url: trimmed } });
    },
  });

  return (
    <section className="rounded-[7px] border border-border bg-card p-8">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#2c5c8e] dark:text-[#76a9dd]">
        Nouveau téléchargement
      </p>
      <h1 className="mt-2 font-display text-[32px] font-normal tracking-tight text-foreground">
        Ajouter une saison
      </h1>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          e.stopPropagation();
          void form.handleSubmit();
        }}
        className="mt-6 space-y-3"
      >
        <form.Field
          name="url"
          validators={{
            onBlur: urlSchema,
          }}
        >
          {(field) => {
            const trimmed = field.state.value.trim();
            const isPreviewOk =
              previewState.status === 'ok' && previewState.url === trimmed;
            const isPreviewError =
              previewState.status === 'error' && previewState.url === trimmed;
            const fieldError =
              field.state.meta.isTouched && field.state.meta.errors.length > 0
                ? formatZodError(field.state.meta.errors[0])
                : null;

            return (
              <>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <Input
                    id={field.name}
                    name={field.name}
                    type="url"
                    placeholder="https://demo.local/season/demo-show/1"
                    value={field.state.value}
                    aria-invalid={Boolean(fieldError || isPreviewError)}
                    className="h-12 font-mono text-sm md:text-sm"
                    onChange={(e) => {
                      const nextValue = e.target.value;
                      field.handleChange(nextValue);
                      setSubmitError(null);
                      if (previewState.status !== 'idle' && previewState.url !== nextValue.trim()) {
                        setPreviewState({ status: 'idle' });
                      }
                    }}
                    onBlur={() => {
                      field.handleBlur();
                      const current = field.state.value.trim();
                      if (!current) {
                        setPreviewState({ status: 'idle' });
                        return;
                      }
                      const parsed = urlSchema.safeParse(current);
                      if (!parsed.success) {
                        setPreviewState({ status: 'idle' });
                        return;
                      }
                      setSubmitError(null);
                      previewMutation.mutate({ body: { url: parsed.data } });
                    }}
                  />
                  <Button
                    type="submit"
                    className="h-12 shrink-0 rounded-full px-8 sm:w-auto"
                    disabled={
                      !isPreviewOk ||
                      previewMutation.isPending ||
                      createJob.isPending
                    }
                  >
                    {createJob.isPending ? 'Envoi…' : 'Télécharger'}
                  </Button>
                </div>

                {previewMutation.isPending && (
                  <p className="text-sm text-muted-foreground">
                    Prévisualisation en cours…
                  </p>
                )}

                {!previewMutation.isPending && fieldError && (
                  <StatusStrip variant="error">{fieldError}</StatusStrip>
                )}

                {!previewMutation.isPending && !fieldError && isPreviewOk && (
                  <StatusStrip variant="success">
                    « {previewState.preview.episode_count} épisodes seront téléchargés » —{' '}
                    {previewState.preview.series_title} (Saison{' '}
                    {previewState.preview.season_number})
                  </StatusStrip>
                )}

                {!previewMutation.isPending && !fieldError && isPreviewError && (
                  <StatusStrip variant="error">{previewState.message}</StatusStrip>
                )}

                {submitError && (
                  <StatusStrip variant="error">{submitError}</StatusStrip>
                )}
              </>
            );
          }}
        </form.Field>
      </form>
    </section>
  );
}