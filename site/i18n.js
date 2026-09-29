(() => {
  const english = document.documentElement.lang === "en";
  const root = new URL(english ? "../" : "./", location.href);
  const japanese = /[ぁ-ヿ㐀-鿿]/;
  const values = /`[^`]+`|https?:\/\/[^\s<>)]*|(?<![A-Za-z_])[ABC](?![A-Za-z_])|[+−-]?\d+(?:[.,]\d+)*/g;
  function translate(text) {
    if (!english || !japanese.test(text) || /^https?:\/\//.test(text)) return text;
    const parameters = [];
    const key = text.trim().replace(/\s+/g, " ").replace(values, value => {
      parameters.push(value);
      return `{${parameters.length - 1}}`;
    });
    const message = globalThis.RHINO_EN?.[key];
    if (message === undefined) throw new Error(`Missing English display translation: ${key}`);
    return message.replace(/\{(\d+)\}/g, (_, index) => parameters[Number(index)]);
  }
  function localizeData(value) {
    if (!english) return value;
    if (typeof value === "string") return translate(value);
    if (Array.isArray(value)) return value.map(localizeData);
    if (value && typeof value === "object") {
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, localizeData(item)]));
    }
    return value;
  }
  function languageLinks() {
    for (const link of document.querySelectorAll("[data-language-link]")) {
      const target = new URL(link.href);
      target.search = location.search;
      target.hash = location.hash;
      link.href = target.href;
    }
  }
  function selectDesign(design) {
    const url = new URL(location.href);
    url.searchParams.set("design", design);
    history.replaceState(null, "", url);
    languageLinks();
  }
  globalThis.RhinoLocale = {
    english, translate, localizeData, languageLinks, selectDesign,
    text: (ja, en) => english ? en : ja,
    asset: path => new URL(path, root).href,
  };
  languageLinks();
  window.addEventListener("hashchange", languageLinks);
  for (const link of document.querySelectorAll("[data-language-link]")) {
    link.addEventListener("click", languageLinks);
  }
})();
