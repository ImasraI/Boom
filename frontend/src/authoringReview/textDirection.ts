/** Presentation only: preserve every character; never reconstruct damaged PDF math. */
export function directionRuns(text: string): {value:string; ltr:boolean}[] {
  const runs:{value:string;ltr:boolean}[]=[];
  const pattern=/[A-Za-zΑ-ω0-9۰-۹٠-٩()[\]{}+−=×÷*/^_.:,<>≤≥∞∑√|%-]+(?:[ \t]+[A-Za-zΑ-ω0-9۰-۹٠-٩()[\]{}+−=×÷*/^_.:,<>≤≥∞∑√|%-]+)*/g;
  let cursor=0;
  for(const match of text.matchAll(pattern)) {
    if(!/[A-Za-zΑ-ω0-9۰-۹٠-٩]/.test(match[0]))continue;
    const start=match.index!;
    if(start>cursor)runs.push({value:text.slice(cursor,start),ltr:false});
    runs.push({value:match[0],ltr:true});cursor=start+match[0].length;
  }
  if(cursor<text.length)runs.push({value:text.slice(cursor),ltr:false});
  return runs;
}
