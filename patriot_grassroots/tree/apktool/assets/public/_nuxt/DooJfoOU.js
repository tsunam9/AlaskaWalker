
!function(){try{var e="undefined"!=typeof window?window:"undefined"!=typeof global?global:"undefined"!=typeof globalThis?globalThis:"undefined"!=typeof self?self:{},n=(new e.Error).stack;n&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[n]="a66740d9-9262-51f5-a4fd-50b8788af208")}catch(e){}}();
import{b_ as d,cx as t,hs as i,ht as l}from"./BYbP5qv3.js";try{let e=typeof window<"u"?window:typeof global<"u"?global:typeof globalThis<"u"?globalThis:typeof self<"u"?self:{},a=new e.Error().stack;a&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[a]="5202d29d-ced7-468b-8afb-6d32c98846e7",e._sentryDebugIdIdentifier="sentry-dbid-5202d29d-ced7-468b-8afb-6d32c98846e7")}catch{}/**
 * @license lucide-vue-next v0.536.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const r=d("clipboard-check",[["rect",{width:"8",height:"4",x:"8",y:"2",rx:"1",ry:"1",key:"tgr4d6"}],["path",{d:"M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2",key:"116196"}],["path",{d:"m9 14 2 2 4-4",key:"df797q"}]]);function o(e,a){return t({key:()=>["project-daily-review",e.value??"",a.value],query:()=>l({composable:"$fetch",path:{project_id:e.value},query:{date:a.value}}),enabled:()=>!!e.value&&!!a.value,staleTime:6e4})}function s(e){return t({key:()=>["project-daily-review-pending-dates",e.value??""],query:()=>i({composable:"$fetch",path:{project_id:e.value}}),enabled:()=>!!e.value,staleTime:6e4})}export{r as C,o as a,s as u};

//# debugId=a66740d9-9262-51f5-a4fd-50b8788af208
