// Current app browsers support WOFF2. Do not emit duplicate KaTeX TTF/WOFF fallbacks.
export function modernMathFonts(){
 return {postcssPlugin:'geometry:modern-math-fonts',AtRule:{'font-face'(rule){
  const family=rule.nodes?.find(n=>n.type==='decl'&&n.prop==='font-family')?.value||'';
  if(!/^['"]?KaTeX_/.test(family))return;
  rule.walkDecls('src',decl=>{
   const woff2=decl.value.split(',').filter(value=>/format\(['"]woff2['"]\)/.test(value));
   if(woff2.length)decl.value=woff2.join(',');
  });
 }}};
}

// Vite may collect imported font files before PostCSS removes the fallback URL.
// Remove only generated KaTeX fallback assets which no CSS or JS still references.
export function compactMathFontAssets(){
 return {name:'geometry:compact-math-font-assets',apply:'build',enforce:'post',generateBundle:{order:'post',handler(_options,bundle){
  const used=Object.values(bundle).filter(item=>item.type==='chunk'||/\.css$/.test(item.fileName)).map(item=>item.type==='chunk'?item.code:String(item.source)).join('\n');
  const removed=new Set();
  for(const [key,item] of Object.entries(bundle)){
   const name=item.fileName.split('/').pop();
   if(item.type==='asset'&&/^KaTeX_.*\.(?:woff|ttf)$/.test(name)&&!used.includes(name)){removed.add(item.fileName);delete bundle[key]}
  }
  for(const item of Object.values(bundle)){
   if(item.type!=='asset'||!item.fileName.endsWith('manifest.json'))continue;
   try{const data=JSON.parse(String(item.source));for(const entry of Object.values(data))if(entry&&Array.isArray(entry.assets))entry.assets=entry.assets.filter(path=>!removed.has(path));item.source=JSON.stringify(data)}catch{/* Not a Vite asset manifest. */}
  }
 }}};
}
