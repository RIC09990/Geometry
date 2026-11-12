export type AiImage={name:string;dataUrl:string};
export type AiAttachment=AiImage&{id:string;text?:string};
const readDataUrl=(file:Blob)=>new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(new Error('文件读取失败'));reader.readAsDataURL(file)});
export async function readAiFiles(files:File[],progress:(label:string)=>void):Promise<AiAttachment[]>{
 const output:AiAttachment[]=[];
 for(const file of files){
  progress(file.name);
  if(file.type.startsWith('image/')||/\.(png|jpe?g|gif|webp)$/i.test(file.name)){
   if(file.size>32*1024*1024)throw new Error('单张图片超过32 MiB，请压缩后重试。');
   output.push({id:crypto.randomUUID(),name:file.name,dataUrl:await readDataUrl(file)});
  }else if(file.type==='application/pdf'||/\.pdf$/i.test(file.name)){
   const pdfjs=await import('pdfjs-dist');pdfjs.GlobalWorkerOptions.workerSrc=new URL('../node_modules/pdfjs-dist/build/pdf.worker.min.mjs',import.meta.url).href;
   const task=pdfjs.getDocument({data:await file.arrayBuffer()});const document=await task.promise;
   try{for(let pageNumber=1;pageNumber<=document.numPages;pageNumber++){
    progress(`${file.name} · ${pageNumber}/${document.numPages}`);
    const page=await document.getPage(pageNumber),natural=page.getViewport({scale:1}),scale=Math.min(2.5,2400/Math.max(natural.width,natural.height)),viewport=page.getViewport({scale});
    const canvas=window.document.createElement('canvas');canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
    await page.render({canvas,canvasContext:canvas.getContext('2d')!,viewport}).promise;
    output.push({id:crypto.randomUUID(),name:`${file.name} · ${pageNumber}`,dataUrl:canvas.toDataURL('image/jpeg',.93)});canvas.width=canvas.height=0;page.cleanup();
    if(output.reduce((sum,f)=>sum+f.dataUrl.length,0)>45*1024*1024)throw new Error('附件超过单次请求容量，请分批发送。');
   }}finally{await task.destroy()}
  }else if(/\.(txt|md)$/i.test(file.name)){
   const text=await file.text();if(text.length>100000)throw new Error('文字文件较长，请分段上传。');
   output.push({id:crypto.randomUUID(),name:file.name,dataUrl:'',text});
  }else throw new Error('支持图片、PDF、TXT 和 Markdown。手写文档可导出为 PDF 或拍照上传。');
 }
 return output;
}
export function attachmentText(files:AiAttachment[]){return files.filter(f=>f.text!==undefined).map(f=>`\n\n附件 ${f.name}：\n${f.text}`).join('')}
export function attachmentImages(files:AiAttachment[]):AiImage[]{return files.filter(f=>f.dataUrl).map(({name,dataUrl})=>({name,dataUrl}))}
