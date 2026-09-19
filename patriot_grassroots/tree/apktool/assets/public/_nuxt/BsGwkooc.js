
!function(){try{var e="undefined"!=typeof window?window:"undefined"!=typeof global?global:"undefined"!=typeof globalThis?globalThis:"undefined"!=typeof self?self:{},n=(new e.Error).stack;n&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[n]="071151e9-ff6f-5dd7-bc8b-c52434e410d4")}catch(e){}}();
import{b_ as s}from"./BYbP5qv3.js";try{let e=typeof window<"u"?window:typeof global<"u"?global:typeof globalThis<"u"?globalThis:typeof self<"u"?self:{},t=new e.Error().stack;t&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[t]="f300b6d1-5151-405f-a0a4-97c06bd7bd9b",e._sentryDebugIdIdentifier="sentry-dbid-f300b6d1-5151-405f-a0a4-97c06bd7bd9b")}catch{}/**
 * @license lucide-vue-next v0.536.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const o=s("circle-stop",[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["rect",{x:"9",y:"9",width:"6",height:"6",rx:"1",key:"1ssd4o"}]]);function c(e){e&&e.getTracks().forEach(t=>{t.stop()})}function d(e){let t="";const a=new Uint8Array(e),r=a.byteLength;for(let n=0;n<r;n++)t+=String.fromCharCode(a[n]);return window.btoa(t)}function l(e){var n;const t=e.getAudioTracks()[0],a=t.getSettings(),r=t.getCapabilities();return{sample_rate:a.sampleRate||48e3,channels:a.channelCount||1,bits_per_sample:((n=r.sampleSize)==null?void 0:n.max)||16,encoding:"linear16"}}export{o as C,d as a,l as c,c as s};

//# debugId=071151e9-ff6f-5dd7-bc8b-c52434e410d4
