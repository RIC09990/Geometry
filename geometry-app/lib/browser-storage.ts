// Resolve browser storage lazily so importing this module during SSR is safe.
function persistentStorage():Storage|undefined{
  return typeof window==='undefined'?undefined:window.localStorage;
}
function sessionOnlyStorage():Storage|undefined{
  return typeof window==='undefined'?undefined:window.sessionStorage;
}

export const browserStorage:Storage={
  get length(){return persistentStorage()?.length??0;},
  clear(){persistentStorage()?.clear();},
  getItem(key:string){return persistentStorage()?.getItem(key)??null;},
  key(index:number){return persistentStorage()?.key(index)??null;},
  removeItem(key:string){persistentStorage()?.removeItem(key);},
  setItem(key:string,value:string){persistentStorage()?.setItem(key,value);},
};
export const browserSessionStorage:Storage={
  get length(){return sessionOnlyStorage()?.length??0;},
  clear(){sessionOnlyStorage()?.clear();},
  getItem(key:string){return sessionOnlyStorage()?.getItem(key)??null;},
  key(index:number){return sessionOnlyStorage()?.key(index)??null;},
  removeItem(key:string){sessionOnlyStorage()?.removeItem(key);},
  setItem(key:string,value:string){sessionOnlyStorage()?.setItem(key,value);},
};
