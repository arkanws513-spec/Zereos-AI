// Pre-render bootstrap — must run synchronously before the body renders to
// avoid a flash of the wrong theme / locale (FOUC). Extracted from two inline
// <script> blocks in index.html so the SPA can be served with a
// script-src 'self' CSP (M1). Load WITHOUT defer, in <head>, so it still
// executes before the rest of the document (same timing as the old inline).
(function () {
  // `localStorage` puo' sollevare (dati del sito bloccati, anteprima): qui
  // un errore fermerebbe l'intero script, e con lui il tema e la lingua
  // della pagina. Si legge null e non si scrive;
  // la stessa regola di `readStorage` in shared/utils.js.
  function read(key) {
    try { return localStorage.getItem(key); } catch (_) { return null; }
  }
  function write(key, value) {
    try { localStorage.setItem(key, value); } catch (_) { /* storage non disponibile */ }
  }
  var THEMES = ['chanel', 'synthwave', 'kyoto', 'sticker', 'comic', 'y2k', 'stone'];
  // Come MIGRATION in shared/theme.js: i modi di una volta e gli id italiani
  // dei temi fino al 25/09/2026.
  var MIGRATION = { dark: 'chanel', light: 'stone', match: 'chanel', fumetto: 'comic', pietra: 'stone' };
  // Il default e' DEFAULT_THEME di shared/theme.js (qui non si importa: lo
  // script e' classico e deve girare prima di tutto il resto). Dal 27/09/2026
  // e' `synthwave`; chi aveva gia' un `tc-theme` salvato lo tiene.
  var t = read('tc-theme') || 'synthwave';
  t = MIGRATION[t] || t;
  if (THEMES.indexOf(t) === -1) t = 'synthwave';
  write('tc-theme', t);
  document.documentElement.setAttribute('data-theme', t);

  // Zereos AI mobile defaults to Arabic. Respect an explicit saved locale, and
  // otherwise keep the Arabic shell instead of silently replacing it with the
  // device language before the i18n module starts.
  var locale = read('locale') || 'ar';
  if (locale !== 'ar' && locale !== 'en' && locale !== 'it') locale = 'ar';
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr';

  // Mascotte: anti-flash come il tema. La verità a runtime resta in
  // shared/mascot.js (localStorage + evento 'mascotchange'); qui solo
  // l'attributo iniziale su <html> per evitare che lampeggi visibile prima
  // che mobile-jenny.js applichi la preferenza "non visibile" (il lato non
  // serve: la mascotte è creata da JS e posizionata prima del primo paint).
  // Le chiavi si chiamavano `jenny-mascotte-*` fino al 25/09/2026: finche'
  // shared/mascot.js non le ha copiate, qui si legge anche il nome vecchio.
  var mascotVisible = read('jenny-mascot-visible') || read('jenny-mascotte-visible');
  if (mascotVisible === '0') {
    document.documentElement.setAttribute('data-mascot-hidden', '1');
  }
  // Taglia: stesso anti-flash. Il default CSS vale solo per 'sm', quindi senza
  // questo chi ha scelto un'altra taglia vedrebbe Jenny comparire piccola e
  // poi ridimensionarsi. Le misure sono duplicate da MASCOT_SIZES in
  // shared/mascot.js — qui non si possono importare moduli.
  var mascotSizes = { sm: '120px', md: '160px', lg: '210px' };
  var mascotSize = mascotSizes[read('jenny-mascot-size') || read('jenny-mascotte-size')];
  if (mascotSize) {
    document.documentElement.style.setProperty('--jenny-size', mascotSize);
  }
})();
