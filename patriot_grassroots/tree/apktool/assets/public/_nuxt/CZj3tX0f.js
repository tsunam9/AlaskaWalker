
!function(){try{var e="undefined"!=typeof window?window:"undefined"!=typeof global?global:"undefined"!=typeof globalThis?globalThis:"undefined"!=typeof self?self:{},n=(new e.Error).stack;n&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[n]="d02273e3-9d20-57d2-89e8-b84f322a6b4a")}catch(e){}}();
import{b_ as o,b$ as r,cg as d,c5 as l,c3 as f,dM as u,cj as p,cb as s,cA as b,c9 as m,cm as y}from"./BYbP5qv3.js";try{let e=typeof window<"u"?window:typeof global<"u"?global:typeof globalThis<"u"?globalThis:typeof self<"u"?self:{},t=new e.Error().stack;t&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[t]="fc9745e5-ebf0-48bc-b5fa-7371df5cc16a",e._sentryDebugIdIdentifier="sentry-dbid-fc9745e5-ebf0-48bc-b5fa-7371df5cc16a")}catch{}/**
 * @license lucide-vue-next v0.536.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const g=o("search-x",[["path",{d:"m13.5 8.5-5 5",key:"1cs55j"}],["path",{d:"m8.5 8.5 5 5",key:"a8mexj"}],["circle",{cx:"11",cy:"11",r:"8",key:"4ej97u"}],["path",{d:"m21 21-4.3-4.3",key:"1qie3q"}]]),j=r({__name:"AppEmpty",props:{title:{default:void 0},description:{default:void 0},variant:{default:"page"},iconClass:{default:"text-muted-foreground"},subject:{default:void 0},icon:{type:[Function,Object],default:void 0}},setup(e){const t=e,c={table:{card:!1,class:"min-h-48 py-4"},page:{card:!0,class:"min-h-80"}},n=d(()=>t.description?t.description:t.subject?`No ${t.subject} found`:"No items found");return(a,h)=>{const i=u;return f(),l(i,{variant:"default",title:a.title,description:s(n),icon:a.icon||s(g),"icon-class":a.iconClass,card:c[a.variant].card,class:p(s(b)("mx-auto p-0 px-0 sm:px-8 flex items-center justify-center",c[a.variant].class))},{default:m(()=>[y(a.$slots,"default")]),_:3},8,["title","description","icon","icon-class","card","class"])}}});export{j as _};

//# debugId=d02273e3-9d20-57d2-89e8-b84f322a6b4a
