// 启动入口（必须最后加载）
// 经典脚本，由 index.html 按顺序加载并共享全局作用域。
init().catch(e=>{
  let message=e.message;
  try{message=tr('ui.failed_to_load_error',{error:e.message});}catch(error){}
  $('#list').innerHTML = `<div class="empty">${esc(message)}</div>`;
  toast(message, true);
});
