import { cn } from 'cn';

export type StatusBadgeKind = 'done' | 'running' | 'waiting' | 'failed' | 'skipped';

type KindStyles = {
  defaultLabel: string;
  badgeClassName: string;
  dotClassName: string;
};

function kindStyles(kind: StatusBadgeKind): KindStyles {
  switch (kind) {
    case 'done':
      return {
        defaultLabel: 'Terminé',
        badgeClassName: 'bg-ad-ok-bg text-ad-ok-fg',
        dotClassName: 'bg-ad-ok-fg',
      };
    case 'running':
      return {
        defaultLabel: 'En cours',
        badgeClassName: 'bg-accent text-accent-foreground',
        dotClassName: 'bg-ad-live ad-pulse',
      };
    case 'waiting':
      return {
        defaultLabel: 'En attente',
        badgeClassName: 'bg-muted text-muted-foreground',
        dotClassName: 'bg-ad-muted',
      };
    case 'failed':
      return {
        defaultLabel: 'Échec',
        badgeClassName: 'bg-ad-err-bg text-ad-err-fg',
        dotClassName: 'bg-ad-err-fg',
      };
    case 'skipped':
      return {
        defaultLabel: 'Ignoré',
        badgeClassName: 'bg-muted text-muted-foreground',
        dotClassName: 'bg-ad-muted',
      };
    default: {
      const exhaustiveCheck: never = kind;
      return exhaustiveCheck;
    }
  }
}

export type StatusBadgeProps = {
  kind: StatusBadgeKind;
  label?: string;
  className?: string;
};

export function StatusBadge({ kind, label, className }: StatusBadgeProps) {
  const styles = kindStyles(kind);
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium',
        styles.badgeClassName,
        className,
      )}
    >
      <span
        className={cn('size-1.5 shrink-0 rounded-full', styles.dotClassName)}
        aria-hidden
      />
      {label ?? styles.defaultLabel}
    </span>
  );
}