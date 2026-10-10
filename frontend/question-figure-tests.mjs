import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

const vite = await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'});
test.after(async()=>{await vite.close();});
const {default:QuestionFigure} = await vite.ssrLoadModule('/src/components/QuestionFigure.tsx');
const {compileExpression,figureModel} = await vite.ssrLoadModule('/src/questionFigures.ts');
const render = figure => renderToStaticMarkup(React.createElement(QuestionFigure,{figure}));

test('graphs use Python power precedence without executing model-supplied JavaScript',()=>{
  assert.equal(compileExpression('-x**2')(3),-9);
  assert.equal(compileExpression('2**3**2')(0),512);
  assert.equal(compileExpression('sqrt(abs(x)) + cos(0)')(-9),4);
  for(const expression of ['x^2','alert(1)','globalThis.process.exit()','x;throw Error()','constructor(x)','__proto__(x)','sin(x','x+'.repeat(101)]) {
    assert.equal(compileExpression(expression),null,expression);
  }
});

test('all four supported diagram types draw visible accessible SVG',()=>{
  const figures=[
    {type:'geometry',data:{shape:'triangle',points:{A:[0,0],B:[4,0],C:[0,3]},labels:{A:'A',B:'B',C:'C'},side_lengths:{AB:4,AC:3,BC:5},marks:{right_angle_at:'A'}}},
    {type:'function_plot',data:{expression:'x**2 - 3*x + 2',variable:'x',domain:[-2,5],highlight_points:[{x:1,y:0,label:'A'}]}},
    {type:'bar_chart',data:{categories:['الف','ب'],values:[12,19],x_label:'دسته',y_label:'فراوانی'}},
    {type:'coordinate_plane',data:{points:[{x:1,y:2,label:'P'}],lines:[{from:[0,0],to:[4,4],label:'l'}],x_range:[-5,5],y_range:[-5,5]}},
  ];
  for (const figure of figures) {
    const html=render(figure);
    assert.match(html,/<svg[^>]+role="img"/);
    assert.match(html,/<title[^>]*>[^<]+<\/title>/);
    assert.match(html,/<path|<line|<rect/);
    assert.doesNotMatch(html,/NaN|Infinity|قابل نمایش نیست/);
  }
  assert.match(render(figures[0]),/>5<\/text>/);
  assert.match(render(figures[2]),/فراوانی/);
  assert.match(render(figures[3]),/>P<\/text>/);
  assert.doesNotMatch(render({type:'bar_chart',data:{categories:['A','B'],values:[0,0]}}),/NaN|Infinity/);
});

test('legacy text questions render no placeholder; corrupt diagrams are explained without crashing',()=>{
  assert.equal(render(undefined),'');
  assert.equal(render({type:'none',data:{}}),'');
  const invalid=[
    {type:'geometry',data:{points:{A:[0,0],B:[0,0]}}},
    {type:'function_plot',data:{expression:'x',domain:[1,1]}},
    {type:'bar_chart',data:{categories:['A'],values:[1,2]}},
    {type:'coordinate_plane',data:{points:[{x:Infinity,y:0}],x_range:[-5,5],y_range:[-5,5]}},
    {type:'geometry',data:{points:{A:[null,0],B:[1,1]}}},
  ];
  for (const figure of invalid) {
    assert.equal(figureModel(figure),null);
    assert.match(render(figure),/مشکل شکل را گزارش کن/);
    assert.doesNotMatch(render(figure),/<svg/);
  }
});

test('untrusted diagram labels are escaped and every graph has its own clip id',()=>{
  const figure={type:'bar_chart',data:{categories:['<script>bad()</script>'],values:[2]}};
  assert.doesNotMatch(render(figure),/<script>/);
  assert.match(render(figure),/&lt;script&gt;/);
  const plot={type:'function_plot',data:{expression:'1/x',domain:[-2,2]}};
  const html=renderToStaticMarkup(React.createElement('div',null,React.createElement(QuestionFigure,{figure:plot}),React.createElement(QuestionFigure,{figure:plot})));
  const ids=[...html.matchAll(/<clipPath id="([^"]+)"/g)].map(m=>m[1]);
  assert.equal(ids.length,2);
  assert.equal(new Set(ids).size,2);
  assert.doesNotMatch(html,/NaN|Infinity/);
});
