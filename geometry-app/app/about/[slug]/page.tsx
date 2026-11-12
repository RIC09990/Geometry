import {notFound} from 'next/navigation';
import {GeometryApp} from '@/components/geometry/app';
export default async function AboutDetailPage({params}:{params:Promise<{slug:string}>}){
 const {slug}=await params;
 if(!['privacy','data','terms','contact'].includes(slug))notFound();
 return <GeometryApp key={slug} page="about-detail" aboutId={slug}/>;
}
