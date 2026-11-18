import { Moon, Sun } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { getTheme, toggleTheme } from '@/lib/theme';

export function ThemeToggle() {
  const [theme, setThemeState] = useState(getTheme);

  const isDark = theme === 'dark';
  const ariaLabel = isDark ? 'Passer en mode clair' : 'Passer en mode sombre';

  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      className="size-9 shrink-0 rounded-full"
      aria-label={ariaLabel}
      onClick={() => setThemeState(toggleTheme())}
    >
      {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}