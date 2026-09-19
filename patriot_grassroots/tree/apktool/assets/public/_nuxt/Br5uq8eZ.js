
!function(){try{var e="undefined"!=typeof window?window:"undefined"!=typeof global?global:"undefined"!=typeof globalThis?globalThis:"undefined"!=typeof self?self:{},n=(new e.Error).stack;n&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[n]="e27e8124-3b61-5000-9a23-c964fe7fabd0")}catch(e){}}();
import{J as Ue,k as Le,b6 as kt,G as St,l as ye,aA as Ye,j as Et,i as Lt}from"./BYbP5qv3.js";import{i as Tt}from"./Dg8mknNh.js";try{let e=typeof window<"u"?window:typeof global<"u"?global:typeof globalThis<"u"?globalThis:typeof self<"u"?self:{},t=new e.Error().stack;t&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[t]="d1e47ce2-e8fa-4751-a100-2d949ead1033",e._sentryDebugIdIdentifier="sentry-dbid-d1e47ce2-e8fa-4751-a100-2d949ead1033")}catch{}function Ft(e,t={},r=Ue()){const{message:n,name:o,email:a,url:l,source:s,associatedEventId:u,tags:c}=e,d={contexts:{feedback:{contact_email:a,name:o,message:n,url:l,source:s,associated_event_id:u}},type:"feedback",level:"info",tags:c},i=(r==null?void 0:r.getClient())||Le();return i&&i.emit("beforeSendFeedback",d,t),r.captureEvent(d,t)}const Z=St,C=Z.document,ue=Z.navigator,dt="Report a Bug",Dt="Cancel",$t="Send Bug Report",At="Confirm",Ht="Report a Bug",Rt="your.email@example.org",Mt="Email",It="What's the bug? What did you expect?",Pt="Description",Bt="Your Name",Nt="Name",Ut="Thank you for your report!",qt="(required)",zt="Add a screenshot",Vt="Remove screenshot",Wt="widget",Gt="api",jt=5e3,Zt=(e,t={includeReplay:!0})=>{if(!e.message)throw new Error("Unable to submit feedback with empty message");const r=Le();if(!r)throw new Error("No client setup, cannot send feedback.");e.tags&&Object.keys(e.tags).length&&Ue().setTags(e.tags);const n=Ft({source:Gt,url:kt(),...e},t);return new Promise((o,a)=>{const l=setTimeout(()=>a("Unable to determine if Feedback was correctly sent."),3e4),s=r.on("afterSendEvent",(u,c)=>{if(u.event_id===n)return clearTimeout(l),s(),c&&typeof c.statusCode=="number"&&c.statusCode>=200&&c.statusCode<300?o(n):c&&typeof c.statusCode=="number"&&c.statusCode===0?a("Unable to send Feedback. This is because of network issues, or because you are using an ad-blocker."):c&&typeof c.statusCode=="number"&&c.statusCode===403?a("Unable to send Feedback. This could be because this domain is not in your list of allowed domains."):a("Unable to send Feedback. This could be because of network issues, or because you are using an ad-blocker")})})},we=typeof __SENTRY_DEBUG__>"u"||__SENTRY_DEBUG__;function Xt(){return!(/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ue.userAgent)||/Macintosh/i.test(ue.userAgent)&&ue.maxTouchPoints&&ue.maxTouchPoints>1||!isSecureContext)}function be(e,t){return{...e,...t,tags:{...e.tags,...t.tags},onFormOpen:()=>{var r,n;(r=t.onFormOpen)==null||r.call(t),(n=e.onFormOpen)==null||n.call(e)},onFormClose:()=>{var r,n;(r=t.onFormClose)==null||r.call(t),(n=e.onFormClose)==null||n.call(e)},onSubmitSuccess:(r,n)=>{var o,a;(o=t.onSubmitSuccess)==null||o.call(t,r,n),(a=e.onSubmitSuccess)==null||a.call(e,r,n)},onSubmitError:r=>{var n,o;(n=t.onSubmitError)==null||n.call(t,r),(o=e.onSubmitError)==null||o.call(e,r)},onFormSubmitted:()=>{var r,n;(r=t.onFormSubmitted)==null||r.call(t),(n=e.onFormSubmitted)==null||n.call(e)},themeDark:{...e.themeDark,...t.themeDark},themeLight:{...e.themeLight,...t.themeLight}}}function Yt(e){const t=C.createElement("style");return t.textContent=`
.widget__actor {
  position: fixed;
  z-index: var(--z-index);
  margin: var(--page-margin);
  inset: var(--actor-inset);

  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;

  font-family: inherit;
  font-size: var(--font-size);
  font-weight: 600;
  line-height: 1.14em;
  text-decoration: none;

  background: var(--actor-background, var(--background));
  border-radius: var(--actor-border-radius, 1.7em/50%);
  border: var(--actor-border, var(--border));
  box-shadow: var(--actor-box-shadow, var(--box-shadow));
  color: var(--actor-color, var(--foreground));
  fill: var(--actor-color, var(--foreground));
  cursor: pointer;
  opacity: 1;
  transition: transform 0.2s ease-in-out;
  transform: translate(0, 0) scale(1);
}
.widget__actor[aria-hidden="true"] {
  opacity: 0;
  pointer-events: none;
  visibility: hidden;
  transform: translate(0, 16px) scale(0.98);
}

.widget__actor:hover {
  background: var(--actor-hover-background, var(--background));
  filter: var(--interactive-filter);
}

.widget__actor svg {
  width: 1.14em;
  height: 1.14em;
}

@media (max-width: 600px) {
  .widget__actor span {
    display: none;
  }
}
`,e&&t.setAttribute("nonce",e),t}function U(e,t){return Object.entries(t).forEach(([r,n])=>{e.setAttributeNS(null,r,n)}),e}const ie=20,Kt="http://www.w3.org/2000/svg";function Jt(){const e=s=>Z.document.createElementNS(Kt,s),t=U(e("svg"),{width:`${ie}`,height:`${ie}`,viewBox:`0 0 ${ie} ${ie}`,fill:"var(--actor-color, var(--foreground))"}),r=U(e("g"),{clipPath:"url(#clip0_57_80)"}),n=U(e("path"),{"fill-rule":"evenodd","clip-rule":"evenodd",d:"M15.6622 15H12.3997C12.2129 14.9959 12.031 14.9396 11.8747 14.8375L8.04965 12.2H7.49956V19.1C7.4875 19.3348 7.3888 19.5568 7.22256 19.723C7.05632 19.8892 6.83435 19.9879 6.59956 20H2.04956C1.80193 19.9968 1.56535 19.8969 1.39023 19.7218C1.21511 19.5467 1.1153 19.3101 1.11206 19.0625V12.2H0.949652C0.824431 12.2017 0.700142 12.1783 0.584123 12.1311C0.468104 12.084 0.362708 12.014 0.274155 11.9255C0.185602 11.8369 0.115689 11.7315 0.0685419 11.6155C0.0213952 11.4995 -0.00202913 11.3752 -0.00034808 11.25V3.75C-0.00900498 3.62067 0.0092504 3.49095 0.0532651 3.36904C0.0972798 3.24712 0.166097 3.13566 0.255372 3.04168C0.344646 2.94771 0.452437 2.87327 0.571937 2.82307C0.691437 2.77286 0.82005 2.74798 0.949652 2.75H8.04965L11.8747 0.1625C12.031 0.0603649 12.2129 0.00407221 12.3997 0H15.6622C15.9098 0.00323746 16.1464 0.103049 16.3215 0.278167C16.4966 0.453286 16.5964 0.689866 16.5997 0.9375V3.25269C17.3969 3.42959 18.1345 3.83026 18.7211 4.41679C19.5322 5.22788 19.9878 6.32796 19.9878 7.47502C19.9878 8.62209 19.5322 9.72217 18.7211 10.5333C18.1345 11.1198 17.3969 11.5205 16.5997 11.6974V14.0125C16.6047 14.1393 16.5842 14.2659 16.5395 14.3847C16.4948 14.5035 16.4268 14.6121 16.3394 14.7042C16.252 14.7962 16.147 14.8698 16.0307 14.9206C15.9144 14.9714 15.7891 14.9984 15.6622 15ZM1.89695 10.325H1.88715V4.625H8.33715C8.52423 4.62301 8.70666 4.56654 8.86215 4.4625L12.6872 1.875H14.7247V13.125H12.6872L8.86215 10.4875C8.70666 10.3835 8.52423 10.327 8.33715 10.325H2.20217C2.15205 10.3167 2.10102 10.3125 2.04956 10.3125C1.9981 10.3125 1.94708 10.3167 1.89695 10.325ZM2.98706 12.2V18.1625H5.66206V12.2H2.98706ZM16.5997 9.93612V5.01393C16.6536 5.02355 16.7072 5.03495 16.7605 5.04814C17.1202 5.13709 17.4556 5.30487 17.7425 5.53934C18.0293 5.77381 18.2605 6.06912 18.4192 6.40389C18.578 6.73866 18.6603 7.10452 18.6603 7.47502C18.6603 7.84552 18.578 8.21139 18.4192 8.54616C18.2605 8.88093 18.0293 9.17624 17.7425 9.41071C17.4556 9.64518 17.1202 9.81296 16.7605 9.90191C16.7072 9.91509 16.6536 9.9265 16.5997 9.93612Z"});t.appendChild(r).appendChild(n);const o=e("defs"),a=U(e("clipPath"),{id:"clip0_57_80"}),l=U(e("rect"),{width:`${ie}`,height:`${ie}`,fill:"white"});return a.appendChild(l),o.appendChild(a),t.appendChild(o).appendChild(a).appendChild(l),t}function Qt({triggerLabel:e,triggerAriaLabel:t,shadow:r,styleNonce:n}){const o=C.createElement("button");if(o.type="button",o.className="widget__actor",o.ariaHidden="false",o.ariaLabel=t||e||dt,o.appendChild(Jt()),e){const l=C.createElement("span");l.appendChild(C.createTextNode(e)),o.appendChild(l)}const a=Yt(n);return{el:o,appendToDom(){r.appendChild(a),r.appendChild(o)},removeFromDom(){o.remove(),a.remove()},show(){o.ariaHidden="false"},hide(){o.ariaHidden="true"}}}const ft="rgba(88, 74, 192, 1)",Ot={foreground:"#2b2233",background:"#ffffff",accentForeground:"white",accentBackground:ft,successColor:"#268d75",errorColor:"#df3338",border:"1.5px solid rgba(41, 35, 47, 0.13)",boxShadow:"0px 4px 24px 0px rgba(43, 34, 51, 0.12)",outline:"1px auto var(--accent-background)",interactiveFilter:"brightness(95%)"},Ke={foreground:"#ebe6ef",background:"#29232f",accentForeground:"white",accentBackground:ft,successColor:"#2da98c",errorColor:"#f55459",border:"1.5px solid rgba(235, 230, 239, 0.15)",boxShadow:"0px 4px 24px 0px rgba(43, 34, 51, 0.12)",outline:"1px auto var(--accent-background)",interactiveFilter:"brightness(150%)"};function Je(e){return`
  --foreground: ${e.foreground};
  --background: ${e.background};
  --accent-foreground: ${e.accentForeground};
  --accent-background: ${e.accentBackground};
  --success-color: ${e.successColor};
  --error-color: ${e.errorColor};
  --border: ${e.border};
  --box-shadow: ${e.boxShadow};
  --outline: ${e.outline};
  --interactive-filter: ${e.interactiveFilter};
  `}function er({colorScheme:e,themeDark:t,themeLight:r,styleNonce:n}){const o=C.createElement("style");return o.textContent=`
:host {
  --font-family: system-ui, 'Helvetica Neue', Arial, sans-serif;
  --font-size: 14px;
  --z-index: 100000;

  --page-margin: 16px;
  --inset: auto 0 0 auto;
  --actor-inset: var(--inset);

  font-family: var(--font-family);
  font-size: var(--font-size);

  ${e!=="system"?"color-scheme: only light;":""}

  ${Je(e==="dark"?{...Ke,...t}:{...Ot,...r})}
}

${e==="system"?`
@media (prefers-color-scheme: dark) {
  :host {
    ${Je({...Ke,...t})}
  }
}`:""}
}
`,n&&o.setAttribute("nonce",n),o}const qr=({lazyLoadIntegration:e,getModalIntegration:t,getScreenshotIntegration:r})=>(({id:o="sentry-feedback",autoInject:a=!0,showBranding:l=!0,isEmailRequired:s=!1,isNameRequired:u=!1,showEmail:c=!0,showName:d=!0,enableScreenshot:i=!0,useSentryUser:h={email:"email",name:"username"},tags:_,styleNonce:f,scriptNonce:v,colorScheme:m="system",themeLight:g={},themeDark:y={},addScreenshotButtonLabel:A=zt,cancelButtonLabel:E=Dt,confirmButtonLabel:G=At,emailLabel:q=Mt,emailPlaceholder:R=Rt,formTitle:z=Ht,isRequiredLabel:T=qt,messageLabel:I=Pt,messagePlaceholder:K=It,nameLabel:b=Nt,namePlaceholder:w=Bt,removeScreenshotButtonLabel:H=Vt,submitButtonLabel:M=$t,successMessageText:ee=Ut,triggerLabel:ae=dt,triggerAriaLabel:P="",onFormOpen:B,onFormClose:D,onSubmitSuccess:V,onSubmitError:ge,onFormSubmitted:J}={})=>{const j={id:o,autoInject:a,showBranding:l,isEmailRequired:s,isNameRequired:u,showEmail:c,showName:d,enableScreenshot:i,useSentryUser:h,tags:_,styleNonce:f,scriptNonce:v,colorScheme:m,themeDark:y,themeLight:g,triggerLabel:ae,triggerAriaLabel:P,cancelButtonLabel:E,submitButtonLabel:M,confirmButtonLabel:G,formTitle:z,emailLabel:q,emailPlaceholder:R,messageLabel:I,messagePlaceholder:K,nameLabel:b,namePlaceholder:w,successMessageText:ee,isRequiredLabel:T,addScreenshotButtonLabel:A,removeScreenshotButtonLabel:H,onFormClose:D,onFormOpen:B,onSubmitError:ge,onSubmitSuccess:V,onFormSubmitted:J};let te=null,_e=[];const je=S=>{if(!te){const $=C.createElement("div");$.id=String(S.id),C.body.appendChild($),te=$.attachShadow({mode:"open"}),te.appendChild(er(S))}return te},Ze=async S=>{const $=S.enableScreenshot&&Xt();let X,N;try{X=(t?t():await e("feedbackModalIntegration",v))(),Ye(X)}catch{throw we&&ye.error("[Feedback] Error when trying to load feedback integrations. Try using `feedbackSyncIntegration` in your `Sentry.init`."),new Error("[Feedback] Missing feedback modal integration!")}try{const W=$?r?r():await e("feedbackScreenshotIntegration",v):void 0;W&&(N=W(),Ye(N))}catch{we&&ye.error("[Feedback] Missing feedback screenshot integration. Proceeding without screenshots.")}const F=X.createDialog({options:{...S,onFormClose:()=>{var W;F==null||F.close(),(W=S.onFormClose)==null||W.call(S)},onFormSubmitted:()=>{var W;F==null||F.close(),(W=S.onFormSubmitted)==null||W.call(S)}},screenshotIntegration:N,sendFeedback:Zt,shadow:je(S)});return F},Xe=(S,$={})=>{const X=be(j,$),N=typeof S=="string"?C.querySelector(S):typeof S.addEventListener=="function"?S:null;if(!N)throw we&&ye.error("[Feedback] Unable to attach to target element"),new Error("Unable to attach to target element");let F=null;const W=async()=>{F||(F=await Ze({...X,onFormSubmitted:()=>{var pe;F==null||F.removeFromDom(),(pe=X.onFormSubmitted)==null||pe.call(X)}})),F.appendToDom(),F.open()};N.addEventListener("click",W);const De=()=>{_e=_e.filter(pe=>pe!==De),F==null||F.removeFromDom(),F=null,N.removeEventListener("click",W)};return _e.push(De),De},Fe=(S={})=>{const $=be(j,S),X=je($),N=Qt({triggerLabel:$.triggerLabel,triggerAriaLabel:$.triggerAriaLabel,shadow:X,styleNonce:f});return Xe(N.el,{...$,onFormOpen(){N.hide()},onFormClose(){N.show()},onFormSubmitted(){N.show()}}),N};return{name:"Feedback",setupOnce(){!Tt()||!j.autoInject||(C.readyState==="loading"?C.addEventListener("DOMContentLoaded",()=>Fe().appendToDom()):Fe().appendToDom())},attachTo:Xe,createWidget(S={}){const $=Fe(be(j,S));return $.appendToDom(),$},async createForm(S={}){return Ze(be(j,S))},remove(){var S;te&&((S=te.parentElement)==null||S.remove(),te=null),_e.forEach($=>$()),_e=[]}}});function zr(){const e=Le();return e==null?void 0:e.getIntegrationByName("Feedback")}var Te,k,ht,re,Qe,gt,Ie,de={},qe=[],tr=/acit|ex(?:s|g|n|p|$)|rph|grid|ows|mnc|ntw|ine[ch]|zoo|^ord|itera/i,ze=Array.isArray;function O(e,t){for(var r in t)e[r]=t[r];return e}function pt(e){var t=e.parentNode;t&&t.removeChild(e)}function p(e,t,r){var n,o,a,l={};for(a in t)a=="key"?n=t[a]:a=="ref"?o=t[a]:l[a]=t[a];if(arguments.length>2&&(l.children=arguments.length>3?Te.call(arguments,2):r),typeof e=="function"&&e.defaultProps!=null)for(a in e.defaultProps)l[a]===void 0&&(l[a]=e.defaultProps[a]);return Ce(e,l,n,o,null)}function Ce(e,t,r,n,o){var a={type:e,props:t,key:r,ref:n,__k:null,__:null,__b:0,__e:null,__d:void 0,__c:null,constructor:void 0,__v:o??++ht,__i:-1,__u:0};return o==null&&k.vnode!=null&&k.vnode(a),a}function fe(e){return e.children}function xe(e,t){this.props=e,this.context=t}function le(e,t){if(t==null)return e.__?le(e.__,e.__i+1):null;for(var r;t<e.__k.length;t++)if((r=e.__k[t])!=null&&r.__e!=null)return r.__e;return typeof e.type=="function"?le(e):null}function rr(e,t,r){var n,o=e.__v,a=o.__e,l=e.__P;if(l)return(n=O({},o)).__v=o.__v+1,k.vnode&&k.vnode(n),Ve(l,n,o,e.__n,l.ownerSVGElement!==void 0,32&o.__u?[a]:null,t,a??le(o),!!(32&o.__u),r),n.__.__k[n.__i]=n,n.__d=void 0,n.__e!=a&&bt(n),n}function bt(e){var t,r;if((e=e.__)!=null&&e.__c!=null){for(e.__e=e.__c.base=null,t=0;t<e.__k.length;t++)if((r=e.__k[t])!=null&&r.__e!=null){e.__e=e.__c.base=r.__e;break}return bt(e)}}function Oe(e){(!e.__d&&(e.__d=!0)&&re.push(e)&&!Ee.__r++||Qe!==k.debounceRendering)&&((Qe=k.debounceRendering)||gt)(Ee)}function Ee(){var e,t,r,n=[],o=[];for(re.sort(Ie);e=re.shift();)e.__d&&(r=re.length,t=rr(e,n,o)||t,r===0||re.length>r?(Pe(n,t,o),o.length=n.length=0,t=void 0,re.sort(Ie)):t&&k.__c&&k.__c(t,qe));t&&Pe(n,t,o),Ee.__r=0}function mt(e,t,r,n,o,a,l,s,u,c,d){var i,h,_,f,v,m=n&&n.__k||qe,g=t.length;for(r.__d=u,nr(r,t,m),u=r.__d,i=0;i<g;i++)(_=r.__k[i])!=null&&typeof _!="boolean"&&typeof _!="function"&&(h=_.__i===-1?de:m[_.__i]||de,_.__i=i,Ve(e,_,h,o,a,l,s,u,c,d),f=_.__e,_.ref&&h.ref!=_.ref&&(h.ref&&We(h.ref,null,_),d.push(_.ref,_.__c||f,_)),v==null&&f!=null&&(v=f),65536&_.__u||h.__k===_.__k?u=vt(_,u,e):typeof _.type=="function"&&_.__d!==void 0?u=_.__d:f&&(u=f.nextSibling),_.__d=void 0,_.__u&=-196609);r.__d=u,r.__e=v}function nr(e,t,r){var n,o,a,l,s,u=t.length,c=r.length,d=c,i=0;for(e.__k=[],n=0;n<u;n++)(o=e.__k[n]=(o=t[n])==null||typeof o=="boolean"||typeof o=="function"?null:typeof o=="string"||typeof o=="number"||typeof o=="bigint"||o.constructor==String?Ce(null,o,null,null,o):ze(o)?Ce(fe,{children:o},null,null,null):o.constructor===void 0&&o.__b>0?Ce(o.type,o.props,o.key,o.ref?o.ref:null,o.__v):o)!=null?(o.__=e,o.__b=e.__b+1,s=or(o,r,l=n+i,d),o.__i=s,a=null,s!==-1&&(d--,(a=r[s])&&(a.__u|=131072)),a==null||a.__v===null?(s==-1&&i--,typeof o.type!="function"&&(o.__u|=65536)):s!==l&&(s===l+1?i++:s>l?d>u-l?i+=s-l:i--:i=s<l&&s==l-1?s-l:0,s!==n+i&&(o.__u|=65536))):(a=r[n])&&a.key==null&&a.__e&&(a.__e==e.__d&&(e.__d=le(a)),Be(a,a,!1),r[n]=null,d--);if(d)for(n=0;n<c;n++)(a=r[n])!=null&&(131072&a.__u)==0&&(a.__e==e.__d&&(e.__d=le(a)),Be(a,a))}function vt(e,t,r){var n,o;if(typeof e.type=="function"){for(n=e.__k,o=0;n&&o<n.length;o++)n[o]&&(n[o].__=e,t=vt(n[o],t,r));return t}e.__e!=t&&(r.insertBefore(e.__e,t||null),t=e.__e);do t=t&&t.nextSibling;while(t!=null&&t.nodeType===8);return t}function or(e,t,r,n){var o=e.key,a=e.type,l=r-1,s=r+1,u=t[r];if(u===null||u&&o==u.key&&a===u.type)return r;if(n>(u!=null&&(131072&u.__u)==0?1:0))for(;l>=0||s<t.length;){if(l>=0){if((u=t[l])&&(131072&u.__u)==0&&o==u.key&&a===u.type)return l;l--}if(s<t.length){if((u=t[s])&&(131072&u.__u)==0&&o==u.key&&a===u.type)return s;s++}}return-1}function et(e,t,r){t[0]==="-"?e.setProperty(t,r??""):e[t]=r==null?"":typeof r!="number"||tr.test(t)?r:r+"px"}function me(e,t,r,n,o){var a;e:if(t==="style")if(typeof r=="string")e.style.cssText=r;else{if(typeof n=="string"&&(e.style.cssText=n=""),n)for(t in n)r&&t in r||et(e.style,t,"");if(r)for(t in r)n&&r[t]===n[t]||et(e.style,t,r[t])}else if(t[0]==="o"&&t[1]==="n")a=t!==(t=t.replace(/(PointerCapture)$|Capture$/i,"$1")),t=t.toLowerCase()in e?t.toLowerCase().slice(2):t.slice(2),e.l||(e.l={}),e.l[t+a]=r,r?n?r.u=n.u:(r.u=Date.now(),e.addEventListener(t,a?rt:tt,a)):e.removeEventListener(t,a?rt:tt,a);else{if(o)t=t.replace(/xlink(H|:h)/,"h").replace(/sName$/,"s");else if(t!=="width"&&t!=="height"&&t!=="href"&&t!=="list"&&t!=="form"&&t!=="tabIndex"&&t!=="download"&&t!=="rowSpan"&&t!=="colSpan"&&t!=="role"&&t in e)try{e[t]=r??"";break e}catch{}typeof r=="function"||(r==null||r===!1&&t[4]!=="-"?e.removeAttribute(t):e.setAttribute(t,r))}}function tt(e){if(this.l){var t=this.l[e.type+!1];if(e.t){if(e.t<=t.u)return}else e.t=Date.now();return t(k.event?k.event(e):e)}}function rt(e){if(this.l)return this.l[e.type+!0](k.event?k.event(e):e)}function Ve(e,t,r,n,o,a,l,s,u,c){var d,i,h,_,f,v,m,g,y,A,E,G,q,R,z,T=t.type;if(t.constructor!==void 0)return null;128&r.__u&&(u=!!(32&r.__u),a=[s=t.__e=r.__e]),(d=k.__b)&&d(t);e:if(typeof T=="function")try{if(g=t.props,y=(d=T.contextType)&&n[d.__c],A=d?y?y.props.value:d.__:n,r.__c?m=(i=t.__c=r.__c).__=i.__E:("prototype"in T&&T.prototype.render?t.__c=i=new T(g,A):(t.__c=i=new xe(g,A),i.constructor=T,i.render=ir),y&&y.sub(i),i.props=g,i.state||(i.state={}),i.context=A,i.__n=n,h=i.__d=!0,i.__h=[],i._sb=[]),i.__s==null&&(i.__s=i.state),T.getDerivedStateFromProps!=null&&(i.__s==i.state&&(i.__s=O({},i.__s)),O(i.__s,T.getDerivedStateFromProps(g,i.__s))),_=i.props,f=i.state,i.__v=t,h)T.getDerivedStateFromProps==null&&i.componentWillMount!=null&&i.componentWillMount(),i.componentDidMount!=null&&i.__h.push(i.componentDidMount);else{if(T.getDerivedStateFromProps==null&&g!==_&&i.componentWillReceiveProps!=null&&i.componentWillReceiveProps(g,A),!i.__e&&(i.shouldComponentUpdate!=null&&i.shouldComponentUpdate(g,i.__s,A)===!1||t.__v===r.__v)){for(t.__v!==r.__v&&(i.props=g,i.state=i.__s,i.__d=!1),t.__e=r.__e,t.__k=r.__k,t.__k.forEach(function(I){I&&(I.__=t)}),E=0;E<i._sb.length;E++)i.__h.push(i._sb[E]);i._sb=[],i.__h.length&&l.push(i);break e}i.componentWillUpdate!=null&&i.componentWillUpdate(g,i.__s,A),i.componentDidUpdate!=null&&i.__h.push(function(){i.componentDidUpdate(_,f,v)})}if(i.context=A,i.props=g,i.__P=e,i.__e=!1,G=k.__r,q=0,"prototype"in T&&T.prototype.render){for(i.state=i.__s,i.__d=!1,G&&G(t),d=i.render(i.props,i.state,i.context),R=0;R<i._sb.length;R++)i.__h.push(i._sb[R]);i._sb=[]}else do i.__d=!1,G&&G(t),d=i.render(i.props,i.state,i.context),i.state=i.__s;while(i.__d&&++q<25);i.state=i.__s,i.getChildContext!=null&&(n=O(O({},n),i.getChildContext())),h||i.getSnapshotBeforeUpdate==null||(v=i.getSnapshotBeforeUpdate(_,f)),mt(e,ze(z=d!=null&&d.type===fe&&d.key==null?d.props.children:d)?z:[z],t,r,n,o,a,l,s,u,c),i.base=t.__e,t.__u&=-161,i.__h.length&&l.push(i),m&&(i.__E=i.__=null)}catch(I){t.__v=null,u||a!=null?(t.__e=s,t.__u|=u?160:32,a[a.indexOf(s)]=null):(t.__e=r.__e,t.__k=r.__k),k.__e(I,t,r)}else a==null&&t.__v===r.__v?(t.__k=r.__k,t.__e=r.__e):t.__e=ar(r.__e,t,r,n,o,a,l,u,c);(d=k.diffed)&&d(t)}function Pe(e,t,r){for(var n=0;n<r.length;n++)We(r[n],r[++n],r[++n]);k.__c&&k.__c(t,e),e.some(function(o){try{e=o.__h,o.__h=[],e.some(function(a){a.call(o)})}catch(a){k.__e(a,o.__v)}})}function ar(e,t,r,n,o,a,l,s,u){var c,d,i,h,_,f,v,m=r.props,g=t.props,y=t.type;if(y==="svg"&&(o=!0),a!=null){for(c=0;c<a.length;c++)if((_=a[c])&&"setAttribute"in _==!!y&&(y?_.localName===y:_.nodeType===3)){e=_,a[c]=null;break}}if(e==null){if(y===null)return document.createTextNode(g);e=o?document.createElementNS("http://www.w3.org/2000/svg",y):document.createElement(y,g.is&&g),a=null,s=!1}if(y===null)m===g||s&&e.data===g||(e.data=g);else{if(a=a&&Te.call(e.childNodes),m=r.props||de,!s&&a!=null)for(m={},c=0;c<e.attributes.length;c++)m[(_=e.attributes[c]).name]=_.value;for(c in m)_=m[c],c=="children"||(c=="dangerouslySetInnerHTML"?i=_:c==="key"||c in g||me(e,c,null,_,o));for(c in g)_=g[c],c=="children"?h=_:c=="dangerouslySetInnerHTML"?d=_:c=="value"?f=_:c=="checked"?v=_:c==="key"||s&&typeof _!="function"||m[c]===_||me(e,c,_,m[c],o);if(d)s||i&&(d.__html===i.__html||d.__html===e.innerHTML)||(e.innerHTML=d.__html),t.__k=[];else if(i&&(e.innerHTML=""),mt(e,ze(h)?h:[h],t,r,n,o&&y!=="foreignObject",a,l,a?a[0]:r.__k&&le(r,0),s,u),a!=null)for(c=a.length;c--;)a[c]!=null&&pt(a[c]);s||(c="value",f!==void 0&&(f!==e[c]||y==="progress"&&!f||y==="option"&&f!==m[c])&&me(e,c,f,m[c],!1),c="checked",v!==void 0&&v!==e[c]&&me(e,c,v,m[c],!1))}return e}function We(e,t,r){try{typeof e=="function"?e(t):e.current=t}catch(n){k.__e(n,r)}}function Be(e,t,r){var n,o;if(k.unmount&&k.unmount(e),(n=e.ref)&&(n.current&&n.current!==e.__e||We(n,null,t)),(n=e.__c)!=null){if(n.componentWillUnmount)try{n.componentWillUnmount()}catch(a){k.__e(a,t)}n.base=n.__P=null,e.__c=void 0}if(n=e.__k)for(o=0;o<n.length;o++)n[o]&&Be(n[o],t,r||typeof e.type!="function");r||e.__e==null||pt(e.__e),e.__=e.__e=e.__d=void 0}function ir(e,t,r){return this.constructor(e,r)}function cr(e,t,r){var n,o,a,l;k.__&&k.__(e,t),o=(n=!1)?null:t.__k,a=[],l=[],Ve(t,e=t.__k=p(fe,null,[e]),o||de,de,t.ownerSVGElement!==void 0,o?null:t.firstChild?Te.call(t.childNodes):null,a,o?o.__e:t.firstChild,n,l),e.__d=void 0,Pe(a,e,l)}Te=qe.slice,k={__e:function(e,t,r,n){for(var o,a,l;t=t.__;)if((o=t.__c)&&!o.__)try{if((a=o.constructor)&&a.getDerivedStateFromError!=null&&(o.setState(a.getDerivedStateFromError(e)),l=o.__d),o.componentDidCatch!=null&&(o.componentDidCatch(e,n||{}),l=o.__d),l)return o.__E=o}catch(s){e=s}throw e}},ht=0,xe.prototype.setState=function(e,t){var r;r=this.__s!=null&&this.__s!==this.state?this.__s:this.__s=O({},this.state),typeof e=="function"&&(e=e(O({},r),this.props)),e&&O(r,e),e!=null&&this.__v&&(t&&this._sb.push(t),Oe(this))},xe.prototype.forceUpdate=function(e){this.__v&&(this.__e=!0,e&&this.__h.push(e),Oe(this))},xe.prototype.render=fe,re=[],gt=typeof Promise=="function"?Promise.prototype.then.bind(Promise.resolve()):setTimeout,Ie=function(e,t){return e.__v.__b-t.__v.__b},Ee.__r=0;var Y,x,$e,nt,se=0,yt=[],ke=[],L=k,ot=L.__b,at=L.__r,it=L.diffed,ct=L.__c,lt=L.unmount,st=L.__;function oe(e,t){L.__h&&L.__h(x,e,se||t),se=0;var r=x.__H||(x.__H={__:[],__h:[]});return e>=r.__.length&&r.__.push({__V:ke}),r.__[e]}function ne(e){return se=1,wt(xt,e)}function wt(e,t,r){var n=oe(Y++,2);if(n.t=e,!n.__c&&(n.__=[r?r(t):xt(void 0,t),function(s){var u=n.__N?n.__N[0]:n.__[0],c=n.t(u,s);u!==c&&(n.__N=[c,n.__[1]],n.__c.setState({}))}],n.__c=x,!x.u)){var o=function(s,u,c){if(!n.__c.__H)return!0;var d=n.__c.__H.__.filter(function(h){return!!h.__c});if(d.every(function(h){return!h.__N}))return!a||a.call(this,s,u,c);var i=!1;return d.forEach(function(h){if(h.__N){var _=h.__[0];h.__=h.__N,h.__N=void 0,_!==h.__[0]&&(i=!0)}}),!(!i&&n.__c.props===s)&&(!a||a.call(this,s,u,c))};x.u=!0;var a=x.shouldComponentUpdate,l=x.componentWillUpdate;x.componentWillUpdate=function(s,u,c){if(this.__e){var d=a;a=void 0,o(s,u,c),a=d}l&&l.call(this,s,u,c)},x.shouldComponentUpdate=o}return n.__N||n.__}function lr(e,t){var r=oe(Y++,3);!L.__s&&Ge(r.__H,t)&&(r.__=e,r.i=t,x.__H.__h.push(r))}function Ct(e,t){var r=oe(Y++,4);!L.__s&&Ge(r.__H,t)&&(r.__=e,r.i=t,x.__h.push(r))}function sr(e){return se=5,he(function(){return{current:e}},[])}function _r(e,t,r){se=6,Ct(function(){return typeof e=="function"?(e(t()),function(){return e(null)}):e?(e.current=t(),function(){return e.current=null}):void 0},r==null?r:r.concat(e))}function he(e,t){var r=oe(Y++,7);return Ge(r.__H,t)?(r.__V=e(),r.i=t,r.__h=e,r.__V):r.__}function ce(e,t){return se=8,he(function(){return e},t)}function ur(e){var t=x.context[e.__c],r=oe(Y++,9);return r.c=e,t?(r.__==null&&(r.__=!0,t.sub(x)),t.props.value):e.__}function dr(e,t){L.useDebugValue&&L.useDebugValue(t?t(e):e)}function fr(e){var t=oe(Y++,10),r=ne();return t.__=e,x.componentDidCatch||(x.componentDidCatch=function(n,o){t.__&&t.__(n,o),r[1](n)}),[r[0],function(){r[1](void 0)}]}function hr(){var e=oe(Y++,11);if(!e.__){for(var t=x.__v;t!==null&&!t.__m&&t.__!==null;)t=t.__;var r=t.__m||(t.__m=[0,0]);e.__="P"+r[0]+"-"+r[1]++}return e.__}function gr(){for(var e;e=yt.shift();)if(e.__P&&e.__H)try{e.__H.__h.forEach(Se),e.__H.__h.forEach(Ne),e.__H.__h=[]}catch(t){e.__H.__h=[],L.__e(t,e.__v)}}L.__b=function(e){x=null,ot&&ot(e)},L.__=function(e,t){t.__k&&t.__k.__m&&(e.__m=t.__k.__m),st&&st(e,t)},L.__r=function(e){at&&at(e),Y=0;var t=(x=e.__c).__H;t&&($e===x?(t.__h=[],x.__h=[],t.__.forEach(function(r){r.__N&&(r.__=r.__N),r.__V=ke,r.__N=r.i=void 0})):(t.__h.forEach(Se),t.__h.forEach(Ne),t.__h=[],Y=0)),$e=x},L.diffed=function(e){it&&it(e);var t=e.__c;t&&t.__H&&(t.__H.__h.length&&(yt.push(t)!==1&&nt===L.requestAnimationFrame||((nt=L.requestAnimationFrame)||pr)(gr)),t.__H.__.forEach(function(r){r.i&&(r.__H=r.i),r.__V!==ke&&(r.__=r.__V),r.i=void 0,r.__V=ke})),$e=x=null},L.__c=function(e,t){t.some(function(r){try{r.__h.forEach(Se),r.__h=r.__h.filter(function(n){return!n.__||Ne(n)})}catch(n){t.some(function(o){o.__h&&(o.__h=[])}),t=[],L.__e(n,r.__v)}}),ct&&ct(e,t)},L.unmount=function(e){lt&&lt(e);var t,r=e.__c;r&&r.__H&&(r.__H.__.forEach(function(n){try{Se(n)}catch(o){t=o}}),r.__H=void 0,t&&L.__e(t,r.__v))};var _t=typeof requestAnimationFrame=="function";function pr(e){var t,r=function(){clearTimeout(n),_t&&cancelAnimationFrame(t),setTimeout(e)},n=setTimeout(r,100);_t&&(t=requestAnimationFrame(r))}function Se(e){var t=x,r=e.__c;typeof r=="function"&&(e.__c=void 0,r()),x=t}function Ne(e){var t=x;e.__c=e.__(),x=t}function Ge(e,t){return!e||e.length!==t.length||t.some(function(r,n){return r!==e[n]})}function xt(e,t){return typeof t=="function"?t(e):t}const br=Object.defineProperty({__proto__:null,useCallback:ce,useContext:ur,useDebugValue:dr,useEffect:lr,useErrorBoundary:fr,useId:hr,useImperativeHandle:_r,useLayoutEffect:Ct,useMemo:he,useReducer:wt,useRef:sr,useState:ne},Symbol.toStringTag,{value:"Module"}),mr="http://www.w3.org/2000/svg";function vr(){const e=n=>C.createElementNS(mr,n),t=U(e("svg"),{width:"32",height:"30",viewBox:"0 0 72 66",fill:"inherit"}),r=U(e("path"),{transform:"translate(11, 11)",d:"M29,2.26a4.67,4.67,0,0,0-8,0L14.42,13.53A32.21,32.21,0,0,1,32.17,40.19H27.55A27.68,27.68,0,0,0,12.09,17.47L6,28a15.92,15.92,0,0,1,9.23,12.17H4.62A.76.76,0,0,1,4,39.06l2.94-5a10.74,10.74,0,0,0-3.36-1.9l-2.91,5a4.54,4.54,0,0,0,1.69,6.24A4.66,4.66,0,0,0,4.62,44H19.15a19.4,19.4,0,0,0-8-17.31l2.31-4A23.87,23.87,0,0,1,23.76,44H36.07a35.88,35.88,0,0,0-16.41-31.8l4.67-8a.77.77,0,0,1,1.05-.27c.53.29,20.29,34.77,20.66,35.17a.76.76,0,0,1-.68,1.13H40.6q.09,1.91,0,3.81h4.78A4.59,4.59,0,0,0,50,39.43a4.49,4.49,0,0,0-.62-2.28Z"});return t.appendChild(r),t}function yr({options:e}){const t=he(()=>({__html:vr().outerHTML}),[]);return p("h2",{class:"dialog__header"},p("span",{class:"dialog__title"},e.formTitle),e.showBranding?p("a",{class:"brand-link",target:"_blank",href:"https://sentry.io/welcome/",title:"Powered by Sentry",rel:"noopener noreferrer",dangerouslySetInnerHTML:t}):null)}function wr(e,t){const r=[];return t.isNameRequired&&!e.name&&r.push(t.nameLabel),t.isEmailRequired&&!e.email&&r.push(t.emailLabel),e.message||r.push(t.messageLabel),r}function Ae(e,t){const r=e.get(t);return typeof r=="string"?r.trim():""}function Cr({options:e,defaultEmail:t,defaultName:r,onFormClose:n,onSubmit:o,onSubmitSuccess:a,onSubmitError:l,showEmail:s,showName:u,screenshotInput:c}){const{tags:d,addScreenshotButtonLabel:i,removeScreenshotButtonLabel:h,cancelButtonLabel:_,emailLabel:f,emailPlaceholder:v,isEmailRequired:m,isNameRequired:g,messageLabel:y,messagePlaceholder:A,nameLabel:E,namePlaceholder:G,submitButtonLabel:q,isRequiredLabel:R}=e,[z,T]=ne(!1),[I,K]=ne(null),[b,w]=ne(!1),H=c==null?void 0:c.input,[M,ee]=ne(null),ae=ce(D=>{ee(D),w(!1)},[]),P=ce(D=>{const V=wr(D,{emailLabel:f,isEmailRequired:m,isNameRequired:g,messageLabel:y,nameLabel:E});return V.length>0?K(`Please enter in the following required fields: ${V.join(", ")}`):K(null),V.length===0},[f,m,g,y,E]),B=ce(async D=>{T(!0);try{if(D.preventDefault(),!(D.target instanceof HTMLFormElement))return;const V=new FormData(D.target),ge=await(c&&b?c.value():void 0),J={name:Ae(V,"name"),email:Ae(V,"email"),message:Ae(V,"message"),attachments:ge?[ge]:void 0};if(!P(J))return;try{const j=await o({name:J.name,email:J.email,message:J.message,source:Wt,tags:d},{attachments:J.attachments});a(J,j)}catch(j){we&&ye.error(j),K(j),l(j)}}finally{T(!1)}},[c&&b,a,l]);return p("form",{class:"form",onSubmit:B},H&&b?p(H,{onError:ae}):null,p("fieldset",{class:"form__right","data-sentry-feedback":!0,disabled:z},p("div",{class:"form__top"},I?p("div",{class:"form__error-container"},I):null,u?p("label",{for:"name",class:"form__label"},p(He,{label:E,isRequiredLabel:R,isRequired:g}),p("input",{class:"form__input",defaultValue:r,id:"name",name:"name",placeholder:G,required:g,type:"text"})):p("input",{"aria-hidden":!0,value:r,name:"name",type:"hidden"}),s?p("label",{for:"email",class:"form__label"},p(He,{label:f,isRequiredLabel:R,isRequired:m}),p("input",{class:"form__input",defaultValue:t,id:"email",name:"email",placeholder:v,required:m,type:"email"})):p("input",{"aria-hidden":!0,value:t,name:"email",type:"hidden"}),p("label",{for:"message",class:"form__label"},p(He,{label:y,isRequiredLabel:R,isRequired:!0}),p("textarea",{autoFocus:!0,class:"form__input form__input--textarea",id:"message",name:"message",placeholder:A,required:!0,rows:5})),H?p("label",{for:"screenshot",class:"form__label"},p("button",{class:"btn btn--default",disabled:z,type:"button",onClick:()=>{ee(null),w(D=>!D)}},b?h:i),M?p("div",{class:"form__error-container"},M.message):null):null),p("div",{class:"btn-group"},p("button",{class:"btn btn--primary",disabled:z,type:"submit"},q),p("button",{class:"btn btn--default",disabled:z,type:"button",onClick:n},_))))}function He({label:e,isRequired:t,isRequiredLabel:r}){return p("span",{class:"form__label__text"},e,t&&p("span",{class:"form__label__text--required"},r))}const ve=16,ut=17,xr="http://www.w3.org/2000/svg";function kr(){const e=u=>Z.document.createElementNS(xr,u),t=U(e("svg"),{width:`${ve}`,height:`${ut}`,viewBox:`0 0 ${ve} ${ut}`,fill:"inherit"}),r=U(e("g"),{clipPath:"url(#clip0_57_156)"}),n=U(e("path"),{"fill-rule":"evenodd","clip-rule":"evenodd",d:"M3.55544 15.1518C4.87103 16.0308 6.41775 16.5 8 16.5C10.1217 16.5 12.1566 15.6571 13.6569 14.1569C15.1571 12.6566 16 10.6217 16 8.5C16 6.91775 15.5308 5.37103 14.6518 4.05544C13.7727 2.73985 12.5233 1.71447 11.0615 1.10897C9.59966 0.503466 7.99113 0.34504 6.43928 0.653721C4.88743 0.962403 3.46197 1.72433 2.34315 2.84315C1.22433 3.96197 0.462403 5.38743 0.153721 6.93928C-0.15496 8.49113 0.00346625 10.0997 0.608967 11.5615C1.21447 13.0233 2.23985 14.2727 3.55544 15.1518ZM4.40546 3.1204C5.46945 2.40946 6.72036 2.03 8 2.03C9.71595 2.03 11.3616 2.71166 12.575 3.92502C13.7883 5.13838 14.47 6.78405 14.47 8.5C14.47 9.77965 14.0905 11.0306 13.3796 12.0945C12.6687 13.1585 11.6582 13.9878 10.476 14.4775C9.29373 14.9672 7.99283 15.0953 6.73777 14.8457C5.48271 14.596 4.32987 13.9798 3.42502 13.075C2.52018 12.1701 1.90397 11.0173 1.65432 9.76224C1.40468 8.50718 1.5328 7.20628 2.0225 6.02404C2.5122 4.8418 3.34148 3.83133 4.40546 3.1204Z"}),o=U(e("path"),{d:"M6.68775 12.4297C6.78586 12.4745 6.89218 12.4984 7 12.5C7.11275 12.4955 7.22315 12.4664 7.32337 12.4145C7.4236 12.3627 7.51121 12.2894 7.58 12.2L12 5.63999C12.0848 5.47724 12.1071 5.28902 12.0625 5.11098C12.0178 4.93294 11.9095 4.77744 11.7579 4.67392C11.6064 4.57041 11.4221 4.52608 11.24 4.54931C11.0579 4.57254 10.8907 4.66173 10.77 4.79999L6.88 10.57L5.13 8.56999C5.06508 8.49566 4.98613 8.43488 4.89768 8.39111C4.80922 8.34735 4.713 8.32148 4.61453 8.31498C4.51605 8.30847 4.41727 8.32147 4.32382 8.35322C4.23038 8.38497 4.14413 8.43484 4.07 8.49999C3.92511 8.63217 3.83692 8.81523 3.82387 9.01092C3.81083 9.2066 3.87393 9.39976 4 9.54999L6.43 12.24C6.50187 12.3204 6.58964 12.385 6.68775 12.4297Z"});t.appendChild(r).append(o,n);const a=e("defs"),l=U(e("clipPath"),{id:"clip0_57_156"}),s=U(e("rect"),{width:`${ve}`,height:`${ve}`,fill:"white",transform:"translate(0 0.5)"});return l.appendChild(s),a.appendChild(l),t.appendChild(a).appendChild(l).appendChild(s),t}function Sr({open:e,onFormSubmitted:t,...r}){const n=r.options,o=he(()=>({__html:kr().outerHTML}),[]),[a,l]=ne(null),s=ce(()=>{a&&(clearTimeout(a),l(null)),t()},[a]),u=ce((c,d)=>{r.onSubmitSuccess(c,d),l(setTimeout(()=>{t(),l(null)},jt))},[t]);return p(fe,null,a?p("div",{class:"success__position",onClick:s},p("div",{class:"success__content"},n.successMessageText,p("span",{class:"success__icon",dangerouslySetInnerHTML:o}))):p("dialog",{class:"dialog",onClick:n.onFormClose,open:e},p("div",{class:"dialog__position"},p("div",{class:"dialog__content",onClick:c=>{c.stopPropagation()}},p(yr,{options:n}),p(Cr,{...r,onSubmitSuccess:u})))))}const Er=`
.dialog {
  position: fixed;
  z-index: var(--z-index);
  margin: 0;
  inset: 0;

  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  height: 100vh;
  width: 100vw;

  color: var(--dialog-color, var(--foreground));
  fill: var(--dialog-color, var(--foreground));
  line-height: 1.75em;

  background-color: rgba(0, 0, 0, 0.05);
  border: none;
  inset: 0;
  opacity: 1;
  transition: opacity 0.2s ease-in-out;
}

.dialog__position {
  position: fixed;
  z-index: var(--z-index);
  inset: var(--dialog-inset);
  padding: var(--page-margin);
  display: flex;
  max-height: calc(100vh - (2 * var(--page-margin)));
}
@media (max-width: 600px) {
  .dialog__position {
    inset: var(--page-margin);
    padding: 0;
  }
}

.dialog__position:has(.editor) {
  inset: var(--page-margin);
  padding: 0;
}

.dialog:not([open]) {
  opacity: 0;
  pointer-events: none;
  visibility: hidden;
}
.dialog:not([open]) .dialog__content {
  transform: translate(0, -16px) scale(0.98);
}

.dialog__content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: var(--dialog-padding, 24px);
  max-width: 100%;
  width: 100%;
  max-height: 100%;
  overflow: auto;

  background: var(--dialog-background, var(--background));
  border-radius: var(--dialog-border-radius, 20px);
  border: var(--dialog-border, var(--border));
  box-shadow: var(--dialog-box-shadow, var(--box-shadow));
  transform: translate(0, 0) scale(1);
  transition: transform 0.2s ease-in-out;
}

`,Lr=`
.dialog__header {
  display: flex;
  gap: 4px;
  justify-content: space-between;
  font-weight: var(--dialog-header-weight, 600);
  margin: 0;
}
.dialog__title {
  align-self: center;
  width: var(--form-width, 272px);
}

@media (max-width: 600px) {
  .dialog__title {
    width: auto;
  }
}

.dialog__position:has(.editor) .dialog__title {
  width: auto;
}


.brand-link {
  display: inline-flex;
}
.brand-link:focus-visible {
  outline: var(--outline);
}
`,Tr=`
.form {
  display: flex;
  overflow: auto;
  flex-direction: row;
  gap: 16px;
  flex: 1 0;
}

.form fieldset {
  border: none;
  margin: 0;
  padding: 0;
}

.form__right {
  flex: 0 0 auto;
  display: flex;
  overflow: auto;
  flex-direction: column;
  justify-content: space-between;
  gap: 20px;
  width: var(--form-width, 100%);
}

.dialog__position:has(.editor) .form__right {
  width: var(--form-width, 272px);
}

.form__top {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form__error-container {
  color: var(--error-color);
  fill: var(--error-color);
}

.form__label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0px;
}

.form__label__text {
  display: flex;
  gap: 4px;
  align-items: center;
}

.form__label__text--required {
  font-size: 0.85em;
}

.form__input {
  font-family: inherit;
  line-height: inherit;
  background: transparent;
  box-sizing: border-box;
  border: var(--input-border, var(--border));
  border-radius: var(--input-border-radius, 6px);
  color: var(--input-color, inherit);
  fill: var(--input-color, inherit);
  font-size: var(--input-font-size, inherit);
  font-weight: var(--input-font-weight, 500);
  padding: 6px 12px;
}

.form__input::placeholder {
  opacity: 0.65;
  color: var(--input-placeholder-color, inherit);
  filter: var(--interactive-filter);
}

.form__input:focus-visible {
  outline: var(--input-focus-outline, var(--outline));
}

.form__input--textarea {
  font-family: inherit;
  resize: vertical;
}

.error {
  color: var(--error-color);
  fill: var(--error-color);
}
`,Fr=`
.btn-group {
  display: grid;
  gap: 8px;
}

.btn {
  line-height: inherit;
  border: var(--button-border, var(--border));
  border-radius: var(--button-border-radius, 6px);
  cursor: pointer;
  font-family: inherit;
  font-size: var(--button-font-size, inherit);
  font-weight: var(--button-font-weight, 600);
  padding: var(--button-padding, 6px 16px);
}
.btn[disabled] {
  opacity: 0.6;
  pointer-events: none;
}

.btn--primary {
  color: var(--button-primary-color, var(--accent-foreground));
  fill: var(--button-primary-color, var(--accent-foreground));
  background: var(--button-primary-background, var(--accent-background));
  border: var(--button-primary-border, var(--border));
  border-radius: var(--button-primary-border-radius, 6px);
  font-weight: var(--button-primary-font-weight, 500);
}
.btn--primary:hover {
  color: var(--button-primary-hover-color, var(--accent-foreground));
  fill: var(--button-primary-hover-color, var(--accent-foreground));
  background: var(--button-primary-hover-background, var(--accent-background));
  filter: var(--interactive-filter);
}
.btn--primary:focus-visible {
  background: var(--button-primary-hover-background, var(--accent-background));
  filter: var(--interactive-filter);
  outline: var(--button-primary-focus-outline, var(--outline));
}

.btn--default {
  color: var(--button-color, var(--foreground));
  fill: var(--button-color, var(--foreground));
  background: var(--button-background, var(--background));
  border: var(--button-border, var(--border));
  border-radius: var(--button-border-radius, 6px);
  font-weight: var(--button-font-weight, 500);
}
.btn--default:hover {
  color: var(--button-color, var(--foreground));
  fill: var(--button-color, var(--foreground));
  background: var(--button-hover-background, var(--background));
  filter: var(--interactive-filter);
}
.btn--default:focus-visible {
  background: var(--button-hover-background, var(--background));
  filter: var(--interactive-filter);
  outline: var(--button-focus-outline, var(--outline));
}
`,Dr=`
.success__position {
  position: fixed;
  inset: var(--dialog-inset);
  padding: var(--page-margin);
  z-index: var(--z-index);
}
.success__content {
  background: var(--success-background, var(--background));
  border: var(--success-border, var(--border));
  border-radius: var(--success-border-radius, 1.7em/50%);
  box-shadow: var(--success-box-shadow, var(--box-shadow));
  font-weight: var(--success-font-weight, 600);
  color: var(--success-color);
  fill: var(--success-color);
  padding: 12px 24px;
  line-height: 1.75em;

  display: grid;
  align-items: center;
  grid-auto-flow: column;
  gap: 6px;
  cursor: default;
}

.success__icon {
  display: flex;
}
`;function $r(e){const t=C.createElement("style");return t.textContent=`
:host {
  --dialog-inset: var(--inset);
}

${Er}
${Lr}
${Tr}
${Fr}
${Dr}
`,e&&t.setAttribute("nonce",e),t}function Ar(){const e=Ue().getUser(),t=Et().getUser(),r=Lt().getUser();return e&&Object.keys(e).length?e:t&&Object.keys(t).length?t:r}const Vr=(()=>({name:"FeedbackModal",setupOnce(){},createDialog:({options:e,screenshotIntegration:t,sendFeedback:r,shadow:n})=>{const o=n,a=e.useSentryUser,l=Ar(),s=C.createElement("div"),u=$r(e.styleNonce);let c="";const d={get el(){return s},appendToDom(){!o.contains(u)&&!o.contains(s)&&(o.appendChild(u),o.appendChild(s))},removeFromDom(){s.remove(),u.remove(),C.body.style.overflow=c},open(){var _,f;h(!0),(_=e.onFormOpen)==null||_.call(e),(f=Le())==null||f.emit("openFeedbackWidget"),c=C.body.style.overflow,C.body.style.overflow="hidden"},close(){h(!1),C.body.style.overflow=c}},i=t==null?void 0:t.createInput({h:p,hooks:br,dialog:d,options:e}),h=_=>{cr(p(Sr,{options:e,screenshotInput:i,showName:e.showName||e.isNameRequired,showEmail:e.showEmail||e.isEmailRequired,defaultName:a&&l&&l[a.name]||"",defaultEmail:a&&l&&l[a.email]||"",onFormClose:()=>{var f;h(!1),(f=e.onFormClose)==null||f.call(e)},onSubmit:r,onSubmitSuccess:(f,v)=>{var m;h(!1),(m=e.onSubmitSuccess)==null||m.call(e,f,v)},onSubmitError:f=>{var v;(v=e.onSubmitError)==null||v.call(e,f)},onFormSubmitted:()=>{var f;(f=e.onFormSubmitted)==null||f.call(e)},open:_}),s)};return d}}));function Hr({h:e}){return function(){return e("svg",{"data-test-id":"icon-close",viewBox:"0 0 16 16",fill:"#2B2233",height:"25px",width:"25px"},e("circle",{r:"7",cx:"8",cy:"8",fill:"white"}),e("path",{strokeWidth:"1.5",d:"M8,16a8,8,0,1,1,8-8A8,8,0,0,1,8,16ZM8,1.53A6.47,6.47,0,1,0,14.47,8,6.47,6.47,0,0,0,8,1.53Z"}),e("path",{strokeWidth:"1.5",d:"M5.34,11.41a.71.71,0,0,1-.53-.22.74.74,0,0,1,0-1.06l5.32-5.32a.75.75,0,0,1,1.06,1.06L5.87,11.19A.74.74,0,0,1,5.34,11.41Z"}),e("path",{strokeWidth:"1.5",d:"M10.66,11.41a.74.74,0,0,1-.53-.22L4.81,5.87A.75.75,0,0,1,5.87,4.81l5.32,5.32a.74.74,0,0,1,0,1.06A.71.71,0,0,1,10.66,11.41Z"}))}}function Rr(e){const t=C.createElement("style"),r="#1A141F",n="#302735";return t.textContent=`
.editor {
  display: flex;
  flex-grow: 1;
  flex-direction: column;
}

.editor__image-container {
  justify-items: center;
  padding: 15px;
  position: relative;
  height: 100%;
  border-radius: var(--menu-border-radius, 6px);

  background-color: ${r};
  background-image: repeating-linear-gradient(
      -145deg,
      transparent,
      transparent 8px,
      ${r} 8px,
      ${r} 11px
    ),
    repeating-linear-gradient(
      -45deg,
      transparent,
      transparent 15px,
      ${n} 15px,
      ${n} 16px
    );
}

.editor__canvas-container {
  width: 100%;
  height: 100%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.editor__canvas-container > * {
  object-fit: contain;
  position: absolute;
}

.editor__tool-container {
  padding-top: 8px;
  display: flex;
  justify-content: center;
}

.editor__tool-bar {
  display: flex;
  gap: 8px;
}

.editor__tool {
  display: flex;
  padding: 8px 12px;
  justify-content: center;
  align-items: center;
  border: var(--button-border, var(--border));
  border-radius: var(--button-border-radius, 6px);
  background: var(--button-background, var(--background));
  color: var(--button-color, var(--foreground));
}

.editor__tool--active {
  background: var(--button-primary-background, var(--accent-background));
  color: var(--button-primary-color, var(--accent-foreground));
}

.editor__rect {
  position: absolute;
  z-index: 2;
}

.editor__rect button {
  opacity: 0;
  position: absolute;
  top: -12px;
  right: -12px;
  cursor: pointer;
  padding: 0;
  z-index: 3;
  border: none;
  background: none;
}

.editor__rect:hover button {
  opacity: 1;
}
`,e&&t.setAttribute("nonce",e),t}function Mr({h:e}){return function({action:r,setAction:n}){return e("div",{class:"editor__tool-container"},e("div",{class:"editor__tool-bar"},e("button",{type:"button",class:`editor__tool ${r==="highlight"?"editor__tool--active":""}`,onClick:()=>{n(r==="highlight"?"":"highlight")}},"Highlight"),e("button",{type:"button",class:`editor__tool ${r==="hide"?"editor__tool--active":""}`,onClick:()=>{n(r==="hide"?"":"hide")}},"Hide")))}}function Ir({hooks:e}){function t(){const[r,n]=e.useState(Z.devicePixelRatio??1);return e.useEffect(()=>{const o=()=>{n(Z.devicePixelRatio)},a=matchMedia(`(resolution: ${Z.devicePixelRatio}dppx)`);return a.addEventListener("change",o),()=>{a.removeEventListener("change",o)}},[]),r}return function({onBeforeScreenshot:n,onScreenshot:o,onAfterScreenshot:a,onError:l}){const s=t();e.useEffect(()=>{(async()=>{n();const c=await ue.mediaDevices.getDisplayMedia({video:{width:Z.innerWidth*s,height:Z.innerHeight*s},audio:!1,monitorTypeSurfaces:"exclude",preferCurrentTab:!0,selfBrowserSurface:"include",surfaceSwitching:"exclude"}),d=C.createElement("video");await new Promise((i,h)=>{d.srcObject=c,d.onloadedmetadata=()=>{o(d,s),c.getTracks().forEach(_=>_.stop()),i()},d.play().catch(h)}),a()})().catch(l)},[])}}function Pr(e,t,r){switch(e.type){case"highlight":{t.shadowColor="rgba(0, 0, 0, 0.7)",t.shadowBlur=50,t.fillStyle=r,t.fillRect(e.x-1,e.y-1,e.w+2,e.h+2),t.clearRect(e.x,e.y,e.w,e.h);break}case"hide":t.fillStyle="rgb(0, 0, 0)",t.fillRect(e.x,e.y,e.w,e.h);break}}function Q(e,t,r){if(!e)return;const n=e.getContext("2d",t);n&&r(e,n)}function Re(e,t){Q(e,{alpha:!0},(r,n)=>{n.drawImage(t,0,0,t.width,t.height,0,0,r.width,r.height)})}function Me(e,t,r){Q(e,{alpha:!0},(n,o)=>{r.length&&(o.fillStyle="rgba(0, 0, 0, 0.25)",o.fillRect(0,0,n.width,n.height)),r.forEach(a=>{Pr(a,o,t)})})}function Br({h:e,hooks:t,outputBuffer:r,dialog:n,options:o}){const a=Ir({hooks:t}),l=Mr({h:e}),s=Hr({h:e}),u={__html:Rr(o.styleNonce).innerText},c=n.el.style,d=({screenshot:i})=>{const[h,_]=t.useState("highlight"),[f,v]=t.useState([]),m=t.useRef(null),g=t.useRef(null),y=t.useRef(null),A=t.useRef(null),[E,G]=t.useState(1),q=t.useMemo(()=>{const b=C.getElementById(o.id);if(!b)return"white";const w=getComputedStyle(b);return w.getPropertyValue("--button-primary-background")||w.getPropertyValue("--accent-background")},[o.id]);t.useLayoutEffect(()=>{const b=()=>{const w=m.current;w&&(Q(i.canvas,{alpha:!1},H=>{const M=Math.min(w.clientWidth/H.width,w.clientHeight/H.height);G(M)}),(w.clientHeight===0||w.clientWidth===0)&&setTimeout(b,0))};return b(),Z.addEventListener("resize",b),()=>{Z.removeEventListener("resize",b)}},[i]);const R=t.useCallback((b,w)=>{Q(b,{alpha:!0},(H,M)=>{M.scale(w,w),H.width=i.canvas.width,H.height=i.canvas.height})},[i]);t.useEffect(()=>{R(g.current,i.dpi),Re(g.current,i.canvas)},[i]),t.useEffect(()=>{R(y.current,i.dpi),Q(y.current,{alpha:!0},(b,w)=>{w.clearRect(0,0,b.width,b.height)}),Me(y.current,q,f)},[f,q]),t.useEffect(()=>{R(r,i.dpi),Re(r,i.canvas),Q(C.createElement("canvas"),{alpha:!0},(b,w)=>{w.scale(i.dpi,i.dpi),b.width=i.canvas.width,b.height=i.canvas.height,Me(b,q,f),Re(r,b)})},[f,i,q]);const z=b=>{if(!h||!A.current)return;const w=A.current.getBoundingClientRect(),H={type:h,x:b.offsetX/E,y:b.offsetY/E},M=(P,B)=>{const D=(B.clientX-w.x)/E,V=(B.clientY-w.y)/E;return{type:P.type,x:Math.min(P.x,D),y:Math.min(P.y,V),w:Math.abs(D-P.x),h:Math.abs(V-P.y)}},ee=P=>{Q(y.current,{alpha:!0},(B,D)=>{D.clearRect(0,0,B.width,B.height)}),Me(y.current,q,[...f,M(H,P)])},ae=P=>{const B=M(H,P);B.w*E>=1&&B.h*E>=1&&v(D=>[...D,B]),C.removeEventListener("mousemove",ee),C.removeEventListener("mouseup",ae)};C.addEventListener("mousemove",ee),C.addEventListener("mouseup",ae)},T=t.useCallback(b=>w=>{w.preventDefault(),w.stopPropagation(),v(H=>{const M=[...H];return M.splice(b,1),M})},[]),I={width:`${i.canvas.width*E}px`,height:`${i.canvas.height*E}px`},K=b=>{b.stopPropagation()};return e("div",{class:"editor"},e("style",{nonce:o.styleNonce,dangerouslySetInnerHTML:u}),e("div",{class:"editor__image-container"},e("div",{class:"editor__canvas-container",ref:m},e("canvas",{ref:g,id:"background",style:I}),e("canvas",{ref:y,id:"foreground",style:I}),e("div",{ref:A,onMouseDown:z,style:I},f.map((b,w)=>e("div",{key:w,class:"editor__rect",style:{top:`${b.y*E}px`,left:`${b.x*E}px`,width:`${b.w*E}px`,height:`${b.h*E}px`}},e("button",{"aria-label":"Remove",onClick:T(w),onMouseDown:K,onMouseUp:K,type:"button"},e(s,null))))))),e(l,{action:h,setAction:_}))};return function({onError:h}){const[_,f]=t.useState();return a({onBeforeScreenshot:t.useCallback(()=>{c.display="none"},[]),onScreenshot:t.useCallback((v,m)=>{Q(C.createElement("canvas"),{alpha:!1},(g,y)=>{y.scale(m,m),g.width=v.videoWidth,g.height=v.videoHeight,y.drawImage(v,0,0,g.width,g.height),f({canvas:g,dpi:m})}),r.width=v.videoWidth,r.height=v.videoHeight},[]),onAfterScreenshot:t.useCallback(()=>{c.display="block"},[]),onError:t.useCallback(v=>{c.display="block",h(v)},[])}),_?e(d,{screenshot:_}):e("div",null)}}const Wr=(()=>({name:"FeedbackScreenshot",setupOnce(){},createInput:({h:e,hooks:t,dialog:r,options:n})=>{const o=C.createElement("canvas");return{input:Br({h:e,hooks:t,outputBuffer:o,dialog:r,options:n}),value:async()=>{const a=await new Promise(l=>{o.toBlob(l,"image/png")});if(a)return{data:new Uint8Array(await a.arrayBuffer()),filename:"screenshot.png",contentType:"application/png"}}}}}));export{Wr as a,qr as b,Ft as c,Vr as f,zr as g,Zt as s};

//# debugId=e27e8124-3b61-5000-9a23-c964fe7fabd0
