'use client';
import {createContext,useContext,useEffect,useState,useSyncExternalStore,type ReactNode} from 'react';
import {useAiCredentials} from './ai-credentials';
import {createAiChatSession,type AiChatSession} from './ai-chat-session';

const Context=createContext<AiChatSession|undefined>(undefined);
export function AiChatSessionProvider({children}:{children:ReactNode}){
 const [session]=useState(createAiChatSession),credentials=useAiCredentials();
 // This effect belongs to the persistent root, not a page being revisited.
 useEffect(()=>{session.credentialsChanged()},[session,credentials.mode,credentials.key,credentials.config]);
 useEffect(()=>()=>session.dispose(),[session]);
 return <Context.Provider value={session}>{children}</Context.Provider>;
}
export function useAiChatSession(){
 const shared=useContext(Context),[standalone]=useState(()=>shared?undefined:createAiChatSession());
 return shared||standalone!;
}
export function useAiChatState(){const session=useAiChatSession();return {session,state:useSyncExternalStore(session.subscribe,session.getSnapshot,session.getSnapshot)}}
export function useAiChatActivity(){const session=useAiChatSession();return useSyncExternalStore(session.subscribe,session.getActivity,session.getActivity)}
