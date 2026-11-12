// Vinext retains a lazy namespace in a variable. Rolldown's shared-chunk pass
// loses that namespace boundary. Explicit static property reads preserve it.
const navigationExports = [
  'navigateClientSide', 'getPrefetchInterceptionContext', 'getPrefetchCache',
  'getPrefetchedUrls', 'getMountedSlotsHeader', 'createAppPrefetchRequestHeaders',
  'discardLearningOnlyPrefetchCacheEntry', 'hasSearchAgnosticPrefetchShellForRoute',
  'hasPrefetchCacheEntryForNavigation', 'peekPrefetchResponseForNavigation',
  'prefetchRscResponse', 'prepareNavigationPrefetchSnapshot',
  'DYNAMIC_NAVIGATION_CACHE_TTL', 'restoreRscResponse', 'PREFETCH_CACHE_TTL',
];
export function navigationCompat() {
  return {
    name: 'geometry:vinext-navigation-compat',
    enforce: 'pre',
    transform(code, id) {
      if (!id.replaceAll('\\', '/').endsWith('/vinext/dist/shims/link.js')) return;
      const modules = {
        './navigation.js': navigationExports,
        '../server/app-elements.js': ['AppElementsWire'],
        '../server/app-rsc-cache-busting.js': ['createRscRequestUrl', 'stripRscCacheBustingSearchParam', 'stripRscSuffix'],
        '../server/app-rsc-render-mode.js': ['APP_RSC_RENDER_MODE_PREFETCH_DYNAMIC_SHELL', 'APP_RSC_RENDER_MODE_PREFETCH_LOADING_SHELL'],
        '../server/headers.js': ['NEXT_ROUTER_PREFETCH_HEADER', 'NEXT_ROUTER_SEGMENT_PREFETCH_HEADER', 'VINEXT_MOUNTED_SLOTS_HEADER'],
      };
      let imports = '';
      for (const [path, names] of Object.entries(modules)) {
        const original = `import("${path}")`;
        if (!code.includes(original)) continue;
        imports += `import {${names.map(name => `${name} as geometry_${name}`).join(',')}} from "${path}";\n`;
        code = code.replaceAll(original, `Promise.resolve({${names.map(name => `${name}: geometry_${name}`).join(',')}})`);
      }
      return {code: imports + code, map: null};
    },
  };
}
