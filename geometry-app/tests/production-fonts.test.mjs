import test from 'node:test';
import assert from 'node:assert/strict';
import postcss from 'postcss';
import {modernMathFonts,compactMathFontAssets} from '../scripts/vite/modern-math-fonts.mjs';

test('Only redundant math font fallbacks are removed; font style and other families are retained',async()=>{
 const input=`@font-face{font-family:KaTeX_Main;src:url(a.woff2) format('woff2'),url(a.woff) format('woff'),url(a.ttf) format('truetype');font-style:italic;font-weight:700}@font-face{font-family:Other;src:url(b.ttf) format('truetype')}@font-face{font-family:KaTeX_Old;src:url(c.ttf) format('truetype')}`;
 const {css}=await postcss([modernMathFonts()]).process(input,{from:undefined});
 assert.ok(css.includes("src:url(a.woff2) format('woff2');font-style:italic;font-weight:700"));
 assert.ok(!css.includes('url(a.woff)'));assert.ok(!css.includes('url(a.ttf)'));
 assert.ok(css.includes("src:url(b.ttf) format('truetype')"));assert.ok(css.includes("src:url(c.ttf) format('truetype')"));
});

test('Production cleanup keeps referenced fallbacks and only removes unused generated KaTeX duplicates',()=>{
 const asset=(fileName,source='font-bytes')=>({type:'asset',fileName,source});
 const bundle={a:asset('KaTeX_Main.hash.ttf'),b:asset('KaTeX_Main.hash.woff'),c:asset('KaTeX_Main.hash.woff2'),d:asset('Other.ttf'),css:asset('style.css','url(KaTeX_Main.hash.woff2);url(KaTeX_Main.hash.woff)'),manifest:asset('.vite/manifest.json',JSON.stringify({main:{assets:['KaTeX_Main.hash.ttf','KaTeX_Main.hash.woff2']}}))};
 compactMathFontAssets().generateBundle.handler({},bundle);
 assert.equal(bundle.a,undefined);assert.ok(bundle.b);assert.ok(bundle.c);assert.ok(bundle.d);
 assert.deepEqual(JSON.parse(bundle.manifest.source).main.assets,['KaTeX_Main.hash.woff2']);
});
