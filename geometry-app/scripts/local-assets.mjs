// Build-stamped assets are safe to reuse for a week. HTML must revalidate after deployments.
const artwork=/^\/(?:(?:archive-collage|mobius-strip)\.[a-f0-9]{12}\.webp|euclid-book1-plate1\.[a-f0-9]{12}\.jpg)$/;
export function staticAssetPath(pathname){
  return /^\/_next\/static\/[^\\]+$/.test(pathname)||artwork.test(pathname)||pathname==='/favicon.svg';
}
export function assetCacheControl(pathname,status=200){
  if(![200,304].includes(status)||!staticAssetPath(pathname))return 'no-store, max-age=0';
  return pathname.startsWith('/_next/static/')||artwork.test(pathname)
    ?'public, max-age=604800, immutable':'public, max-age=0, must-revalidate';
}

export function responseCacheControl(pathname,status,requestHeaders={},responseHeaders={}){
  const credentials=requestHeaders['x-ai-api-key']||requestHeaders['x-deepseek-api-key']||requestHeaders.authorization;
  const privateResponse=/(?:^|,)\s*(?:private|no-store)(?:\s|,|=|$)/i.test(String(responseHeaders['cache-control']||''));
  if(credentials||responseHeaders['set-cookie']||privateResponse)return 'no-store, max-age=0';
  if(staticAssetPath(pathname))return assetCacheControl(pathname,status);
  const html=status===304||String(responseHeaders['content-type']||'').toLowerCase().startsWith('text/html');
  const rsc=pathname.endsWith('.rsc')||requestHeaders.rsc==='1'||String(requestHeaders.accept||'').includes('text/x-component');
  return [200,304].includes(status)&&html&&!rsc&&!pathname.startsWith('/api/')
    ?'private, max-age=0, must-revalidate':'no-store, max-age=0';
}

export function preferredEncoding(header=''){
  const choices=new Map(String(header).toLowerCase().split(',').map(value=>{
    const [name,...parameters]=value.trim().split(';');
    const q=parameters.find(p=>p.trim().startsWith('q='));
    const quality=q===undefined?1:Number(q.trim().slice(2));
    return [name,Number.isFinite(quality)&&quality>=0&&quality<=1?quality:0];
  }));
  const quality=name=>choices.has(name)?choices.get(name):(choices.get('*')||0);
  const br=quality('br'),gzip=quality('gzip');
  if(choices.has('identity')&&choices.get('identity')>Math.max(br,gzip))return null;
  return br>0&&br>=gzip?'br':gzip>0?'gzip':null;
}

export function compressibleAsset(pathname,contentType=''){
  return staticAssetPath(pathname)&&/^(?:text\/(?:javascript|css|plain)|application\/(?:javascript|json)|image\/svg\+xml)(?:;|$)/i.test(contentType);
}
