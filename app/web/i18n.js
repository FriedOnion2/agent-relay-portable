// Explicit keys are shared by static bindings, dynamic UI, and server messages.
globalThis.RelayI18n = (() => {
  let catalogs;
  const slots = value => [...value.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort().join(',');
  function configure(zh, en){
    if(Object.keys(zh).sort().join('\n') !== Object.keys(en).sort().join('\n')) throw new Error('Locale keys differ');
    for(const key of Object.keys(zh)){
      if(!/^(ui|msg|err)\.[a-z][a-z0-9_]*$/.test(key) || typeof zh[key] !== 'string' || typeof en[key] !== 'string' || slots(zh[key]) !== slots(en[key]))
        throw new Error('Invalid locale entry: '+key);
    }
    catalogs={zh,en};
  }
  async function load(){
    const values=await Promise.all(['zh','en'].map(async language=>{
      const response=await fetch('/static/locales.'+language+'.json');
      if(!response.ok)throw new Error('Cannot load locale: '+language);
      return response.json();
    }));
    configure(...values);
  }
  function translate(language,key,params={}){
    const template=catalogs?.[language]?.[key];
    if(template === undefined)throw new Error('Unknown message code: '+key);
    return template.replace(/\{(\w+)\}/g,(_,name)=>{
      if(!Object.prototype.hasOwnProperty.call(params,name))throw new Error('Missing message parameter: '+key+'.'+name);
      return String(message(language,params[name]) ?? '');
    });
  }
  function message(language,value){
    if(!value || typeof value !== 'object' || typeof value.code !== 'string')return value;
    if(catalogs?.[language]?.[value.code] === undefined)return value.fallback || value.code;
    try{return translate(language,value.code,value.params || {});}
    catch(error){return value.fallback || value.code;}
  }
  function apply(language,root){
    for(const element of root.querySelectorAll('[data-i18n],[data-i18n-placeholder],[data-i18n-title],[data-i18n-aria-label]')){
      if(element.dataset.i18n)element.textContent=translate(language,element.dataset.i18n);
      for(const attribute of ['placeholder','title','aria-label']){
        const key=element.getAttribute('data-i18n-'+attribute);
        if(key)element.setAttribute(attribute,translate(language,key));
      }
    }
  }
  return {configure,load,translate,message,apply};
})();
