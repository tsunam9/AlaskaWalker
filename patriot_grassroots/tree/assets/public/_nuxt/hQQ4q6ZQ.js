
!function(){try{var e="undefined"!=typeof window?window:"undefined"!=typeof global?global:"undefined"!=typeof globalThis?globalThis:"undefined"!=typeof self?self:{},n=(new e.Error).stack;n&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[n]="5d9eb509-fbed-5d9d-a30b-35eec5fb4d65")}catch(e){}}();
import{b_ as n,dH as h,cz as b,cu as v,cg as t,cx as p,jG as g,cM as _,cN as M,jH as k,cJ as m,cC as w,dn as q}from"./BYbP5qv3.js";try{let e=typeof window<"u"?window:typeof global<"u"?global:typeof globalThis<"u"?globalThis:typeof self<"u"?self:{},s=new e.Error().stack;s&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[s]="b1b7da31-0760-4cae-8af4-74f39a415112",e._sentryDebugIdIdentifier="sentry-dbid-b1b7da31-0760-4cae-8af4-74f39a415112")}catch{}/**
 * @license lucide-vue-next v0.536.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const j=n("camera",[["path",{d:"M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z",key:"1tc9qg"}],["circle",{cx:"12",cy:"13",r:"3",key:"1vg3eu"}]]);/**
 * @license lucide-vue-next v0.536.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=n("file-plus-2",[["path",{d:"M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4",key:"1pf5j1"}],["path",{d:"M14 2v4a2 2 0 0 0 2 2h4",key:"tnqrlb"}],["path",{d:"M3 15h6",key:"4e2qda"}],["path",{d:"M6 12v6",key:"1u72j0"}]]);/**
 * @license lucide-vue-next v0.536.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const B=n("file-plus",[["path",{d:"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z",key:"1rqfz7"}],["path",{d:"M14 2v4a2 2 0 0 0 2 2h4",key:"tnqrlb"}],["path",{d:"M9 15h6",key:"cctwl0"}],["path",{d:"M12 18v-6",key:"17g6i2"}]]),D=h(()=>{const e=b(),{isCanvasserOrSubCanvasser:s,isManager:a,userData:r}=v(),l=t(()=>e.query.project_id||""),u=t(()=>s.value&&r.value?r.value.id:e.query.canvasser_id||""),d=t(()=>a.value&&e.query.is_upload_on_canvassers_behalf==="true"),{data:c,error:i,isLoading:y,refetch:f}=p({key:()=>["ballots.list.draft",l.value,u.value],query:()=>g({composable:"$fetch",query:{project_id:l.value,canvasser_id:u.value}}),enabled:()=>!!l.value&&!!u.value,staleTime:0});return{projectId:l,canvasserId:u,isUploadOnCanvassersBehalf:d,ballots:t(()=>{var o;return((o=c.value)==null?void 0:o.ballots)||[]}),canSubmit:t(()=>{var o;return((o=c.value)==null?void 0:o.can_submit)||!1}),error:i,isLoading:y,refetch:f}}),H=_(()=>{const{mutateAsync:e,asyncStatus:s}=M({mutation:a=>k({composable:"$fetch",body:a}),onSuccess:async(a,r)=>{w().setQueryData(["ballots.list.draft",r.project_id,r.canvasser_id],()=>a),q("New petition added successfully")},onError(a){m(a)}});return{addNewBallot:e,isAddNewBallotLoading:t(()=>s.value==="loading")}});export{j as C,I as F,H as a,B as b,D as u};

//# debugId=5d9eb509-fbed-5d9d-a30b-35eec5fb4d65
