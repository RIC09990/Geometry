import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {BoardMeasurements} from '../components/geometry/board-measurements';

test('Small angles retain their eight-place measurement instead of acos cancellation',()=>{
 const radians=Math.PI/180000000;
 const html=renderToStaticMarkup(React.createElement(BoardMeasurements,{points:[{id:'A',x:1,y:0},{id:'B',x:0,y:0},{id:'C',x:Math.cos(radians),y:Math.sin(radians)}],goal:{id:'goal',kind:'angle_value',args:['A','B','C'],enabled:true,toggleable:true}}));
 assert.match(html,/>0\.00000100°</);
});
test('A multi-term weighted measurement shows eight decimals for each length and the complete sum',()=>{
 const html=renderToStaticMarkup(React.createElement(BoardMeasurements,{points:[{id:'P',x:0,y:0},{id:'A',x:3,y:4},{id:'B',x:0,y:2}],goal:{id:'goal',kind:'minimize',args:['P','A','P','B'],weights:[1.25,2.5],enabled:true,toggleable:true}}));
 for(const value of ['5.00000000','2.00000000','11.25000000'])assert.ok(html.includes(value));
});
