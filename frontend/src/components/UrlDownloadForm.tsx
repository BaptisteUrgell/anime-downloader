import { useState } from 'react';
import { useForm } from '@tanstack/react-form';
import { useMutation, useQueryClient } from '@tanstack/react-query';
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

const urlSchema = z.string().trim().url('Veuillez saisir une URL valide.');

const formSchema = z.object({
  url: urlSchema,
});

type PreviewState =
  | { status: 'idle' }
  | { status: 'ok'; url: string; preview: SeasonPreviewResponse }
  | { status: 'error'; url: string; message: string };

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
    <Card>
      <CardHeader>
        <CardTitle>Nouveau téléchargement</CardTitle>
        <CardDescription>
          Collez l&apos;URL d&apos;une saison puis quittez le champ pour prévisualiser les épisodes.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            void form.handleSubmit();
          }}
          className="space-y-3"
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
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Input
                      id={field.name}
                      name={field.name}
                      type="url"
                      placeholder="https://demo.local/season/demo-show/1"
                      value={field.state.value}
                      aria-invalid={Boolean(fieldError || isPreviewError)}
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
                    <p className="text-sm text-destructive">{fieldError}</p>
                  )}

                  {!previewMutation.isPending && !fieldError && isPreviewOk && (
                    <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
                      « {previewState.preview.episode_count} épisodes seront téléchargés » —{' '}
                      {previewState.preview.series_title} (Saison {previewState.preview.season_number})
                    </p>
                  )}

                  {!previewMutation.isPending && !fieldError && isPreviewError && (
                    <p className="text-sm text-destructive">{previewState.message}</p>
                  )}

                  {submitError && (
                    <p className="text-sm text-destructive">{submitError}</p>
                  )}
                </>
              );
            }}
          </form.Field>
        </form>
      </CardContent>
    </Card>
  );
}
