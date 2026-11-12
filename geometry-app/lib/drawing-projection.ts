export type Residual = (coordinates:number[])=>number;

function jacobian(coordinates:number[],variables:number[],equations:Residual[]){
 const rows=equations.map(()=>Array<number>(variables.length).fill(0));
 for(const [column,index] of variables.entries()){
  const original=coordinates[index],step=2e-6*Math.max(1,Math.abs(original));
  coordinates[index]=original+step;
  const above=equations.map(equation=>equation(coordinates));
  coordinates[index]=original-step;
  for(const [row,equation] of equations.entries())rows[row][column]=(above[row]-equation(coordinates))/(2*step);
  coordinates[index]=original;
 }
 return rows;
}

/** An inferred anchor can be released when both driver axes are fixed by
 * the local equations. A perpendicular pointer on a one-dimensional locus
 * does not make that locus immobile. */
export function dragTangent(coordinates:number[],variables:number[],mobility:number[],equations:Residual[],driver:number,delta:number[]){
 const driverAxes=[variables.indexOf(driver),variables.indexOf(driver+1)].filter(axis=>axis>=0);
 const basis:number[][]=[];
 for(const row of jacobian(coordinates,variables,equations)){
  for(let i=0;i<row.length;i++)row[i]*=mobility[i];
  const norm=Math.hypot(...row);
  if(norm<1e-10)continue;
  const direction=row.map(value=>value/norm);
  // Re-orthogonalize nearly redundant conditions, e.g. a midpoint and
  // collinearity expressed separately.
  for(let pass=0;pass<2;pass++)for(const normal of basis){
   const overlap=normal.reduce((sum,value,i)=>sum+value*direction[i],0);
   for(let i=0;i<direction.length;i++)direction[i]-=overlap*normal[i];
  }
  const remaining=Math.hypot(...direction);
  if(remaining>2e-5)basis.push(direction.map(value=>value/remaining));
 }
 const movable=driverAxes.some(axis=>1-basis.reduce((sum,row)=>sum+row[axis]**2,0)>1e-8);
 const step=variables.map((index,i)=>(index===driver||index===driver+1?delta[index-driver]:0)/mobility[i]);
 for(const normal of basis){
  const overlap=normal.reduce((sum,value,i)=>sum+value*step[i],0);
  for(let i=0;i<step.length;i++)step[i]-=overlap*normal[i];
 }
 return {movable,step:step.map((value,i)=>value*mobility[i])};
}

function solveSymmetric(matrix:number[][],rhs:number[]){
 // The diagonal damping makes the normal matrix positive definite.
 for(let i=0;i<rhs.length;i++)for(let j=0;j<=i;j++){
  let value=matrix[i][j];
  for(let k=0;k<j;k++)value-=matrix[i][k]*matrix[j][k];
  if(i===j&&!(value>0))return;
  matrix[i][j]=i===j?Math.sqrt(value):value/matrix[j][j];
 }
 for(let i=0;i<rhs.length;i++){
  for(let j=0;j<i;j++)rhs[i]-=matrix[i][j]*rhs[j];
  rhs[i]/=matrix[i][i];
 }
 for(let i=rhs.length-1;i>=0;i--){
  for(let j=i+1;j<rhs.length;j++)rhs[i]-=matrix[j][i]*rhs[j];
  rhs[i]/=matrix[i][i];
 }
 return rhs;
}

/** Retract a pointer step onto the equations, with smaller changes to the
 * pointer and reference vertices. The caller independently checks geometry. */
export function correctProjection(coordinates:number[],variables:number[],mobility:number[],equations:Residual[],limits:Residual[],accept:()=>boolean,deadline:number){
 if(!variables.length)return false;
 for(let iteration=0;iteration<9&&performance.now()<deadline;iteration++){
  const active=[...equations,...limits.filter(limit=>limit(coordinates)<0)];
  if(!active.length)return false;
  const residuals=active.map(equation=>equation(coordinates));
  const rows=jacobian(coordinates,variables,active);
  const scales=rows.map(row=>Math.max(Math.hypot(...row),1e-5));
  const width=variables.length,matrix=variables.map(()=>Array<number>(width).fill(0)),rhs=variables.map(()=>0);
  for(let i=0;i<width;i++)matrix[i][i]=1e-7;
  for(const [row,gradient] of rows.entries()){
   const coefficients=gradient.map((value,i)=>value*mobility[i]/scales[row]);
   for(let i=0;i<width;i++){
    rhs[i]-=coefficients[i]*residuals[row]/scales[row];
    for(let j=0;j<=i;j++)matrix[i][j]+=coefficients[i]*coefficients[j];
   }
  }
  const solution=solveSymmetric(matrix,rhs);
  if(!solution||solution.some(value=>!Number.isFinite(value)))return false;
  const before=variables.map(index=>coordinates[index]);
  const error=(values:number[])=>values.reduce((sum,value,i)=>sum+(value/scales[i])**2,0);
  const initialError=error(residuals);
  let improved=false;
  for(const fraction of [1,.5,.25,.125]){
   for(const [i,index] of variables.entries())coordinates[index]=before[i]+fraction*solution[i]*mobility[i];
   if(accept())return true;
   const after=active.map((equation,i)=>i<equations.length?equation(coordinates):Math.min(0,equation(coordinates)));
   if(error(after)<initialError){improved=true;break}
  }
  if(!improved){
   for(const [i,index] of variables.entries())coordinates[index]=before[i];
   return false;
  }
 }
 return false;
}
