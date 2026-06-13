/* Grok2API — theme (light / dark) */
(function () {
  var KEY = 'grok2api_theme';

  function systemTheme() {
    try {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } catch {
      return 'light';
    }
  }

  function storedTheme() {
    try {
      var value = localStorage.getItem(KEY);
      return value === 'dark' || value === 'light' ? value : '';
    } catch {
      return '';
    }
  }

  function resolveTheme() {
    return storedTheme() || systemTheme();
  }

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.style.colorScheme = theme;
  }

  apply(resolveTheme());

  function syncToggle(btn) {
    if (!btn) return;
    var isDark = (document.documentElement.getAttribute('data-theme') || 'light') === 'dark';
    btn.setAttribute('aria-pressed', isDark ? 'true' : 'false');
    btn.setAttribute('data-theme-state', isDark ? 'dark' : 'light');
    var sun = btn.querySelector('.theme-icon-sun');
    var moon = btn.querySelector('.theme-icon-moon');
    if (sun) sun.hidden = isDark;
    if (moon) moon.hidden = !isDark;
  }

  window.Theme = {
    get: function () {
      return document.documentElement.getAttribute('data-theme') || 'light';
    },
    set: function (theme) {
      if (theme !== 'dark' && theme !== 'light') return;
      try {
        localStorage.setItem(KEY, theme);
      } catch {}
      apply(theme);
      document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: theme } }));
    },
    toggle: function () {
      this.set(this.get() === 'dark' ? 'light' : 'dark');
    },
    syncToggle: syncToggle,
    initToggle: function (btn) {
      if (!btn || btn.dataset.themeBound === '1') return;
      btn.dataset.themeBound = '1';
      syncToggle(btn);
      btn.addEventListener('click', function () {
        Theme.toggle();
      });
      document.addEventListener('themechange', function () {
        syncToggle(btn);
      });
    },
  };

  try {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (event) {
      if (storedTheme()) return;
      apply(event.matches ? 'dark' : 'light');
      document.dispatchEvent(new CustomEvent('themechange'));
    });
  } catch {}
})();
