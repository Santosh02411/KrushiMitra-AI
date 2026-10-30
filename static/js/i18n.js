// i18n.js — client-side translation for KrushiMitra AI's UI chrome (nav, footer,
// page headings, labels, buttons, static copy). Content that's built
// dynamically in JS from API responses (table rows, chat replies, admin
// panels) stays in English for now — see data-i18n usage in the
// templates for what's covered.
//
// Mechanism: every translatable element carries data-i18n="some.key".
// applyTranslations(lang) looks the key up in I18N[lang] (falling back
// to English for any missing key) and writes it into the element —
// textContent normally, or the given attribute if data-i18n-attr is set
// (e.g. data-i18n-attr="placeholder" for inputs).

const SUPPORTED_LANGS = ['en', 'hi', 'kn', 'mr', 'ta', 'te'];
const LANG_LABELS = { en: 'English', hi: 'हिन्दी', kn: 'ಕನ್ನಡ', mr: 'मराठी', ta: 'தமிழ்', te: 'తెలుగు' };

function getCurrentLang() {
  const stored = localStorage.getItem('krushi-lang');
  return SUPPORTED_LANGS.includes(stored) ? stored : 'en';
}

function applyTranslations(lang) {
  const dict = I18N[lang] || I18N.en;
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    const text = dict[key] ?? I18N.en[key];
    if (text === undefined) return;
    const attr = el.getAttribute('data-i18n-attr');
    if (attr) el.setAttribute(attr, text); else el.textContent = text;
  });
  document.documentElement.setAttribute('lang', lang);
}

function setLang(lang, opts) {
  if (!SUPPORTED_LANGS.includes(lang)) return;
  localStorage.setItem('krushi-lang', lang);
  applyTranslations(lang);
  if (!opts || opts.syncProfile !== false) syncLangToProfile(lang);
}

// Persists the choice to the signed-in user's profile (same field the
// Profile page's language dropdown already saves), best-effort — a
// logged-out visitor or a failed request just keeps the localStorage copy.
async function syncLangToProfile(lang) {
  try {
    const meRes = await fetch('/api/auth/me', { credentials: 'include' });
    const me = await meRes.json();
    if (!me.success || !me.user) return;
    if (me.user.preferred_language === lang) return;
    await fetch('/api/auth/profile', {
      method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preferred_language: lang }),
    });
  } catch (e) { /* localStorage copy is still the source of truth for this browser */ }
}

// Called once from initCommon() on every page: applies whatever language
// is already in localStorage immediately (no flash of English), then
// checks the signed-in user's saved preference and switches to that if
// it's different (e.g. first load on a new device after registering
// with a non-English preferred_language).
function initLanguage() {
  applyTranslations(getCurrentLang());

  const switcher = document.getElementById('lang-switcher');
  if (switcher) {
    switcher.innerHTML = SUPPORTED_LANGS.map(l => `<option value="${l}">${LANG_LABELS[l]}</option>`).join('');
    switcher.value = getCurrentLang();
    switcher.addEventListener('change', () => setLang(switcher.value));
  }

  fetch('/api/auth/me', { credentials: 'include' }).then(r => r.json()).then(data => {
    if (!data.success || !data.user || !data.user.preferred_language) return;
    const serverLang = data.user.preferred_language;
    if (SUPPORTED_LANGS.includes(serverLang) && serverLang !== getCurrentLang()) {
      localStorage.setItem('krushi-lang', serverLang);
      applyTranslations(serverLang);
      if (switcher) switcher.value = serverLang;
    }
  }).catch(() => { /* not logged in, or offline — localStorage value stands */ });
}

const I18N = {
  en: {
    'nav.decision': '✨ AI Farm Planner', 'nav.assistant': 'AI Assistant',
    'nav.recommend': 'Crop advisor', 'nav.soil': 'Soil', 'nav.market': 'Market', 'nav.dashboard': 'Dashboard',
    'nav.more': '☰ More', 'nav.yield': 'Yield', 'nav.fertilizer': 'Fertilizer', 'nav.profit': 'Profit',
    'nav.disease': 'Disease', 'nav.water': 'Irrigation', 'nav.calendar': 'Calendar', 'nav.records': 'Records',
    'nav.analytics': 'Analytics', 'nav.map': 'Map', 'nav.knowledge': 'Learn', 'nav.chat': 'AI Assistant',
    'nav.admin': 'Admin', 'nav.edit_profile': 'Edit profile', 'nav.logout': 'Logout',
    'nav.delete_account': 'Delete account permanently', 'nav.login_register': 'Login / Register',
    'footer.disclaimer': 'An agricultural decision-support tool. Recommendations are informational and '
      + 'should be combined with local agronomic advice, especially for high-value or first-time crops.',
    'footer.data_sources': 'Data sources: Open-Meteo (weather), browser GPS + reverse geocoding (location), '
      + 'real published agronomy datasets (crop/yield/market models), Google Gemini API (chatbot, if configured).',
    'common.loading': 'Loading…',
    'notif.panel_title': 'Alerts',
    'home.eyebrow': 'Live field reading', 'home.welcome': 'Welcome back',
    'home.lead': 'KrushiMitra AI reads your soil test values against live weather for your exact GPS location and a '
      + 'model trained on 2,200 real field samples across 22 crops — the panel on the right is pulling its '
      + 'numbers from that model right now, not from a script.',
    'home.cta_reading': 'Take a reading', 'home.cta_sources': 'See the data sources',
    'home.model_readout': 'Model readout', 'home.accuracy_label': 'crop model test accuracy',
    'home.training_samples': 'Training samples', 'home.crops_modeled': 'Crops modeled',
    'home.market_r2': 'Market model R²', 'home.weather_source': 'Weather source',
    'home.notif_eyebrow': 'Smart notifications', 'home.notif_heading': 'What needs your attention',
    'home.notif_body': 'Derived from your saved crop calendars and live weather — rain tomorrow, fertilizer '
      + 'due today, harvest approaching, and general disease-risk weather flags.',
    'home.announcements_eyebrow': 'Announcements', 'home.news_heading': 'News',
    'home.all_tools_eyebrow': 'All tools', 'home.jump_heading': 'Jump to a tool',
    'home.f_recommend': 'Recommendation + yield + profitability', 'home.f_soil_title': 'Soil health',
    'home.f_soil': 'Score, deficiencies, fertilizer', 'home.f_yield_title': 'Yield prediction',
    'home.f_yield': 'Expected tonnes for your area', 'home.f_market_title': 'Market price',
    'home.f_market': 'Real mandi prices + prediction', 'home.f_fertilizer': 'Quantity, cost, schedule',
    'home.f_profit': 'Income − expenses', 'home.f_disease_title': 'Disease check',
    'home.f_disease': 'Symptom-based reference', 'home.f_water': '7-day schedule',
    'home.f_calendar_title': 'Crop calendar', 'home.f_calendar': 'Sowing to harvest dates',
    'home.f_dashboard_title': 'Farm dashboard', 'home.f_dashboard': 'Your real charts',
    'home.f_map_title': 'Farm map', 'home.f_map': 'Location + nearby markets',
    'home.f_knowledge_title': 'Knowledge base', 'home.f_knowledge': 'Articles, schemes, practices',
    'home.f_chat': 'LLM chatbot (needs API key)',
    'page.records_eyebrow': 'Your data', 'page.records_heading': 'Farm records',
    'page.dashboard_eyebrow': 'Your data', 'page.dashboard_heading': 'Farm dashboard',
    'page.market_eyebrow': 'Step 3', 'page.market_heading': 'Market price',
    'page.soil_eyebrow': 'Step 2', 'page.soil_heading': 'Soil health analysis',
    'page.yield_eyebrow': 'Standalone tool', 'page.yield_heading': 'Yield prediction',
    'page.fertilizer_eyebrow': 'Step 4', 'page.fertilizer_heading': 'Fertilizer recommendation',
    'page.profit_eyebrow': 'Standalone tool', 'page.profit_heading': 'Profit estimation',
    'page.disease_eyebrow': 'Step 5', 'page.disease_heading': 'Disease check',
    'page.water_eyebrow': 'Step 2', 'page.water_heading': 'Irrigation schedule',
    'page.calendar_eyebrow': 'Step 6', 'page.calendar_heading': 'Crop calendar',
    'page.analytics_eyebrow': 'Your data, aggregated', 'page.analytics_heading': 'Analytics',
    'page.map_eyebrow': 'Free, no API key', 'page.map_heading': 'Interactive farm map',
    'page.knowledge_eyebrow': 'Reference', 'page.knowledge_heading': 'Farming knowledge base',
    'page.chat_eyebrow': 'Real LLM, needs a key', 'page.chat_heading': 'Ask KrushiMitra AI',
    'page.profile_eyebrow': 'Account settings', 'page.profile_heading': 'Profile',
    'page.recommend_eyebrow': 'Step 1', 'page.recommend_heading': 'Crop recommendation',
    'page.about_eyebrow': 'Honesty about data', 'page.about_heading': "What's real, and what's a labeled fallback",
    'page.admin_eyebrow': 'Admin only', 'page.admin_heading': 'Admin panel',
    'page.login_eyebrow': 'Sign in required', 'page.login_heading': 'Sign in to use KrushiMitra AI',
    'page.login_lead': "Every tool here — crop advisor, soil health, market prices, irrigation, and the "
      + "rest — is tied to your farm profile, so it's behind sign-in. Registering takes a minute and "
      + "there's no cost.",
    'auth.login_tab': 'Log in', 'auth.register_tab': 'Register', 'auth.forgot_tab': 'Forgot password',
    'auth.email': 'Email', 'auth.password': 'Password', 'auth.name': 'Name',
    'auth.password_min': 'Password (min. 8 characters)', 'auth.confirm_password': 'Confirm password',
    'auth.location': 'Location', 'auth.farm_size': 'Farm size (acres)', 'auth.soil_type': 'Soil type',
    'auth.preferred_language': 'Preferred language', 'auth.create_account': 'Create account',
    'auth.forgot_link': 'Forgot your password?', 'auth.no_account': "Don't have an account?",
    'auth.have_account': 'Already have an account?', 'auth.back_to_login': '← Back to log in',
    'auth.forgot_title': 'Reset your password', 'auth.send_code': 'Send code',
    'auth.verify_code': 'Verify code', 'auth.code_label': '6-digit code',
    'auth.new_password': 'New password', 'auth.confirm_new_password': 'Confirm new password',
    'auth.reset_password': 'Reset password',
    'auth.forgot_step1': "Step 1 of 3 — enter your account email and we'll send a 6-digit code to it.",
    'auth.forgot_step2': 'Step 2 of 3 — enter the 6-digit code sent to your email.',
    'auth.forgot_step3': 'Step 3 of 3 — code verified, set your new password.',
    'auth.email_setup_summary': 'Password reset',
    'auth.forgot_help_text': "A 6-digit code is emailed to your registered address when you request a "
      + "password reset. If it doesn't arrive within a minute or two, check your spam folder.",
    'about.whats_real': 'Built on real data, not guesses',
    'about.login_panel_body': 'Crop and yield recommendations come from real agricultural datasets and '
      + "trained models, not scripted responses. Live weather comes from Open-Meteo for your exact "
      + "location. Market prices are real recorded mandi data. Where something genuinely isn't available "
      + 'yet, KrushiMitra AI says so plainly instead of making up a number.',
    'auth.email_setup_body': 'If SMTP_HOST/SMTP_USER/SMTP_PASSWORD are set in .env, the 6-digit code is '
      + "emailed for real. Without that, there's no way to actually deliver an email, so the code is shown "
      + 'inline instead — clearly labeled as a fallback, not a substitute for real email. See .env.example '
      + 'for Gmail App Password setup, or run python scripts/test_email.py you@example.com to test your '
      + 'SMTP setup directly. Just edited .env? Restart the server — env vars are only read once, at startup.',
  },
  hi: {
    'nav.decision': '✨ AI खेती योजना', 'nav.assistant': 'AI सहायक',
    'nav.recommend': 'फ़सल सलाहकार', 'nav.soil': 'मिट्टी', 'nav.market': 'बाज़ार', 'nav.dashboard': 'डैशबोर्ड',
    'nav.more': '☰ और', 'nav.yield': 'उपज', 'nav.fertilizer': 'उर्वरक', 'nav.profit': 'लाभ',
    'nav.disease': 'रोग', 'nav.water': 'सिंचाई', 'nav.calendar': 'कैलेंडर', 'nav.records': 'रिकॉर्ड',
    'nav.analytics': 'विश्लेषण', 'nav.map': 'मानचित्र', 'nav.knowledge': 'सीखें', 'nav.chat': 'कृषि से पूछें',
    'nav.admin': 'व्यवस्थापक', 'nav.edit_profile': 'प्रोफ़ाइल संपादित करें', 'nav.logout': 'लॉगआउट',
    'nav.delete_account': 'खाता स्थायी रूप से हटाएं', 'nav.login_register': 'लॉगिन / पंजीकरण',
    'footer.disclaimer': 'एक कृषि निर्णय-सहायता उपकरण। सिफारिशें केवल जानकारी के लिए हैं और इन्हें स्थानीय कृषि '
      + 'सलाह के साथ मिलाकर उपयोग करें, विशेष रूप से उच्च-मूल्य या पहली बार उगाई जाने वाली फ़सलों के लिए।',
    'footer.data_sources': 'डेटा स्रोत: Open-Meteo (मौसम), ब्राउज़र GPS + रिवर्स जियोकोडिंग (स्थान), वास्तविक '
      + 'प्रकाशित कृषि डेटासेट (फ़सल/उपज/बाज़ार मॉडल), Google Gemini API (चैटबॉट, यदि कॉन्फ़िगर किया गया हो)।',
    'common.loading': 'लोड हो रहा है…',
    'notif.panel_title': 'अलर्ट',
    'home.eyebrow': 'लाइव फ़ील्ड रीडिंग', 'home.welcome': 'वापसी पर स्वागत है',
    'home.lead': 'कृषि आपके मिट्टी परीक्षण मूल्यों को आपके सटीक GPS स्थान के लाइव मौसम के साथ और 22 फ़सलों के '
      + '2,200 वास्तविक क्षेत्र नमूनों पर प्रशिक्षित मॉडल के साथ पढ़ता है — दाईं ओर का पैनल अभी उसी मॉडल से '
      + 'अपने आंकड़े ले रहा है, किसी स्क्रिप्ट से नहीं।',
    'home.cta_reading': 'रीडिंग लें', 'home.cta_sources': 'डेटा स्रोत देखें',
    'home.model_readout': 'मॉडल रीडआउट', 'home.accuracy_label': 'फ़सल मॉडल परीक्षण सटीकता',
    'home.training_samples': 'प्रशिक्षण नमूने', 'home.crops_modeled': 'मॉडल में शामिल फ़सलें',
    'home.market_r2': 'बाज़ार मॉडल R²', 'home.weather_source': 'मौसम स्रोत',
    'home.notif_eyebrow': 'स्मार्ट सूचनाएं', 'home.notif_heading': 'आपके ध्यान की आवश्यकता है',
    'home.notif_body': 'आपके सहेजे गए फ़सल कैलेंडर और लाइव मौसम से — कल बारिश, आज उर्वरक देय, कटाई नज़दीक, और '
      + 'सामान्य रोग-जोखिम मौसम अलर्ट।',
    'home.announcements_eyebrow': 'घोषणाएं', 'home.news_heading': 'समाचार',
    'home.all_tools_eyebrow': 'सभी उपकरण', 'home.jump_heading': 'किसी उपकरण पर जाएं',
    'home.f_recommend': 'सिफारिश + उपज + लाभप्रदता', 'home.f_soil_title': 'मिट्टी स्वास्थ्य',
    'home.f_soil': 'स्कोर, कमियां, उर्वरक', 'home.f_yield_title': 'उपज पूर्वानुमान',
    'home.f_yield': 'आपके क्षेत्र के लिए अपेक्षित टन', 'home.f_market_title': 'बाज़ार भाव',
    'home.f_market': 'वास्तविक मंडी भाव + पूर्वानुमान', 'home.f_fertilizer': 'मात्रा, लागत, समय-सारिणी',
    'home.f_profit': 'आय − व्यय', 'home.f_disease_title': 'रोग जांच',
    'home.f_disease': 'लक्षण-आधारित संदर्भ', 'home.f_water': '7-दिवसीय समय-सारिणी',
    'home.f_calendar_title': 'फ़सल कैलेंडर', 'home.f_calendar': 'बुवाई से कटाई तक की तारीखें',
    'home.f_dashboard_title': 'फार्म डैशबोर्ड', 'home.f_dashboard': 'आपके वास्तविक चार्ट',
    'home.f_map_title': 'फार्म मानचित्र', 'home.f_map': 'स्थान + नज़दीकी बाज़ार',
    'home.f_knowledge_title': 'ज्ञान आधार', 'home.f_knowledge': 'लेख, योजनाएं, प्रथाएं',
    'home.f_chat': 'LLM चैटबॉट (API कुंजी आवश्यक)',
    'page.records_eyebrow': 'आपका डेटा', 'page.records_heading': 'फार्म रिकॉर्ड',
    'page.dashboard_eyebrow': 'आपका डेटा', 'page.dashboard_heading': 'फार्म डैशबोर्ड',
    'page.market_eyebrow': 'चरण 3', 'page.market_heading': 'बाज़ार भाव',
    'page.soil_eyebrow': 'चरण 2', 'page.soil_heading': 'मिट्टी स्वास्थ्य विश्लेषण',
    'page.yield_eyebrow': 'स्वतंत्र उपकरण', 'page.yield_heading': 'उपज पूर्वानुमान',
    'page.fertilizer_eyebrow': 'चरण 4', 'page.fertilizer_heading': 'उर्वरक सिफारिश',
    'page.profit_eyebrow': 'स्वतंत्र उपकरण', 'page.profit_heading': 'लाभ अनुमान',
    'page.disease_eyebrow': 'चरण 5', 'page.disease_heading': 'रोग जांच',
    'page.water_eyebrow': 'चरण 2', 'page.water_heading': 'सिंचाई समय-सारिणी',
    'page.calendar_eyebrow': 'चरण 6', 'page.calendar_heading': 'फ़सल कैलेंडर',
    'page.analytics_eyebrow': 'आपका डेटा, संकलित', 'page.analytics_heading': 'विश्लेषण',
    'page.map_eyebrow': 'निःशुल्क, कोई API कुंजी नहीं', 'page.map_heading': 'इंटरैक्टिव फार्म मानचित्र',
    'page.knowledge_eyebrow': 'संदर्भ', 'page.knowledge_heading': 'कृषि ज्ञान आधार',
    'page.chat_eyebrow': 'वास्तविक LLM, कुंजी आवश्यक', 'page.chat_heading': 'कृषि से पूछें',
    'page.profile_eyebrow': 'खाता सेटिंग्स', 'page.profile_heading': 'प्रोफ़ाइल',
    'page.recommend_eyebrow': 'चरण 1', 'page.recommend_heading': 'फ़सल सिफारिश',
    'page.about_eyebrow': 'डेटा के बारे में ईमानदारी', 'page.about_heading': 'क्या वास्तविक है, और क्या लेबल किया गया फ़ॉलबैक है',
    'page.admin_eyebrow': 'केवल व्यवस्थापक', 'page.admin_heading': 'व्यवस्थापक पैनल',
    'page.login_eyebrow': 'साइन इन आवश्यक', 'page.login_heading': 'कृषि का उपयोग करने के लिए साइन इन करें',
    'page.login_lead': 'यहां हर उपकरण — फ़सल सलाहकार, मिट्टी स्वास्थ्य, बाज़ार भाव, सिंचाई, और बाकी सब — आपकी '
      + 'फार्म प्रोफ़ाइल से जुड़ा है, इसलिए यह साइन-इन के पीछे है। पंजीकरण में एक मिनट लगता है और कोई लागत नहीं है।',
    'auth.login_tab': 'लॉगिन', 'auth.register_tab': 'पंजीकरण', 'auth.forgot_tab': 'पासवर्ड भूल गए',
    'auth.email': 'ईमेल', 'auth.password': 'पासवर्ड', 'auth.name': 'नाम',
    'auth.password_min': 'पासवर्ड (न्यूनतम 8 अक्षर)', 'auth.confirm_password': 'पासवर्ड की पुष्टि करें',
    'auth.location': 'स्थान', 'auth.farm_size': 'फार्म का आकार (एकड़)', 'auth.soil_type': 'मिट्टी का प्रकार',
    'auth.preferred_language': 'पसंदीदा भाषा', 'auth.create_account': 'खाता बनाएं',
    'auth.forgot_link': 'पासवर्ड भूल गए?', 'auth.no_account': 'खाता नहीं है?',
    'auth.have_account': 'पहले से खाता है?', 'auth.back_to_login': '← लॉगिन पर वापस जाएं',
    'auth.forgot_title': 'अपना पासवर्ड रीसेट करें', 'auth.send_code': 'कोड भेजें',
    'auth.verify_code': 'कोड सत्यापित करें', 'auth.code_label': '6-अंकीय कोड',
    'auth.new_password': 'नया पासवर्ड', 'auth.confirm_new_password': 'नए पासवर्ड की पुष्टि करें',
    'auth.reset_password': 'पासवर्ड रीसेट करें',
    'auth.forgot_step1': 'चरण 1/3 — अपना खाता ईमेल दर्ज करें और हम उस पर 6-अंकीय कोड भेजेंगे।',
    'auth.forgot_step2': 'चरण 2/3 — अपने ईमेल पर भेजा गया 6-अंकीय कोड दर्ज करें।',
    'auth.forgot_step3': 'चरण 3/3 — कोड सत्यापित, अब अपना नया पासवर्ड सेट करें।',
    'auth.email_setup_summary': 'पासवर्ड रीसेट',
    'auth.forgot_help_text': 'जब आप पासवर्ड रीसेट का अनुरोध करते हैं, तो आपके पंजीकृत पते पर एक 6-अंकीय कोड '
      + 'ईमेल किया जाता है। यदि यह एक-दो मिनट में नहीं आता, तो अपना स्पैम फ़ोल्डर जांचें।',
    'about.whats_real': 'वास्तविक डेटा पर आधारित, अनुमानों पर नहीं',
    'about.login_panel_body': 'फ़सल और उपज सिफारिशें वास्तविक कृषि डेटासेट और प्रशिक्षित मॉडल से आती हैं, '
      + 'स्क्रिप्टेड जवाबों से नहीं। लाइव मौसम आपके सटीक स्थान के लिए Open-Meteo से आता है। बाज़ार भाव '
      + 'वास्तविक दर्ज मंडी डेटा हैं। जहां कुछ वास्तव में अभी उपलब्ध नहीं है, कृषि साफ़ तौर पर यह बताता है '
      + 'बजाय कोई संख्या बना देने के।',
    'auth.email_setup_body': 'यदि .env में SMTP_HOST/SMTP_USER/SMTP_PASSWORD सेट हैं, तो 6-अंकीय कोड '
      + 'वास्तव में ईमेल किया जाता है। इसके बिना, वास्तव में ईमेल भेजने का कोई तरीका नहीं है, इसलिए कोड '
      + 'सीधे स्क्रीन पर दिखाया जाता है — स्पष्ट रूप से एक फॉलबैक के रूप में लेबल किया गया, वास्तविक ईमेल '
      + 'का विकल्प नहीं। Gmail App Password सेटअप के लिए .env.example देखें, या अपना SMTP सेटअप सीधे '
      + 'टेस्ट करने के लिए python scripts/test_email.py you@example.com चलाएं। अभी-अभी .env संपादित '
      + 'किया? सर्वर पुनः आरंभ करें — env वेरिएबल केवल स्टार्टअप पर एक बार पढ़े जाते हैं।',
  },
  kn: {
    'nav.decision': '✨ AI ಕೃಷಿ ಯೋಜನೆ', 'nav.assistant': 'AI ಸಹಾಯಕ',
    'nav.recommend': 'ಬೆಳೆ ಸಲಹೆಗಾರ', 'nav.soil': 'ಮಣ್ಣು', 'nav.market': 'ಮಾರುಕಟ್ಟೆ', 'nav.dashboard': 'ಡ್ಯಾಶ್‌ಬೋರ್ಡ್',
    'nav.more': '☰ ಇನ್ನಷ್ಟು', 'nav.yield': 'ಇಳುವರಿ', 'nav.fertilizer': 'ಗೊಬ್ಬರ', 'nav.profit': 'ಲಾಭ',
    'nav.disease': 'ರೋಗ', 'nav.water': 'ನೀರಾವರಿ', 'nav.calendar': 'ಕ್ಯಾಲೆಂಡರ್', 'nav.records': 'ದಾಖಲೆಗಳು',
    'nav.analytics': 'ವಿಶ್ಲೇಷಣೆ', 'nav.map': 'ನಕ್ಷೆ', 'nav.knowledge': 'ಕಲಿಯಿರಿ', 'nav.chat': 'ಕೃಷಿಯನ್ನು ಕೇಳಿ',
    'nav.admin': 'ನಿರ್ವಾಹಕ', 'nav.edit_profile': 'ಪ್ರೊಫೈಲ್ ಸಂಪಾದಿಸಿ', 'nav.logout': 'ಲಾಗ್ಔಟ್',
    'nav.delete_account': 'ಖಾತೆಯನ್ನು ಶಾಶ್ವತವಾಗಿ ಅಳಿಸಿ', 'nav.login_register': 'ಲಾಗಿನ್ / ನೋಂದಣಿ',
    'footer.disclaimer': 'ಒಂದು ಕೃಷಿ ನಿರ್ಧಾರ-ಬೆಂಬಲ ಸಾಧನ. ಶಿಫಾರಸುಗಳು ಮಾಹಿತಿ ಉದ್ದೇಶಕ್ಕಾಗಿ ಮಾತ್ರ, ಇವುಗಳನ್ನು ಸ್ಥಳೀಯ ಕೃಷಿ '
      + 'ಸಲಹೆಯೊಂದಿಗೆ ಸಂಯೋಜಿಸಬೇಕು, ವಿಶೇಷವಾಗಿ ಹೆಚ್ಚು ಮೌಲ್ಯದ ಅಥವಾ ಮೊದಲ ಬಾರಿಗೆ ಬೆಳೆಯುವ ಬೆಳೆಗಳಿಗೆ.',
    'footer.data_sources': 'ಡೇಟಾ ಮೂಲಗಳು: Open-Meteo (ಹವಾಮಾನ), ಬ್ರೌಸರ್ GPS + ರಿವರ್ಸ್ ಜಿಯೋಕೋಡಿಂಗ್ (ಸ್ಥಳ), ನೈಜ '
      + 'ಪ್ರಕಟಿತ ಕೃಷಿ ಡೇಟಾಸೆಟ್‌ಗಳು (ಬೆಳೆ/ಇಳುವರಿ/ಮಾರುಕಟ್ಟೆ ಮಾದರಿಗಳು), Google Gemini API (ಚಾಟ್‌ಬಾಟ್, ಕಾನ್ಫಿಗರ್ ಮಾಡಿದ್ದರೆ).',
    'common.loading': 'ಲೋಡ್ ಆಗುತ್ತಿದೆ…',
    'notif.panel_title': 'ಎಚ್ಚರಿಕೆಗಳು',
    'home.eyebrow': 'ಲೈವ್ ಫೀಲ್ಡ್ ರೀಡಿಂಗ್', 'home.welcome': 'ಮತ್ತೆ ಸ್ವಾಗತ',
    'home.lead': 'ಕೃಷಿ ನಿಮ್ಮ ಮಣ್ಣಿನ ಪರೀಕ್ಷಾ ಮೌಲ್ಯಗಳನ್ನು ನಿಮ್ಮ ನಿಖರ GPS ಸ್ಥಳದ ಲೈವ್ ಹವಾಮಾನ ಮತ್ತು 22 ಬೆಳೆಗಳಾದ್ಯಂತ '
      + '2,200 ನೈಜ ಕ್ಷೇತ್ರ ಮಾದರಿಗಳ ಮೇಲೆ ತರಬೇತಿ ಪಡೆದ ಮಾದರಿಯೊಂದಿಗೆ ಓದುತ್ತದೆ — ಬಲಭಾಗದ ಪ್ಯಾನಲ್ ಈಗ ಆ ಮಾದರಿಯಿಂದ '
      + 'ತನ್ನ ಸಂಖ್ಯೆಗಳನ್ನು ಪಡೆಯುತ್ತಿದೆ, ಸ್ಕ್ರಿಪ್ಟ್‌ನಿಂದ ಅಲ್ಲ.',
    'home.cta_reading': 'ಒಂದು ರೀಡಿಂಗ್ ತೆಗೆದುಕೊಳ್ಳಿ', 'home.cta_sources': 'ಡೇಟಾ ಮೂಲಗಳನ್ನು ನೋಡಿ',
    'home.model_readout': 'ಮಾದರಿ ರೀಡ್‌ಔಟ್', 'home.accuracy_label': 'ಬೆಳೆ ಮಾದರಿ ಪರೀಕ್ಷಾ ನಿಖರತೆ',
    'home.training_samples': 'ತರಬೇತಿ ಮಾದರಿಗಳು', 'home.crops_modeled': 'ಮಾದರಿಯಲ್ಲಿರುವ ಬೆಳೆಗಳು',
    'home.market_r2': 'ಮಾರುಕಟ್ಟೆ ಮಾದರಿ R²', 'home.weather_source': 'ಹವಾಮಾನ ಮೂಲ',
    'home.notif_eyebrow': 'ಸ್ಮಾರ್ಟ್ ಅಧಿಸೂಚನೆಗಳು', 'home.notif_heading': 'ನಿಮ್ಮ ಗಮನ ಬೇಕಿರುವುದು',
    'home.notif_body': 'ನಿಮ್ಮ ಉಳಿಸಿದ ಬೆಳೆ ಕ್ಯಾಲೆಂಡರ್‌ಗಳು ಮತ್ತು ಲೈವ್ ಹವಾಮಾನದಿಂದ — ನಾಳೆ ಮಳೆ, ಇಂದು ಗೊಬ್ಬರ ಬಾಕಿ, '
      + 'ಸುಗ್ಗಿ ಸಮೀಪಿಸುತ್ತಿದೆ, ಮತ್ತು ಸಾಮಾನ್ಯ ರೋಗ-ಅಪಾಯದ ಹವಾಮಾನ ಎಚ್ಚರಿಕೆಗಳು.',
    'home.announcements_eyebrow': 'ಪ್ರಕಟಣೆಗಳು', 'home.news_heading': 'ಸುದ್ದಿ',
    'home.all_tools_eyebrow': 'ಎಲ್ಲಾ ಪರಿಕರಗಳು', 'home.jump_heading': 'ಒಂದು ಪರಿಕರಕ್ಕೆ ಹೋಗಿ',
    'home.f_recommend': 'ಶಿಫಾರಸು + ಇಳುವರಿ + ಲಾಭದಾಯಕತೆ', 'home.f_soil_title': 'ಮಣ್ಣಿನ ಆರೋಗ್ಯ',
    'home.f_soil': 'ಸ್ಕೋರ್, ಕೊರತೆಗಳು, ಗೊಬ್ಬರ', 'home.f_yield_title': 'ಇಳುವರಿ ಮುನ್ಸೂಚನೆ',
    'home.f_yield': 'ನಿಮ್ಮ ಪ್ರದೇಶಕ್ಕೆ ನಿರೀಕ್ಷಿತ ಟನ್‌ಗಳು', 'home.f_market_title': 'ಮಾರುಕಟ್ಟೆ ಬೆಲೆ',
    'home.f_market': 'ನೈಜ ಮಂಡಿ ಬೆಲೆಗಳು + ಮುನ್ಸೂಚನೆ', 'home.f_fertilizer': 'ಪ್ರಮಾಣ, ವೆಚ್ಚ, ವೇಳಾಪಟ್ಟಿ',
    'home.f_profit': 'ಆದಾಯ − ವೆಚ್ಚ', 'home.f_disease_title': 'ರೋಗ ಪರೀಕ್ಷೆ',
    'home.f_disease': 'ಲಕ್ಷಣ ಆಧಾರಿತ ಉಲ್ಲೇಖ', 'home.f_water': '7-ದಿನಗಳ ವೇಳಾಪಟ್ಟಿ',
    'home.f_calendar_title': 'ಬೆಳೆ ಕ್ಯಾಲೆಂಡರ್', 'home.f_calendar': 'ಬಿತ್ತನೆಯಿಂದ ಸುಗ್ಗಿಯವರೆಗಿನ ದಿನಾಂಕಗಳು',
    'home.f_dashboard_title': 'ಫಾರ್ಮ್ ಡ್ಯಾಶ್‌ಬೋರ್ಡ್', 'home.f_dashboard': 'ನಿಮ್ಮ ನೈಜ ಚಾರ್ಟ್‌ಗಳು',
    'home.f_map_title': 'ಫಾರ್ಮ್ ನಕ್ಷೆ', 'home.f_map': 'ಸ್ಥಳ + ಹತ್ತಿರದ ಮಾರುಕಟ್ಟೆಗಳು',
    'home.f_knowledge_title': 'ಜ್ಞಾನ ಆಧಾರ', 'home.f_knowledge': 'ಲೇಖನಗಳು, ಯೋಜನೆಗಳು, ಅಭ್ಯಾಸಗಳು',
    'home.f_chat': 'LLM ಚಾಟ್‌ಬಾಟ್ (API ಕೀ ಅಗತ್ಯ)',
    'page.records_eyebrow': 'ನಿಮ್ಮ ಡೇಟಾ', 'page.records_heading': 'ಫಾರ್ಮ್ ದಾಖಲೆಗಳು',
    'page.dashboard_eyebrow': 'ನಿಮ್ಮ ಡೇಟಾ', 'page.dashboard_heading': 'ಫಾರ್ಮ್ ಡ್ಯಾಶ್‌ಬೋರ್ಡ್',
    'page.market_eyebrow': 'ಹಂತ 3', 'page.market_heading': 'ಮಾರುಕಟ್ಟೆ ಬೆಲೆ',
    'page.soil_eyebrow': 'ಹಂತ 2', 'page.soil_heading': 'ಮಣ್ಣಿನ ಆರೋಗ್ಯ ವಿಶ್ಲೇಷಣೆ',
    'page.yield_eyebrow': 'ಸ್ವತಂತ್ರ ಪರಿಕರ', 'page.yield_heading': 'ಇಳುವರಿ ಮುನ್ಸೂಚನೆ',
    'page.fertilizer_eyebrow': 'ಹಂತ 4', 'page.fertilizer_heading': 'ಗೊಬ್ಬರ ಶಿಫಾರಸು',
    'page.profit_eyebrow': 'ಸ್ವತಂತ್ರ ಪರಿಕರ', 'page.profit_heading': 'ಲಾಭ ಅಂದಾಜು',
    'page.disease_eyebrow': 'ಹಂತ 5', 'page.disease_heading': 'ರೋಗ ಪರೀಕ್ಷೆ',
    'page.water_eyebrow': 'ಹಂತ 2', 'page.water_heading': 'ನೀರಾವರಿ ವೇಳಾಪಟ್ಟಿ',
    'page.calendar_eyebrow': 'ಹಂತ 6', 'page.calendar_heading': 'ಬೆಳೆ ಕ್ಯಾಲೆಂಡರ್',
    'page.analytics_eyebrow': 'ನಿಮ್ಮ ಡೇಟಾ, ಒಟ್ಟುಗೂಡಿಸಲಾಗಿದೆ', 'page.analytics_heading': 'ವಿಶ್ಲೇಷಣೆ',
    'page.map_eyebrow': 'ಉಚಿತ, API ಕೀ ಇಲ್ಲ', 'page.map_heading': 'ಸಂವಾದಾತ್ಮಕ ಫಾರ್ಮ್ ನಕ್ಷೆ',
    'page.knowledge_eyebrow': 'ಉಲ್ಲೇಖ', 'page.knowledge_heading': 'ಕೃಷಿ ಜ್ಞಾನ ಆಧಾರ',
    'page.chat_eyebrow': 'ನೈಜ LLM, ಕೀ ಅಗತ್ಯ', 'page.chat_heading': 'ಕೃಷಿಯನ್ನು ಕೇಳಿ',
    'page.profile_eyebrow': 'ಖಾತೆ ಸೆಟ್ಟಿಂಗ್‌ಗಳು', 'page.profile_heading': 'ಪ್ರೊಫೈಲ್',
    'page.recommend_eyebrow': 'ಹಂತ 1', 'page.recommend_heading': 'ಬೆಳೆ ಶಿಫಾರಸು',
    'page.about_eyebrow': 'ಡೇಟಾ ಬಗ್ಗೆ ಪ್ರಾಮಾಣಿಕತೆ', 'page.about_heading': 'ಏನು ನೈಜ, ಮತ್ತು ಏನು ಲೇಬಲ್ ಮಾಡಿದ ಫಾಲ್‌ಬ್ಯಾಕ್',
    'page.admin_eyebrow': 'ನಿರ್ವಾಹಕರಿಗೆ ಮಾತ್ರ', 'page.admin_heading': 'ನಿರ್ವಾಹಕ ಫಲಕ',
    'page.login_eyebrow': 'ಸೈನ್ ಇನ್ ಅಗತ್ಯ', 'page.login_heading': 'ಕೃಷಿಯನ್ನು ಬಳಸಲು ಸೈನ್ ಇನ್ ಮಾಡಿ',
    'page.login_lead': 'ಇಲ್ಲಿರುವ ಪ್ರತಿಯೊಂದು ಪರಿಕರ — ಬೆಳೆ ಸಲಹೆಗಾರ, ಮಣ್ಣಿನ ಆರೋಗ್ಯ, ಮಾರುಕಟ್ಟೆ ಬೆಲೆಗಳು, ನೀರಾವರಿ, '
      + 'ಮತ್ತು ಉಳಿದವು — ನಿಮ್ಮ ಫಾರ್ಮ್ ಪ್ರೊಫೈಲ್‌ಗೆ ಸಂಬಂಧಿಸಿದೆ, ಆದ್ದರಿಂದ ಇದು ಸೈನ್-ಇನ್ ಹಿಂದೆ ಇದೆ. ನೋಂದಣಿಗೆ '
      + 'ಒಂದು ನಿಮಿಷ ತೆಗೆದುಕೊಳ್ಳುತ್ತದೆ ಮತ್ತು ಯಾವುದೇ ವೆಚ್ಚವಿಲ್ಲ.',
    'auth.login_tab': 'ಲಾಗಿನ್', 'auth.register_tab': 'ನೋಂದಣಿ', 'auth.forgot_tab': 'ಪಾಸ್‌ವರ್ಡ್ ಮರೆತಿದ್ದೀರಾ',
    'auth.email': 'ಇಮೇಲ್', 'auth.password': 'ಪಾಸ್‌ವರ್ಡ್', 'auth.name': 'ಹೆಸರು',
    'auth.password_min': 'ಪಾಸ್‌ವರ್ಡ್ (ಕನಿಷ್ಠ 8 ಅಕ್ಷರಗಳು)', 'auth.confirm_password': 'ಪಾಸ್‌ವರ್ಡ್ ದೃಢೀಕರಿಸಿ',
    'auth.location': 'ಸ್ಥಳ', 'auth.farm_size': 'ಫಾರ್ಮ್ ಗಾತ್ರ (ಎಕರೆ)', 'auth.soil_type': 'ಮಣ್ಣಿನ ಪ್ರಕಾರ',
    'auth.preferred_language': 'ಆದ್ಯತೆಯ ಭಾಷೆ', 'auth.create_account': 'ಖಾತೆ ರಚಿಸಿ',
    'auth.forgot_link': 'ಪಾಸ್‌ವರ್ಡ್ ಮರೆತಿದ್ದೀರಾ?', 'auth.no_account': 'ಖಾತೆ ಇಲ್ಲವೇ?',
    'auth.have_account': 'ಈಗಾಗಲೇ ಖಾತೆ ಇದೆಯೇ?', 'auth.back_to_login': '← ಲಾಗಿನ್‌ಗೆ ಹಿಂತಿರುಗಿ',
    'auth.forgot_title': 'ನಿಮ್ಮ ಪಾಸ್‌ವರ್ಡ್ ಮರುಹೊಂದಿಸಿ', 'auth.send_code': 'ಕೋಡ್ ಕಳುಹಿಸಿ',
    'auth.verify_code': 'ಕೋಡ್ ಪರಿಶೀಲಿಸಿ', 'auth.code_label': '6-ಅಂಕಿಯ ಕೋಡ್',
    'auth.new_password': 'ಹೊಸ ಪಾಸ್‌ವರ್ಡ್', 'auth.confirm_new_password': 'ಹೊಸ ಪಾಸ್‌ವರ್ಡ್ ದೃಢೀಕರಿಸಿ',
    'auth.reset_password': 'ಪಾಸ್‌ವರ್ಡ್ ಮರುಹೊಂದಿಸಿ',
    'auth.forgot_step1': 'ಹಂತ 1/3 — ನಿಮ್ಮ ಖಾತೆ ಇಮೇಲ್ ನಮೂದಿಸಿ, ನಾವು ಅದಕ್ಕೆ 6-ಅಂಕಿಯ ಕೋಡ್ ಕಳುಹಿಸುತ್ತೇವೆ.',
    'auth.forgot_step2': 'ಹಂತ 2/3 — ನಿಮ್ಮ ಇಮೇಲ್‌ಗೆ ಕಳುಹಿಸಿದ 6-ಅಂಕಿಯ ಕೋಡ್ ನಮೂದಿಸಿ.',
    'auth.forgot_step3': 'ಹಂತ 3/3 — ಕೋಡ್ ಪರಿಶೀಲಿಸಲಾಗಿದೆ, ಈಗ ನಿಮ್ಮ ಹೊಸ ಪಾಸ್‌ವರ್ಡ್ ಹೊಂದಿಸಿ.',
    'auth.email_setup_summary': 'ಪಾಸ್‌ವರ್ಡ್ ಮರುಹೊಂದಿಕೆ',
    'auth.forgot_help_text': 'ನೀವು ಪಾಸ್‌ವರ್ಡ್ ಮರುಹೊಂದಿಕೆಗೆ ವಿನಂತಿಸಿದಾಗ ನಿಮ್ಮ ನೋಂದಾಯಿತ ವಿಳಾಸಕ್ಕೆ 6-ಅಂಕಿಯ '
      + 'ಕೋಡ್ ಇಮೇಲ್ ಮಾಡಲಾಗುತ್ತದೆ. ಇದು ಒಂದೆರಡು ನಿಮಿಷಗಳಲ್ಲಿ ಬರದಿದ್ದರೆ, ನಿಮ್ಮ ಸ್ಪ್ಯಾಮ್ ಫೋಲ್ಡರ್ ಪರಿಶೀಲಿಸಿ.',
    'about.whats_real': 'ನೈಜ ಡೇಟಾದ ಮೇಲೆ ನಿರ್ಮಿಸಲಾಗಿದೆ, ಊಹೆಗಳ ಮೇಲೆ ಅಲ್ಲ',
    'about.login_panel_body': 'ಬೆಳೆ ಮತ್ತು ಇಳುವರಿ ಶಿಫಾರಸುಗಳು ನೈಜ ಕೃಷಿ ಡೇಟಾಸೆಟ್‌ಗಳು ಮತ್ತು ತರಬೇತಿ ಪಡೆದ '
      + 'ಮಾದರಿಗಳಿಂದ ಬರುತ್ತವೆ, ಸ್ಕ್ರಿಪ್ಟ್ ಮಾಡಿದ ಪ್ರತಿಕ್ರಿಯೆಗಳಿಂದ ಅಲ್ಲ. ಲೈವ್ ಹವಾಮಾನವು ನಿಮ್ಮ ನಿಖರ '
      + 'ಸ್ಥಳಕ್ಕಾಗಿ Open-Meteo ನಿಂದ ಬರುತ್ತದೆ. ಮಾರುಕಟ್ಟೆ ಬೆಲೆಗಳು ನೈಜ ದಾಖಲಾದ ಮಂಡಿ ಡೇಟಾ. ಏನಾದರೂ '
      + 'ನಿಜವಾಗಿಯೂ ಇನ್ನೂ ಲಭ್ಯವಿಲ್ಲದಿದ್ದಲ್ಲಿ, ಕೃಷಿ ಸಂಖ್ಯೆಯನ್ನು ಕಟ್ಟಿಕೊಳ್ಳುವ ಬದಲು ಸ್ಪಷ್ಟವಾಗಿ ಹೇಳುತ್ತದೆ.',
    'auth.email_setup_body': '.env ನಲ್ಲಿ SMTP_HOST/SMTP_USER/SMTP_PASSWORD ಹೊಂದಿಸಿದ್ದರೆ, 6-ಅಂಕಿಯ ಕೋಡ್ '
      + 'ನಿಜವಾಗಿ ಇಮೇಲ್ ಮಾಡಲಾಗುತ್ತದೆ. ಅದಿಲ್ಲದೆ, ನಿಜವಾಗಿ ಇಮೇಲ್ ತಲುಪಿಸಲು ಯಾವುದೇ ಮಾರ್ಗವಿಲ್ಲ, ಆದ್ದರಿಂದ '
      + 'ಕೋಡ್ ಅನ್ನು ಪರದೆಯ ಮೇಲೆ ನೇರವಾಗಿ ತೋರಿಸಲಾಗುತ್ತದೆ — ಸ್ಪಷ್ಟವಾಗಿ ಒಂದು ಫಾಲ್‌ಬ್ಯಾಕ್ ಎಂದು ಲೇಬಲ್ '
      + 'ಮಾಡಲಾಗಿದೆ, ನಿಜವಾದ ಇಮೇಲ್‌ಗೆ ಬದಲಿಯಲ್ಲ. Gmail App Password ಸೆಟಪ್‌ಗಾಗಿ .env.example ನೋಡಿ, ಅಥವಾ '
      + 'ನಿಮ್ಮ SMTP ಸೆಟಪ್ ಅನ್ನು ನೇರವಾಗಿ ಪರೀಕ್ಷಿಸಲು python scripts/test_email.py you@example.com '
      + 'ಚಲಾಯಿಸಿ. ಈಗಷ್ಟೇ .env ಸಂಪಾದಿಸಿದ್ದೀರಾ? ಸರ್ವರ್ ಮರುಪ್ರಾರಂಭಿಸಿ — env ವೇರಿಯೇಬಲ್‌ಗಳನ್ನು ಸ್ಟಾರ್ಟಪ್‌ನಲ್ಲಿ '
      + 'ಒಮ್ಮೆ ಮಾತ್ರ ಓದಲಾಗುತ್ತದೆ.',
  },
  mr: {
    'nav.decision': '✨ AI शेती नियोजन', 'nav.assistant': 'AI सहाय्यक',
    'nav.recommend': 'पीक सल्लागार', 'nav.soil': 'माती', 'nav.market': 'बाजार', 'nav.dashboard': 'डॅशबोर्ड',
    'nav.more': '☰ अधिक', 'nav.yield': 'उत्पादन', 'nav.fertilizer': 'खत', 'nav.profit': 'नफा',
    'nav.disease': 'रोग', 'nav.water': 'सिंचन', 'nav.calendar': 'दिनदर्शिका', 'nav.records': 'नोंदी',
    'nav.analytics': 'विश्लेषण', 'nav.map': 'नकाशा', 'nav.knowledge': 'शिका', 'nav.chat': 'कृषीला विचारा',
    'nav.admin': 'प्रशासक', 'nav.edit_profile': 'प्रोफाइल संपादित करा', 'nav.logout': 'लॉगआउट',
    'nav.delete_account': 'खाते कायमचे हटवा', 'nav.login_register': 'लॉगिन / नोंदणी',
    'footer.disclaimer': 'एक कृषी निर्णय-सहाय्य साधन. शिफारसी केवळ माहितीसाठी आहेत आणि विशेषतः जास्त मूल्याच्या '
      + 'किंवा प्रथमच घेतल्या जाणाऱ्या पिकांसाठी स्थानिक कृषी सल्ल्यासोबत वापराव्यात.',
    'footer.data_sources': 'डेटा स्रोत: Open-Meteo (हवामान), ब्राउझर GPS + रिव्हर्स जिओकोडिंग (स्थान), '
      + 'खरे प्रकाशित कृषी डेटासेट (पीक/उत्पादन/बाजार मॉडेल), Google Gemini API (चॅटबॉट, कॉन्फिगर केले असल्यास).',
    'common.loading': 'लोड होत आहे…',
    'notif.panel_title': 'सूचना',
    'home.eyebrow': 'लाइव्ह फील्ड रीडिंग', 'home.welcome': 'परत स्वागत आहे',
    'home.lead': 'कृषी तुमची माती परीक्षण मूल्ये तुमच्या नेमक्या GPS स्थानाच्या लाइव्ह हवामानासोबत आणि 22 '
      + 'पिकांवरील 2,200 खऱ्या क्षेत्र नमुन्यांवर प्रशिक्षित मॉडेलसोबत वाचते — उजवीकडील पॅनेल आत्ता त्याच '
      + 'मॉडेलमधून आकडे घेत आहे, स्क्रिप्टमधून नाही.',
    'home.cta_reading': 'रीडिंग घ्या', 'home.cta_sources': 'डेटा स्रोत पहा',
    'home.model_readout': 'मॉडेल रीडआउट', 'home.accuracy_label': 'पीक मॉडेल चाचणी अचूकता',
    'home.training_samples': 'प्रशिक्षण नमुने', 'home.crops_modeled': 'मॉडेलमधील पिके',
    'home.market_r2': 'बाजार मॉडेल R²', 'home.weather_source': 'हवामान स्रोत',
    'home.notif_eyebrow': 'स्मार्ट सूचना', 'home.notif_heading': 'तुमच्या लक्षाची गरज असलेल्या गोष्टी',
    'home.notif_body': 'तुमच्या जतन केलेल्या पीक दिनदर्शिका आणि लाइव्ह हवामानावरून — उद्या पाऊस, आज खत देय, '
      + 'कापणी जवळ येत आहे, आणि सर्वसाधारण रोग-जोखीम हवामान इशारे.',
    'home.announcements_eyebrow': 'घोषणा', 'home.news_heading': 'बातम्या',
    'home.all_tools_eyebrow': 'सर्व साधने', 'home.jump_heading': 'एखाद्या साधनावर जा',
    'home.f_recommend': 'शिफारस + उत्पादन + नफाक्षमता', 'home.f_soil_title': 'माती आरोग्य',
    'home.f_soil': 'गुण, कमतरता, खत', 'home.f_yield_title': 'उत्पादन अंदाज',
    'home.f_yield': 'तुमच्या क्षेत्रासाठी अपेक्षित टन', 'home.f_market_title': 'बाजार भाव',
    'home.f_market': 'खरे मंडी भाव + अंदाज', 'home.f_fertilizer': 'प्रमाण, खर्च, वेळापत्रक',
    'home.f_profit': 'उत्पन्न − खर्च', 'home.f_disease_title': 'रोग तपासणी',
    'home.f_disease': 'लक्षण-आधारित संदर्भ', 'home.f_water': '7-दिवसीय वेळापत्रक',
    'home.f_calendar_title': 'पीक दिनदर्शिका', 'home.f_calendar': 'पेरणी ते कापणी तारखा',
    'home.f_dashboard_title': 'फार्म डॅशबोर्ड', 'home.f_dashboard': 'तुमचे खरे तक्ते',
    'home.f_map_title': 'फार्म नकाशा', 'home.f_map': 'स्थान + जवळचे बाजार',
    'home.f_knowledge_title': 'ज्ञान आधार', 'home.f_knowledge': 'लेख, योजना, पद्धती',
    'home.f_chat': 'LLM चॅटबॉट (API की आवश्यक)',
    'page.records_eyebrow': 'तुमचा डेटा', 'page.records_heading': 'फार्म नोंदी',
    'page.dashboard_eyebrow': 'तुमचा डेटा', 'page.dashboard_heading': 'फार्म डॅशबोर्ड',
    'page.market_eyebrow': 'पायरी 3', 'page.market_heading': 'बाजार भाव',
    'page.soil_eyebrow': 'पायरी 2', 'page.soil_heading': 'माती आरोग्य विश्लेषण',
    'page.yield_eyebrow': 'स्वतंत्र साधन', 'page.yield_heading': 'उत्पादन अंदाज',
    'page.fertilizer_eyebrow': 'पायरी 4', 'page.fertilizer_heading': 'खत शिफारस',
    'page.profit_eyebrow': 'स्वतंत्र साधन', 'page.profit_heading': 'नफा अंदाज',
    'page.disease_eyebrow': 'पायरी 5', 'page.disease_heading': 'रोग तपासणी',
    'page.water_eyebrow': 'पायरी 2', 'page.water_heading': 'सिंचन वेळापत्रक',
    'page.calendar_eyebrow': 'पायरी 6', 'page.calendar_heading': 'पीक दिनदर्शिका',
    'page.analytics_eyebrow': 'तुमचा डेटा, एकत्रित', 'page.analytics_heading': 'विश्लेषण',
    'page.map_eyebrow': 'मोफत, API की आवश्यक नाही', 'page.map_heading': 'परस्परसंवादी फार्म नकाशा',
    'page.knowledge_eyebrow': 'संदर्भ', 'page.knowledge_heading': 'शेती ज्ञान आधार',
    'page.chat_eyebrow': 'खरे LLM, की आवश्यक', 'page.chat_heading': 'कृषीला विचारा',
    'page.profile_eyebrow': 'खाते सेटिंग्ज', 'page.profile_heading': 'प्रोफाइल',
    'page.recommend_eyebrow': 'पायरी 1', 'page.recommend_heading': 'पीक शिफारस',
    'page.about_eyebrow': 'डेटाबद्दल प्रामाणिकपणा', 'page.about_heading': 'काय खरे आहे, आणि काय लेबल केलेला फॉलबॅक आहे',
    'page.admin_eyebrow': 'फक्त प्रशासक', 'page.admin_heading': 'प्रशासक पॅनेल',
    'page.login_eyebrow': 'साइन इन आवश्यक', 'page.login_heading': 'कृषी वापरण्यासाठी साइन इन करा',
    'page.login_lead': 'येथील प्रत्येक साधन — पीक सल्लागार, माती आरोग्य, बाजार भाव, सिंचन, आणि बाकीचे — '
      + 'तुमच्या फार्म प्रोफाइलशी जोडलेले आहे, म्हणून ते साइन-इनच्या मागे आहे. नोंदणीला एक मिनिट लागतो '
      + 'आणि काहीही खर्च नाही.',
    'auth.login_tab': 'लॉगिन', 'auth.register_tab': 'नोंदणी', 'auth.forgot_tab': 'पासवर्ड विसरलात',
    'auth.email': 'ईमेल', 'auth.password': 'पासवर्ड', 'auth.name': 'नाव',
    'auth.password_min': 'पासवर्ड (किमान 8 अक्षरे)', 'auth.confirm_password': 'पासवर्डची पुष्टी करा',
    'auth.location': 'स्थान', 'auth.farm_size': 'शेताचा आकार (एकर)', 'auth.soil_type': 'मातीचा प्रकार',
    'auth.preferred_language': 'पसंतीची भाषा', 'auth.create_account': 'खाते तयार करा',
    'auth.forgot_link': 'पासवर्ड विसरलात?', 'auth.no_account': 'खाते नाही?',
    'auth.have_account': 'आधीच खाते आहे?', 'auth.back_to_login': '← लॉगिनवर परत जा',
    'auth.forgot_title': 'तुमचा पासवर्ड रीसेट करा', 'auth.send_code': 'कोड पाठवा',
    'auth.verify_code': 'कोड सत्यापित करा', 'auth.code_label': '6-अंकी कोड',
    'auth.new_password': 'नवीन पासवर्ड', 'auth.confirm_new_password': 'नवीन पासवर्डची पुष्टी करा',
    'auth.reset_password': 'पासवर्ड रीसेट करा',
    'auth.forgot_step1': 'पायरी 1/3 — तुमचा खाते ईमेल टाका, आम्ही त्यावर 6-अंकी कोड पाठवू.',
    'auth.forgot_step2': 'पायरी 2/3 — तुमच्या ईमेलवर पाठवलेला 6-अंकी कोड टाका.',
    'auth.forgot_step3': 'पायरी 3/3 — कोड सत्यापित झाला, आता तुमचा नवीन पासवर्ड सेट करा.',
    'auth.email_setup_summary': 'पासवर्ड रीसेट',
    'auth.forgot_help_text': 'तुम्ही पासवर्ड रीसेटची विनंती करता तेव्हा तुमच्या नोंदणीकृत पत्त्यावर 6-अंकी '
      + 'कोड ईमेल केला जातो. एक-दोन मिनिटांत तो न आल्यास, तुमचा स्पॅम फोल्डर तपासा.',
    'about.whats_real': 'खऱ्या डेटावर आधारित, अंदाजांवर नाही',
    'about.login_panel_body': 'पीक आणि उत्पादन शिफारसी खऱ्या कृषी डेटासेट आणि प्रशिक्षित मॉडेल्सवरून येतात, '
      + 'स्क्रिप्टेड उत्तरांवरून नाही. लाइव्ह हवामान तुमच्या नेमक्या स्थानासाठी Open-Meteo वरून येते. बाजार '
      + 'भाव खरा नोंदवलेला मंडी डेटा आहे. काही खरोखर अद्याप उपलब्ध नसल्यास, कृषी संख्या तयार करण्याऐवजी '
      + 'स्पष्टपणे तसे सांगते.',
    'auth.email_setup_body': '.env मध्ये SMTP_HOST/SMTP_USER/SMTP_PASSWORD सेट असल्यास, 6-अंकी कोड '
      + 'खरोखर ईमेल केला जातो. त्याशिवाय, खरोखर ईमेल पोहोचवण्याचा कोणताही मार्ग नाही, म्हणून कोड '
      + 'थेट स्क्रीनवर दाखवला जातो — स्पष्टपणे फॉलबॅक म्हणून लेबल केलेला, खऱ्या ईमेलचा पर्याय नाही. '
      + 'Gmail App Password सेटअपसाठी .env.example पहा, किंवा तुमचा SMTP सेटअप थेट तपासण्यासाठी '
      + 'python scripts/test_email.py you@example.com चालवा. नुकतेच .env संपादित केले? सर्व्हर '
      + 'रीस्टार्ट करा — env व्हेरिएबल्स फक्त स्टार्टअपला एकदाच वाचली जातात.',
  },
  ta: {
    'nav.decision': '✨ AI விவசாயத் திட்டம்', 'nav.assistant': 'AI உதவியாளர்',
    'nav.recommend': 'பயிர் ஆலோசகர்', 'nav.soil': 'மண்', 'nav.market': 'சந்தை', 'nav.dashboard': 'டாஷ்போர்டு',
    'nav.more': '☰ மேலும்', 'nav.yield': 'விளைச்சல்', 'nav.fertilizer': 'உரம்', 'nav.profit': 'லாபம்',
    'nav.disease': 'நோய்', 'nav.water': 'நீர்ப்பாசனம்', 'nav.calendar': 'நாட்காட்டி', 'nav.records': 'பதிவுகள்',
    'nav.analytics': 'பகுப்பாய்வு', 'nav.map': 'வரைபடம்', 'nav.knowledge': 'கற்றுக்கொள்', 'nav.chat': 'கிருஷியிடம் கேளுங்கள்',
    'nav.admin': 'நிர்வாகி', 'nav.edit_profile': 'சுயவிவரத்தைத் திருத்து', 'nav.logout': 'வெளியேறு',
    'nav.delete_account': 'கணக்கை நிரந்தரமாக நீக்கு', 'nav.login_register': 'உள்நுழை / பதிவு செய்',
    'footer.disclaimer': 'ஒரு விவசாய முடிவு-ஆதரவு கருவி. பரிந்துரைகள் தகவல் நோக்கத்திற்காக மட்டுமே, '
      + 'குறிப்பாக அதிக மதிப்புள்ள அல்லது முதல் முறை பயிரிடப்படும் பயிர்களுக்கு உள்ளூர் வேளாண் ஆலோசனையுடன் இணைத்துப் பயன்படுத்தவும்.',
    'footer.data_sources': 'தரவு ஆதாரங்கள்: Open-Meteo (வானிலை), உலாவி GPS + ரிவர்ஸ் ஜியோகோடிங் (இடம்), '
      + 'உண்மையான வெளியிடப்பட்ட வேளாண் தரவுத்தொகுப்புகள் (பயிர்/விளைச்சல்/சந்தை மாதிரிகள்), Google Gemini API (சாட்பாட், கட்டமைக்கப்பட்டிருந்தால்).',
    'common.loading': 'ஏற்றுகிறது…',
    'notif.panel_title': 'எச்சரிக்கைகள்',
    'home.eyebrow': 'நேரடி வயல் அளவீடு', 'home.welcome': 'மீண்டும் வரவேற்கிறோம்',
    'home.lead': 'உங்கள் துல்லியமான GPS இடத்தின் நேரடி வானிலைக்கு எதிராக உங்கள் மண் பரிசோதனை மதிப்புகளையும், '
      + '22 பயிர்களில் 2,200 உண்மையான வயல் மாதிரிகளில் பயிற்சி பெற்ற மாதிரியையும் கிருஷி படிக்கிறது — வலது '
      + 'பக்கப் பலகம் இப்போது அந்த மாதிரியிலிருந்தே தன் எண்களைப் பெறுகிறது, ஸ்கிரிப்டிலிருந்து அல்ல.',
    'home.cta_reading': 'ஒரு அளவீடு எடுக்கவும்', 'home.cta_sources': 'தரவு ஆதாரங்களைப் பார்க்கவும்',
    'home.model_readout': 'மாதிரி வாசிப்பு', 'home.accuracy_label': 'பயிர் மாதிரி சோதனை துல்லியம்',
    'home.training_samples': 'பயிற்சி மாதிரிகள்', 'home.crops_modeled': 'மாதிரியிடப்பட்ட பயிர்கள்',
    'home.market_r2': 'சந்தை மாதிரி R²', 'home.weather_source': 'வானிலை ஆதாரம்',
    'home.notif_eyebrow': 'ஸ்மார்ட் அறிவிப்புகள்', 'home.notif_heading': 'உங்கள் கவனம் தேவைப்படுவது',
    'home.notif_body': 'உங்கள் சேமித்த பயிர் நாட்காட்டிகள் மற்றும் நேரடி வானிலையிலிருந்து — நாளை மழை, இன்று '
      + 'உரம் செலுத்த வேண்டியது, அறுவடை நெருங்குகிறது, மற்றும் பொதுவான நோய்-ஆபத்து வானிலை எச்சரிக்கைகள்.',
    'home.announcements_eyebrow': 'அறிவிப்புகள்', 'home.news_heading': 'செய்திகள்',
    'home.all_tools_eyebrow': 'அனைத்து கருவிகள்', 'home.jump_heading': 'ஒரு கருவிக்குச் செல்லவும்',
    'home.f_recommend': 'பரிந்துரை + விளைச்சல் + இலாபகரம்', 'home.f_soil_title': 'மண் ஆரோக்கியம்',
    'home.f_soil': 'மதிப்பெண், குறைபாடுகள், உரம்', 'home.f_yield_title': 'விளைச்சல் கணிப்பு',
    'home.f_yield': 'உங்கள் பகுதிக்கான எதிர்பார்க்கப்படும் டன்கள்', 'home.f_market_title': 'சந்தை விலை',
    'home.f_market': 'உண்மையான மண்டி விலைகள் + கணிப்பு', 'home.f_fertilizer': 'அளவு, செலவு, அட்டவணை',
    'home.f_profit': 'வருமானம் − செலவுகள்', 'home.f_disease_title': 'நோய் சோதனை',
    'home.f_disease': 'அறிகுறி அடிப்படையிலான குறிப்பு', 'home.f_water': '7-நாள் அட்டவணை',
    'home.f_calendar_title': 'பயிர் நாட்காட்டி', 'home.f_calendar': 'விதைப்பு முதல் அறுவடை வரையிலான தேதிகள்',
    'home.f_dashboard_title': 'பண்ணை டாஷ்போர்டு', 'home.f_dashboard': 'உங்கள் உண்மையான விளக்கப்படங்கள்',
    'home.f_map_title': 'பண்ணை வரைபடம்', 'home.f_map': 'இடம் + அருகிலுள்ள சந்தைகள்',
    'home.f_knowledge_title': 'அறிவுத் தளம்', 'home.f_knowledge': 'கட்டுரைகள், திட்டங்கள், நடைமுறைகள்',
    'home.f_chat': 'LLM சாட்பாட் (API கீ தேவை)',
    'page.records_eyebrow': 'உங்கள் தரவு', 'page.records_heading': 'பண்ணை பதிவுகள்',
    'page.dashboard_eyebrow': 'உங்கள் தரவு', 'page.dashboard_heading': 'பண்ணை டாஷ்போர்டு',
    'page.market_eyebrow': 'படி 3', 'page.market_heading': 'சந்தை விலை',
    'page.soil_eyebrow': 'படி 2', 'page.soil_heading': 'மண் ஆரோக்கிய பகுப்பாய்வு',
    'page.yield_eyebrow': 'தனி கருவி', 'page.yield_heading': 'விளைச்சல் கணிப்பு',
    'page.fertilizer_eyebrow': 'படி 4', 'page.fertilizer_heading': 'உர பரிந்துரை',
    'page.profit_eyebrow': 'தனி கருவி', 'page.profit_heading': 'லாப மதிப்பீடு',
    'page.disease_eyebrow': 'படி 5', 'page.disease_heading': 'நோய் சோதனை',
    'page.water_eyebrow': 'படி 2', 'page.water_heading': 'நீர்ப்பாசன அட்டவணை',
    'page.calendar_eyebrow': 'படி 6', 'page.calendar_heading': 'பயிர் நாட்காட்டி',
    'page.analytics_eyebrow': 'உங்கள் தரவு, தொகுக்கப்பட்டது', 'page.analytics_heading': 'பகுப்பாய்வு',
    'page.map_eyebrow': 'இலவசம், API கீ தேவையில்லை', 'page.map_heading': 'ஊடாடும் பண்ணை வரைபடம்',
    'page.knowledge_eyebrow': 'குறிப்பு', 'page.knowledge_heading': 'விவசாய அறிவுத் தளம்',
    'page.chat_eyebrow': 'உண்மையான LLM, கீ தேவை', 'page.chat_heading': 'கிருஷியிடம் கேளுங்கள்',
    'page.profile_eyebrow': 'கணக்கு அமைப்புகள்', 'page.profile_heading': 'சுயவிவரம்',
    'page.recommend_eyebrow': 'படி 1', 'page.recommend_heading': 'பயிர் பரிந்துரை',
    'page.about_eyebrow': 'தரவு பற்றிய நேர்மை', 'page.about_heading': 'எது உண்மையானது, எது லேபிளிடப்பட்ட மாற்று',
    'page.admin_eyebrow': 'நிர்வாகிகள் மட்டும்', 'page.admin_heading': 'நிர்வாக பலகம்',
    'page.login_eyebrow': 'உள்நுழைவு தேவை', 'page.login_heading': 'கிருஷியைப் பயன்படுத்த உள்நுழையவும்',
    'page.login_lead': 'இங்குள்ள ஒவ்வொரு கருவியும் — பயிர் ஆலோசகர், மண் ஆரோக்கியம், சந்தை விலைகள், '
      + 'நீர்ப்பாசனம், மற்றும் மற்றவை — உங்கள் பண்ணை சுயவிவரத்துடன் இணைக்கப்பட்டுள்ளது, எனவே இது '
      + 'உள்நுழைவுக்குப் பின்னால் உள்ளது. பதிவு செய்ய ஒரு நிமிடம் ஆகும், செலவு இல்லை.',
    'auth.login_tab': 'உள்நுழை', 'auth.register_tab': 'பதிவு', 'auth.forgot_tab': 'கடவுச்சொல் மறந்துவிட்டதா',
    'auth.email': 'மின்னஞ்சல்', 'auth.password': 'கடவுச்சொல்', 'auth.name': 'பெயர்',
    'auth.password_min': 'கடவுச்சொல் (குறைந்தது 8 எழுத்துகள்)', 'auth.confirm_password': 'கடவுச்சொல்லை உறுதிப்படுத்தவும்',
    'auth.location': 'இடம்', 'auth.farm_size': 'பண்ணை அளவு (ஏக்கர்)', 'auth.soil_type': 'மண் வகை',
    'auth.preferred_language': 'விருப்ப மொழி', 'auth.create_account': 'கணக்கை உருவாக்கவும்',
    'auth.forgot_link': 'கடவுச்சொல்லை மறந்துவிட்டீர்களா?', 'auth.no_account': 'கணக்கு இல்லையா?',
    'auth.have_account': 'ஏற்கனவே கணக்கு உள்ளதா?', 'auth.back_to_login': '← உள்நுழைவுக்குத் திரும்பு',
    'auth.forgot_title': 'உங்கள் கடவுச்சொல்லை மீட்டமைக்கவும்', 'auth.send_code': 'குறியீட்டை அனுப்பு',
    'auth.verify_code': 'குறியீட்டை சரிபார்க்கவும்', 'auth.code_label': '6-இலக்க குறியீடு',
    'auth.new_password': 'புதிய கடவுச்சொல்', 'auth.confirm_new_password': 'புதிய கடவுச்சொல்லை உறுதிப்படுத்தவும்',
    'auth.reset_password': 'கடவுச்சொல்லை மீட்டமைக்கவும்',
    'auth.forgot_step1': 'படி 1/3 — உங்கள் கணக்கு மின்னஞ்சலை உள்ளிடவும், அதற்கு 6-இலக்க குறியீட்டை அனுப்புவோம்.',
    'auth.forgot_step2': 'படி 2/3 — உங்கள் மின்னஞ்சலுக்கு அனுப்பப்பட்ட 6-இலக்க குறியீட்டை உள்ளிடவும்.',
    'auth.forgot_step3': 'படி 3/3 — குறியீடு சரிபார்க்கப்பட்டது, இப்போது உங்கள் புதிய கடவுச்சொல்லை அமைக்கவும்.',
    'auth.email_setup_summary': 'கடவுச்சொல் மீட்டமைப்பு',
    'auth.forgot_help_text': 'நீங்கள் கடவுச்சொல் மீட்டமைப்பைக் கோரும்போது உங்கள் பதிவு செய்யப்பட்ட '
      + 'முகவரிக்கு 6-இலக்க குறியீடு மின்னஞ்சல் செய்யப்படும். இது ஒரு நிமிடத்திலோ இரண்டு நிமிடத்திலோ '
      + 'வராவிட்டால், உங்கள் ஸ்பேம் கோப்புறையைச் சரிபார்க்கவும்.',
    'about.whats_real': 'உண்மையான தரவின் அடிப்படையில், யூகங்கள் அல்ல',
    'about.login_panel_body': 'பயிர் மற்றும் விளைச்சல் பரிந்துரைகள் உண்மையான வேளாண் தரவுத்தொகுப்புகள் மற்றும் '
      + 'பயிற்சி பெற்ற மாதிரிகளிலிருந்து வருகின்றன, ஸ்கிரிப்ட் செய்யப்பட்ட பதில்களிலிருந்து அல்ல. நேரடி '
      + 'வானிலை உங்கள் துல்லியமான இடத்திற்கு Open-Meteo இலிருந்து வருகிறது. சந்தை விலைகள் உண்மையான '
      + 'பதிவுசெய்யப்பட்ட மண்டி தரவு. ஏதேனும் உண்மையிலேயே இன்னும் கிடைக்கவில்லை என்றால், கிருஷி ஒரு '
      + 'எண்ணை உருவாக்குவதற்குப் பதிலாக தெளிவாகக் கூறுகிறது.',
    'auth.email_setup_body': '.env இல் SMTP_HOST/SMTP_USER/SMTP_PASSWORD அமைக்கப்பட்டிருந்தால், 6-இலக்க '
      + 'குறியீடு உண்மையில் மின்னஞ்சல் செய்யப்படும். இல்லையெனில், உண்மையில் மின்னஞ்சல் அனுப்ப வழி '
      + 'இல்லாததால், குறியீடு நேரடியாகத் திரையில் காட்டப்படும் — இது ஒரு மாற்றாக தெளிவாக '
      + 'குறிக்கப்பட்டுள்ளது, உண்மையான மின்னஞ்சலுக்கு மாற்றாக அல்ல. Gmail App Password அமைப்புக்கு '
      + '.env.example ஐப் பார்க்கவும், அல்லது உங்கள் SMTP அமைப்பை நேரடியாகச் சோதிக்க '
      + 'python scripts/test_email.py you@example.com ஐ இயக்கவும். இப்போதுதான் .env ஐத் திருத்தினீர்களா? '
      + 'சர்வரை மறுதொடக்கம் செய்யவும் — env மாறிகள் தொடக்கத்தில் ஒரு முறை மட்டுமே படிக்கப்படும்.',
  },
  te: {
    'nav.decision': '✨ AI వ్యవసాయ ప్రణాళిక', 'nav.assistant': 'AI సహాయకుడు',
    'nav.recommend': 'పంట సలహాదారు', 'nav.soil': 'నేల', 'nav.market': 'మార్కెట్', 'nav.dashboard': 'డాష్‌బోర్డ్',
    'nav.more': '☰ మరిన్ని', 'nav.yield': 'దిగుబడి', 'nav.fertilizer': 'ఎరువు', 'nav.profit': 'లాభం',
    'nav.disease': 'వ్యాధి', 'nav.water': 'నీటిపారుదల', 'nav.calendar': 'క్యాలెండర్', 'nav.records': 'రికార్డులు',
    'nav.analytics': 'విశ్లేషణ', 'nav.map': 'పటం', 'nav.knowledge': 'నేర్చుకోండి', 'nav.chat': 'కృషిని అడగండి',
    'nav.admin': 'నిర్వాహకుడు', 'nav.edit_profile': 'ప్రొఫైల్‌ను సవరించండి', 'nav.logout': 'లాగ్అవుట్',
    'nav.delete_account': 'ఖాతాను శాశ్వతంగా తొలగించండి', 'nav.login_register': 'లాగిన్ / నమోదు',
    'footer.disclaimer': 'ఒక వ్యవసాయ నిర్ణయ-మద్దతు సాధనం. సిఫార్సులు సమాచార ప్రయోజనం కోసం మాత్రమే, ప్రత్యేకించి '
      + 'అధిక-విలువ లేదా మొదటిసారి పండించే పంటలకు స్థానిక వ్యవసాయ సలహాతో కలిపి ఉపయోగించాలి.',
    'footer.data_sources': 'డేటా మూలాలు: Open-Meteo (వాతావరణం), బ్రౌజర్ GPS + రివర్స్ జియోకోడింగ్ (స్థానం), '
      + 'నిజమైన ప్రచురిత వ్యవసాయ డేటాసెట్‌లు (పంట/దిగుబడి/మార్కెట్ మోడల్‌లు), Google Gemini API (చాట్‌బాట్, కాన్ఫిగర్ చేసి ఉంటే).',
    'common.loading': 'లోడ్ అవుతోంది…',
    'notif.panel_title': 'హెచ్చరికలు',
    'home.eyebrow': 'ప్రత్యక్ష క్షేత్ర రీడింగ్', 'home.welcome': 'తిరిగి స్వాగతం',
    'home.lead': 'కృషి మీ మట్టి పరీక్ష విలువలను మీ ఖచ్చితమైన GPS స్థానం యొక్క ప్రత్యక్ష వాతావరణానికి మరియు 22 '
      + 'పంటలలో 2,200 నిజమైన క్షేత్ర నమూనాలపై శిక్షణ పొందిన మోడల్‌కు వ్యతిరేకంగా చదువుతుంది — కుడి వైపు ప్యానెల్ '
      + 'ఇప్పుడు ఆ మోడల్ నుండే తన సంఖ్యలను తీసుకుంటోంది, స్క్రిప్ట్ నుండి కాదు.',
    'home.cta_reading': 'ఒక రీడింగ్ తీసుకోండి', 'home.cta_sources': 'డేటా మూలాలను చూడండి',
    'home.model_readout': 'మోడల్ రీడౌట్', 'home.accuracy_label': 'పంట మోడల్ పరీక్ష ఖచ్చితత్వం',
    'home.training_samples': 'శిక్షణ నమూనాలు', 'home.crops_modeled': 'మోడల్ చేయబడిన పంటలు',
    'home.market_r2': 'మార్కెట్ మోడల్ R²', 'home.weather_source': 'వాతావరణ మూలం',
    'home.notif_eyebrow': 'స్మార్ట్ నోటిఫికేషన్‌లు', 'home.notif_heading': 'మీ దృష్టి అవసరమైనవి',
    'home.notif_body': 'మీ సేవ్ చేసిన పంట క్యాలెండర్‌లు మరియు ప్రత్యక్ష వాతావరణం నుండి — రేపు వర్షం, ఈరోజు '
      + 'ఎరువు గడువు, పంట కోత సమీపిస్తోంది, మరియు సాధారణ వ్యాధి-ప్రమాద వాతావరణ హెచ్చరికలు.',
    'home.announcements_eyebrow': 'ప్రకటనలు', 'home.news_heading': 'వార్తలు',
    'home.all_tools_eyebrow': 'అన్ని సాధనాలు', 'home.jump_heading': 'ఒక సాధనానికి వెళ్లండి',
    'home.f_recommend': 'సిఫార్సు + దిగుబడి + లాభదాయకత', 'home.f_soil_title': 'నేల ఆరోగ్యం',
    'home.f_soil': 'స్కోరు, లోపాలు, ఎరువు', 'home.f_yield_title': 'దిగుబడి అంచనా',
    'home.f_yield': 'మీ ప్రాంతానికి ఊహించిన టన్నులు', 'home.f_market_title': 'మార్కెట్ ధర',
    'home.f_market': 'నిజమైన మండి ధరలు + అంచనా', 'home.f_fertilizer': 'పరిమాణం, ఖర్చు, షెడ్యూల్',
    'home.f_profit': 'ఆదాయం − ఖర్చులు', 'home.f_disease_title': 'వ్యాధి పరీక్ష',
    'home.f_disease': 'లక్షణ-ఆధారిత సూచన', 'home.f_water': '7-రోజుల షెడ్యూల్',
    'home.f_calendar_title': 'పంట క్యాలెండర్', 'home.f_calendar': 'విత్తనం నుండి కోత వరకు తేదీలు',
    'home.f_dashboard_title': 'ఫార్మ్ డాష్‌బోర్డ్', 'home.f_dashboard': 'మీ నిజమైన చార్టులు',
    'home.f_map_title': 'ఫార్మ్ పటం', 'home.f_map': 'స్థానం + సమీప మార్కెట్‌లు',
    'home.f_knowledge_title': 'జ్ఞాన స్థావరం', 'home.f_knowledge': 'వ్యాసాలు, పథకాలు, పద్ధతులు',
    'home.f_chat': 'LLM చాట్‌బాట్ (API కీ అవసరం)',
    'page.records_eyebrow': 'మీ డేటా', 'page.records_heading': 'ఫార్మ్ రికార్డులు',
    'page.dashboard_eyebrow': 'మీ డేటా', 'page.dashboard_heading': 'ఫార్మ్ డాష్‌బోర్డ్',
    'page.market_eyebrow': 'దశ 3', 'page.market_heading': 'మార్కెట్ ధర',
    'page.soil_eyebrow': 'దశ 2', 'page.soil_heading': 'నేల ఆరోగ్య విశ్లేషణ',
    'page.yield_eyebrow': 'స్వతంత్ర సాధనం', 'page.yield_heading': 'దిగుబడి అంచనా',
    'page.fertilizer_eyebrow': 'దశ 4', 'page.fertilizer_heading': 'ఎరువు సిఫార్సు',
    'page.profit_eyebrow': 'స్వతంత్ర సాధనం', 'page.profit_heading': 'లాభ అంచనా',
    'page.disease_eyebrow': 'దశ 5', 'page.disease_heading': 'వ్యాధి పరీక్ష',
    'page.water_eyebrow': 'దశ 2', 'page.water_heading': 'నీటిపారుదల షెడ్యూల్',
    'page.calendar_eyebrow': 'దశ 6', 'page.calendar_heading': 'పంట క్యాలెండర్',
    'page.analytics_eyebrow': 'మీ డేటా, సమీకరించబడింది', 'page.analytics_heading': 'విశ్లేషణ',
    'page.map_eyebrow': 'ఉచితం, API కీ అవసరం లేదు', 'page.map_heading': 'ఇంటరాక్టివ్ ఫార్మ్ పటం',
    'page.knowledge_eyebrow': 'సూచన', 'page.knowledge_heading': 'వ్యవసాయ జ్ఞాన స్థావరం',
    'page.chat_eyebrow': 'నిజమైన LLM, కీ అవసరం', 'page.chat_heading': 'కృషిని అడగండి',
    'page.profile_eyebrow': 'ఖాతా సెట్టింగ్‌లు', 'page.profile_heading': 'ప్రొఫైల్',
    'page.recommend_eyebrow': 'దశ 1', 'page.recommend_heading': 'పంట సిఫార్సు',
    'page.about_eyebrow': 'డేటా గురించి నిజాయితీ', 'page.about_heading': 'ఏది నిజమైనది, ఏది లేబుల్ చేయబడిన ప్రత్యామ్నాయం',
    'page.admin_eyebrow': 'నిర్వాహకులకు మాత్రమే', 'page.admin_heading': 'నిర్వాహక ప్యానెల్',
    'page.login_eyebrow': 'సైన్ ఇన్ అవసరం', 'page.login_heading': 'కృషిని ఉపయోగించడానికి సైన్ ఇన్ చేయండి',
    'page.login_lead': 'ఇక్కడున్న ప్రతి సాధనం — పంట సలహాదారు, నేల ఆరోగ్యం, మార్కెట్ ధరలు, నీటిపారుదల, '
      + 'మరియు మిగిలినవి — మీ ఫార్మ్ ప్రొఫైల్‌తో అనుసంధానించబడి ఉంది, కాబట్టి ఇది సైన్-ఇన్ వెనుక ఉంది. '
      + 'నమోదు చేయడానికి ఒక నిమిషం పడుతుంది మరియు ఎటువంటి ఖర్చు లేదు.',
    'auth.login_tab': 'లాగిన్', 'auth.register_tab': 'నమోదు', 'auth.forgot_tab': 'పాస్‌వర్డ్ మర్చిపోయారా',
    'auth.email': 'ఇమెయిల్', 'auth.password': 'పాస్‌వర్డ్', 'auth.name': 'పేరు',
    'auth.password_min': 'పాస్‌వర్డ్ (కనీసం 8 అక్షరాలు)', 'auth.confirm_password': 'పాస్‌వర్డ్‌ను నిర్ధారించండి',
    'auth.location': 'స్థానం', 'auth.farm_size': 'ఫార్మ్ పరిమాణం (ఎకరాలు)', 'auth.soil_type': 'నేల రకం',
    'auth.preferred_language': 'ఇష్టపడే భాష', 'auth.create_account': 'ఖాతాను సృష్టించండి',
    'auth.forgot_link': 'పాస్‌వర్డ్ మర్చిపోయారా?', 'auth.no_account': 'ఖాతా లేదా?',
    'auth.have_account': 'ఇప్పటికే ఖాతా ఉందా?', 'auth.back_to_login': '← లాగిన్‌కు తిరిగి వెళ్లండి',
    'auth.forgot_title': 'మీ పాస్‌వర్డ్‌ను రీసెట్ చేయండి', 'auth.send_code': 'కోడ్ పంపండి',
    'auth.verify_code': 'కోడ్‌ను ధృవీకరించండి', 'auth.code_label': '6-అంకెల కోడ్',
    'auth.new_password': 'కొత్త పాస్‌వర్డ్', 'auth.confirm_new_password': 'కొత్త పాస్‌వర్డ్‌ను నిర్ధారించండి',
    'auth.reset_password': 'పాస్‌వర్డ్‌ను రీసెట్ చేయండి',
    'auth.forgot_step1': 'దశ 1/3 — మీ ఖాతా ఇమెయిల్‌ను నమోదు చేయండి, మేము దానికి 6-అంకెల కోడ్ పంపుతాము.',
    'auth.forgot_step2': 'దశ 2/3 — మీ ఇమెయిల్‌కు పంపిన 6-అంకెల కోడ్‌ను నమోదు చేయండి.',
    'auth.forgot_step3': 'దశ 3/3 — కోడ్ ధృవీకరించబడింది, ఇప్పుడు మీ కొత్త పాస్‌వర్డ్‌ను సెట్ చేయండి.',
    'auth.email_setup_summary': 'పాస్‌వర్డ్ రీసెట్',
    'auth.forgot_help_text': 'మీరు పాస్‌వర్డ్ రీసెట్‌ను అభ్యర్థించినప్పుడు మీ నమోదిత చిరునామాకు 6-అంకెల '
      + 'కోడ్ ఇమెయిల్ చేయబడుతుంది. ఇది ఒకటి రెండు నిమిషాల్లో రాకపోతే, మీ స్పామ్ ఫోల్డర్‌ను తనిఖీ చేయండి.',
    'about.whats_real': 'నిజమైన డేటాపై నిర్మించబడింది, ఊహలపై కాదు',
    'about.login_panel_body': 'పంట మరియు దిగుబడి సిఫార్సులు నిజమైన వ్యవసాయ డేటాసెట్‌లు మరియు శిక్షణ పొందిన '
      + 'మోడల్‌ల నుండి వస్తాయి, స్క్రిప్ట్ చేసిన ప్రతిస్పందనల నుండి కాదు. ప్రత్యక్ష వాతావరణం మీ ఖచ్చితమైన '
      + 'స్థానానికి Open-Meteo నుండి వస్తుంది. మార్కెట్ ధరలు నిజమైన నమోదిత మండి డేటా. ఏదైనా నిజంగా '
      + 'ఇంకా అందుబాటులో లేకపోతే, కృషి ఒక సంఖ్యను సృష్టించే బదులు స్పష్టంగా చెబుతుంది.',
    'auth.email_setup_body': '.env లో SMTP_HOST/SMTP_USER/SMTP_PASSWORD సెట్ చేసి ఉంటే, 6-అంకెల కోడ్ '
      + 'నిజంగా ఇమెయిల్ చేయబడుతుంది. అది లేకుండా, నిజంగా ఇమెయిల్ చేరవేయడానికి మార్గం లేదు, కాబట్టి '
      + 'కోడ్ నేరుగా స్క్రీన్‌పై చూపబడుతుంది — ఇది ఫాల్‌బ్యాక్‌గా స్పష్టంగా లేబుల్ చేయబడింది, నిజమైన '
      + 'ఇమెయిల్‌కు ప్రత్యామ్నాయం కాదు. Gmail App Password సెటప్ కోసం .env.example చూడండి, లేదా మీ '
      + 'SMTP సెటప్‌ను నేరుగా పరీక్షించడానికి python scripts/test_email.py you@example.com '
      + 'నడపండి. ఇప్పుడే .env సవరించారా? సర్వర్‌ను పునఃప్రారంభించండి — env వేరియబుల్స్ స్టార్టప్‌లో '
      + 'ఒక్కసారి మాత్రమే చదవబడతాయి.',
  },
};
