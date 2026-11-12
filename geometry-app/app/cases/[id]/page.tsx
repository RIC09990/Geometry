import {GeometryApp} from '@/components/geometry/app';
import {notFound} from 'next/navigation';
export default async function Workspace({params}:{params:Promise<{id:string}>}){const {id}=await params;if(id==='new')notFound();return <GeometryApp page="workspace" caseId={id}/>;}
