/* Zereos language system: Arabic is the first-run default. The user can change
   language in-app; the choice is persisted locally and takes precedence over
   the Android/browser locale. */
export class I18n {
  constructor() {
    this.locale = localStorage.getItem('zereos.locale') || 'ar';
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
    localStorage.setItem('zereos.locale', locale);
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr';
    try {
      const res = await fetch(`/assets/i18n/${locale}.json`);
      if (!res.ok) {
        // Risposta non valida: non sovrascrivere translations[locale] con dati
        // errati.
        console.warn(`Failed to load locale ${locale}: HTTP ${res.status}`);
        return;
      }
      this.translations[locale] = await res.json();
    } catch (e) {
      console.warn(`Failed to load locale ${locale}:`, e);
    }
  }

  t(key, params) {
    const keys = key.split('.');
    let value = this.translations[this.locale];
    for (const k of keys) {
      if (!value || typeof value !== 'object') return key;
      value = value[k];
    }
    if (typeof value !== 'string') return key;
    if (params) {
      return value.replace(/\{(\w+)\}/g, (_, name) => params[name] ?? `{${name}}`);
    }
    return value;
  }
}

export const i18n = new I18n();
