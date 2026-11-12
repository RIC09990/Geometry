'use client';
import {useEffect,useId,useRef,useState} from 'react';
import {Point,Problem} from '@/lib/geometry';
import {useT} from '@/lib/i18n';
import {createScene,fitBounds,type BoardScene} from './board-scene';
import {BoardMeasurements} from './board-measurements';
export type BoardProps={problem:Problem;onDragStart?:()=>void;onMove?:(point:Point,preview:Point[])=>Promise<Point[]|undefined>|void;readOnly?:boolean;labels?:boolean;small?:boolean;onReady?:(fit:()=>void)=>void;onPreview?:(points:Point[])=>void;onConstraintState?:(valid:boolean)=>void;measurements?:boolean;placementMessage?:string};
/** Coordinate and UI changes update the existing board, preserving the viewport and SVG. */
export function GeometryBoard(props:BoardProps){
 const {problem,small=false}=props,t=useT();
 const id='board-'+useId().replace(/[^a-zA-Z0-9]/g,'');
 const [live,setLive]=useState(problem.points),[placementValid,setPlacementValid]=useState(false);const latest=useRef(props);latest.current={...props,onPreview:points=>{setLive(points);props.onPreview?.(points)},onConstraintState:valid=>{setPlacementValid(valid);props.onConstraintState?.(valid)}};
 const scene=useRef<BoardScene|undefined>(undefined);const [error,setError]=useState(false);
 useEffect(()=>{
  let disposed=false,board:any,JX:any,observer:ResizeObserver|undefined,resizeFrame=0;
  (async()=>{try{
   const mod=await import('jsxgraph');if(disposed)return;JX=mod.default;
   const container=document.getElementById(id)!;
   board=JX.JSXGraph.initBoard(id,{boundingbox:fitBounds(latest.current.problem,container.clientWidth/container.clientHeight),axis:false,showCopyright:false,showNavigation:false,showFullscreen:false,keepaspectratio:true,resize:{enabled:false},pan:{enabled:!small},zoom:{enabled:!small,wheel:true},renderer:'svg'});
   const runtime=createScene(board,JX,()=>latest.current);scene.current=runtime;runtime.sync();latest.current.onReady?.(()=>runtime.fit());
   let width=0,height=0;
   observer=new ResizeObserver(entries=>{const size=entries[entries.length-1].contentRect;if(size.width<=0||size.height<=0||(Math.abs(width-size.width)<.5&&Math.abs(height-size.height)<.5))return;width=size.width;height=size.height;cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>{if(disposed)return;board.resizeContainer(width,height,true,true);runtime.fit()})});observer.observe(container);
  }catch(e){if(!disposed){console.error('Geometry board:',e);setError(true)}}})();
  return()=>{disposed=true;observer?.disconnect();cancelAnimationFrame(resizeFrame);scene.current?.dispose();scene.current=undefined;if(board&&JX)JX.JSXGraph.freeBoard(board)};
 },[id,small]);
 useEffect(()=>{if(scene.current)scene.current.sync();else setLive(problem.points)},[problem,props.labels,props.readOnly]);
 return <><div id={id} className={'geometry-board '+(small?'mini-board ':'')} aria-label={t(small?`${problem.title} 示意图`:'可拖动的动态几何画板')}/>{!placementValid&&!small&&<p role="status" className="board-placement-error">{t(props.placementMessage||'当前条件尚未得到有效图形。请检查冲突条件或未识别的文字条件。')}</p>}{props.measurements&&!small&&placementValid&&<BoardMeasurements points={live} goal={problem.goal}/>} {error&&<p role="status" className="empty">{t('几何画板暂时无法显示，请刷新页面后重试。')}</p>}</>;
}
