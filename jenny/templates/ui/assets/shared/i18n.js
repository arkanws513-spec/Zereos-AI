/* Zereos language system: Arabic is the first-run default. The user can change
   language in-app; the choice is persisted locally and takes precedence over
   the Android/browser locale. */
export class I18n {
  constructor() {
    this.locale = localStorage.getItem('locale') || localStorage.getItem('zereos.locale') || 'ar';
    this.translations = {};
  }

  detectLocale() {
    const nav = navigator.language || 'ar';
    const supported = ['ar', 'en', 'it'];
    return supported.find(s => s === nav) || supported.find(s => nav.startsWith(s)) || 'ar';
  }

  async load(locale) {
    if (!['ar', 'en', 'it'].includes(locale)) locale = 'ar';
    this.locale = locale;
    try { localStorage.setItem('locale', locale); localStorage.setItem('zereos.locale', locale); } catch (_) {}
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr';
    try {
      const res = await fetch(`/html-mobile/assets/i18n/${locale}.json`);
      if (!res.ok) {
        // Risposta non valida: non sovrascrivere translations[locale] con dati
        // errati.
        console.warn(`Failed to load locale ${locale}: HTTP ${res.status}`);
        return;
      }
      this.translations[locale] = await res.json();
      // English is the complete fallback catalog. Missing keys in another
      // locale must never render the raw i18n key in the UI.
      if (locale !== 'en' && !this.translations.en) {
        try {
          const fallback = await fetch('/html-mobile/assets/i18n/en.json');
          if (fallback.ok) this.translations.en = await fallback.json();
        } catch (_) { /* selected locale remains usable on its own */ }
      }
    } catch (e) {
      console.warn(`Failed to load locale ${locale}:`, e);
    }
  }

  t(key, params) {
    const keys = key.split('.');
    const resolve = (catalog) => {
      let value = catalog;
      for (const k of keys) {
        if (!value || typeof value !== 'object') return undefined;
        value = value[k];
      }
      return typeof value === 'string' ? value : undefined;
    };
    let value = resolve(this.translations[this.locale]);
    if (value === undefined && this.locale !== 'en') {
      value = resolve(this.translations.en);
    }
    if (value === undefined) return key;
    if (params) {
      return value.replace(/\{(\w+)\}/g, (_, name) => params[name] ?? ('{' + name + '}'));
    }
    return value;
  }
}

export const i18n = new I18n();
