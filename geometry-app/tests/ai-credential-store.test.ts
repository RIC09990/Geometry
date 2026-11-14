import test from 'node:test';
import assert from 'node:assert/strict';
import {CREDENTIAL_SESSION_KEY,clearCredentialSession,readCredentialSession,saveCredentialSession} from '../lib/ai-credential-store';
import {aiProviders} from '../lib/ai-providers';

function fakeStorage(){
 const values=new Map<string,string>();
 return {getItem:(name:string)=>values.get(name)??null,setItem:(name:string,value:string)=>{values.set(name,value)},removeItem:(name:string)=>{values.delete(name)},values} as unknown as Storage&{values:Map<string,string>};
}

const custom={provider:'compatible',baseUrl:'https://relay.example/v1',protocol:'chat' as const,model:'deepseek-v4.1-flash'};

test('A saved key and connection survive in session storage',()=>{
 const storage=fakeStorage();
 saveCredentialSession(storage,'sk-test-123',custom);
 const saved=readCredentialSession(storage);
 assert.equal(saved?.key,'sk-test-123');
 assert.deepEqual(saved?.config,custom);
});

test('The official presets keep their thinking level',()=>{
 const storage=fakeStorage();
 saveCredentialSession(storage,'sk-test-123',aiProviders.deepseek.config);
 assert.deepEqual(readCredentialSession(storage)?.config,aiProviders.deepseek.config);
});

test('Unreadable or incomplete records are ignored',()=>{
 const storage=fakeStorage();
 storage.setItem(CREDENTIAL_SESSION_KEY,'{');
 assert.equal(readCredentialSession(storage),undefined);
 storage.setItem(CREDENTIAL_SESSION_KEY,JSON.stringify({key:'',config:custom}));
 assert.equal(readCredentialSession(storage),undefined);
 storage.setItem(CREDENTIAL_SESSION_KEY,JSON.stringify({key:'sk-test-123',config:{provider:'x',baseUrl:'',model:'',protocol:'carrier-pigeon'}}));
 assert.equal(readCredentialSession(storage),undefined);
});

test('Clearing removes the saved key',()=>{
 const storage=fakeStorage();
 saveCredentialSession(storage,'sk-test-123',custom);
 clearCredentialSession(storage);
 assert.equal(storage.getItem(CREDENTIAL_SESSION_KEY),null);
 assert.equal(readCredentialSession(storage),undefined);
});
