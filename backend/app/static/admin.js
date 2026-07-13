const $ = (s) => document.querySelector(s);
const content = $('#adminContent');
const dialog = $('#adminDialog');
const pageTitle = $('#adminPageTitle');
let currentTab = 'dashboard';

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));
const date = (value) => value ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '-';
const empty = (text) => `<div class="notice">${esc(text)}</div>`;
const titles = {dashboard:'数据概览',users:'用户管理',friends:'好友关系',posts:'动态管理',comments:'评论管理',reviews:'纸飞机审核',complaints:'举报中心',words:'敏感词库',configs:'运行配置',maintenance:'维护任务'};
const labels = {ACTIVE:'正常',BANNED:'封禁',MUTED:'禁言',DORMANT:'休眠',PENDING:'待处理',HANDLED:'已处理',REJECTED:'已驳回',PUBLIC:'公开',FRIENDS:'好友可见',PRIVATE:'仅自己'};
const badge = (value) => `<span class="badge">${esc(labels[value] || value || '-')}</span>`;
const head = (title, subtitle='', actions='') => `<div class="page-head"><div><h2>${esc(title)}</h2>${subtitle ? `<p>${esc(subtitle)}</p>` : ''}</div><div class="page-actions">${actions}</div></div>`;
const toast = (message) => { const node=$('#adminToast'); node.textContent=message; node.classList.add('show'); setTimeout(()=>node.classList.remove('show'),1800); };

async function call(path, options = {}) {
  const response = await fetch('/api/admin' + path, {
    ...options,
    credentials: 'same-origin',
    headers: {'Content-Type':'application/json', ...(options.headers||{})}
  });
  const json = await response.json().catch(() => ({}));
  if (response.status === 401 && path !== '/login') {
    showLogin(path === '/me' ? '' : '登录已失效，请重新登录');
    throw new Error('登录已失效');
  }
  if (!response.ok || json.success === false) throw new Error(json.message || '请求失败');
  return json.data;
}

async function render(tab = currentTab) {
  currentTab = tab;
  pageTitle.textContent = titles[tab] || '管理中心';
  document.querySelectorAll('[data-tab]').forEach((node) => node.classList.toggle('active', node.dataset.tab === tab));
  if (!content.children.length) content.innerHTML = '<div class="notice">正在加载…</div>';
  try {
    if (tab === 'dashboard') await renderDashboard();
    else if (tab === 'users') await renderUsers();
    else if (tab === 'posts') await renderPosts();
    else if (tab === 'comments') await renderComments();
    else if (tab === 'friends') await renderFriends();
    else if (tab === 'reviews') await renderReviews();
    else if (tab === 'complaints') await renderComplaints();
    else if (tab === 'words') await renderWords();
    else if (tab === 'configs') await renderConfigs();
    else if (tab === 'maintenance') renderMaintenance();
  } catch (error) {
    content.innerHTML = `<div class="notice error">${esc(error.message)}</div>`;
  }
}

async function renderDashboard() {
  const [data, reviews, complaints] = await Promise.all([call('/dashboard'), call('/reviews/letters'), call('/complaints')]);
  const kpis = [
    ['用户总数',data.total_users,'今日新增 '+data.today_registered_users],
    ['活跃用户',data.active_users,'当前可正常使用'],
    ['有效动态',data.total_posts,'内容存量'],
    ['今日会话',data.today_chat_rooms,'实时聊天'],
    ['今日纸飞机',data.today_letters,'释放 '+data.today_released_letters],
    ['今日打捞',data.today_salvaged_letters,'匿名互动'],
    ['待审核',data.risk_review_letters,'需要人工判断','urgent'],
    ['今日举报',data.today_complaints,'优先处理高风险','urgent']
  ];
  const pending = complaints.filter((item) => item.status === 'PENDING');
  content.innerHTML = `
    ${head('运营概览','平台核心数据与待办工作')}
    <div class="kpi-grid">${kpis.map(([label,value,meta,kind]) => `<div class="kpi ${kind||''}"><div class="kpi-label">${label}</div><div class="kpi-value">${value ?? 0}</div><div class="kpi-meta">${meta}</div></div>`).join('')}</div>
    <div class="admin-grid">
      <section class="admin-card col8"><h3>安全待办</h3>
        <div class="queue-row"><span class="queue-icon">⚑</span><div><strong>待处理举报</strong><small>用户提交的内容与账号举报</small></div><button class="ghost-action" data-action="render" data-value="complaints">${pending.length} 条</button></div>
        <div class="queue-row"><span class="queue-icon">✈</span><div><strong>纸飞机审核</strong><small>命中风险规则、等待人工复核</small></div><button class="ghost-action" data-action="render" data-value="reviews">${reviews.length} 条</button></div>
        <div class="queue-row"><span class="queue-icon">⌁</span><div><strong>今日自动拦截</strong><small>内容安全规则自动处理</small></div><strong>${data.today_intercepts ?? 0}</strong></div>
      </section>
      <section class="admin-card col4"><h3>快捷操作</h3><div class="quick-actions">
        <button data-action="render" data-value="users"><b>用户检索</b><br><small>状态与资料管理</small></button>
        <button data-action="render" data-value="posts"><b>内容巡检</b><br><small>动态与媒体</small></button>
        <button data-action="render" data-value="complaints"><b>举报处置</b><br><small>审核处理队列</small></button>
        <button data-action="render" data-value="maintenance"><b>系统维护</b><br><small>安全运行任务</small></button>
      </div></section>
    </div>`;
}

async function renderUsers(query = '') {
  const users = await call('/users' + (query ? `?q=${encodeURIComponent(query)}` : ''));
  window.adminUserRows = users;
  content.innerHTML = `${head('用户管理','检索账号、查看状态并执行必要处置','<button class="primary" data-action="open-create-user">新建用户</button>')}
    <div class="toolbar"><input id="userSearch" value="${esc(query)}" placeholder="UID、邮箱或用户名"><button class="ghost-action" data-action="search-users">搜索</button><span class="muted">共 ${users.length} 条</span></div>
    <div class="admin-table-wrap"><table><thead><tr><th>用户</th><th>UID</th><th>邮箱</th><th>状态</th><th>注册时间</th><th>操作</th></tr></thead><tbody>
    ${users.map((u) => `<tr><td><b>${esc(u.username || u.anonymous_name)}</b></td><td><code>${esc(u.uid)}</code></td><td>${esc(u.email || '-')}</td><td>${badge(u.status)}</td><td>${date(u.created_at)}</td><td><button class="primary" data-action="edit-user" data-id="${u.id}">管理</button></td></tr>`).join('')}
    </tbody></table></div>`;
}
window.searchUsers = () => renderUsers($('#userSearch').value.trim());
window.openCreateUser = () => {
  dialog.innerHTML = `<h2>新建已验证用户</h2><label>邮箱</label><input id="newEmail"><label>用户名</label><input id="newUsername"><label>临时密码</label><input id="newPassword" type="password"><div class="row" style="justify-content:flex-end;margin-top:18px"><button class="ghost-action" data-action="close-dialog">取消</button><button class="primary" data-action="create-user">创建</button></div>`; dialog.showModal();
};
window.createUser = async () => { await call('/users',{method:'POST',body:JSON.stringify({email:$('#newEmail').value,username:$('#newUsername').value,password:$('#newPassword').value})}); dialog.close(); toast('用户已创建'); await renderUsers(); };
window.editUserById = (id) => {
  const u=(window.adminUserRows||[]).find((item)=>item.id===id); if(!u)return;
  const restore=u.status==='MUTED'?`<button class="ok" data-action="restore-user" data-id="${u.id}" data-value="unmute">解除禁言</button>`:u.status==='BANNED'?`<button class="ok" data-action="restore-user" data-id="${u.id}" data-value="unban">解除封禁</button>`:u.status==='DORMANT'?`<button class="ok" data-action="restore-user" data-id="${u.id}" data-value="activate">唤醒账号</button>`:'';
  dialog.innerHTML=`<div class="row"><div><p class="eyebrow">USER MANAGEMENT</p><h2>${esc(u.username||u.anonymous_name)}</h2></div>${badge(u.status)}</div><div class="notice">UID <b>${esc(u.uid)}</b> · UID 创建后不可修改</div><label>邮箱</label><input id="editEmail" value="${esc(u.email||'')}"><label>用户名</label><input id="editUsername" value="${esc(u.username||'')}"><label>简介</label><textarea id="editBio">${esc(u.bio||'')}</textarea><div class="moderation-actions">${restore}<button class="ghost-action" data-action="mute-user" data-id="${u.id}">禁言</button><button class="danger" data-action="ban-user" data-id="${u.id}">封禁</button></div><div class="row" style="justify-content:flex-end;margin-top:16px"><button class="ghost-action" data-action="close-dialog">取消</button><button class="primary" data-action="save-user" data-id="${u.id}">保存资料</button></div>`; dialog.showModal();
};
window.closeAdminDialog=()=>dialog.close();
window.saveUser=async(id)=>{await call(`/users/${id}`,{method:'PUT',body:JSON.stringify({email:$('#editEmail').value,username:$('#editUsername').value,bio:$('#editBio').value})});dialog.close();toast('用户资料已更新');await renderUsers();};
window.restoreUser=async(id,action)=>{await call(`/users/${id}/${action}`,{method:'POST'});dialog.close();toast('用户状态已恢复');await renderUsers();};
window.muteUser=async(id)=>{const raw=prompt('禁言时长（分钟）','60');if(raw===null)return;const minutes=Number(raw);if(!Number.isInteger(minutes)||minutes<1){toast('请输入有效分钟数');return;}const reason=prompt('禁言原因（可选）','')||null;await call(`/users/${id}/mute`,{method:'POST',body:JSON.stringify({minutes,reason})});dialog.close();toast('用户已禁言');await renderUsers();};
window.banUser=async(id)=>{if(!confirm('封禁后该账号将无法继续互动，确定继续？'))return;const reason=prompt('封禁原因（可选）','')||null;await call(`/users/${id}/ban`,{method:'POST',body:JSON.stringify({reason})});dialog.close();toast('用户已封禁');await renderUsers();};
window.deactivateUser=async(id)=>{if(confirm('确定停用该用户？')){await call(`/users/${id}`,{method:'DELETE'});toast('用户已停用');await renderUsers();}};

async function renderPosts() {
  const posts=await call('/social/posts'); window.adminPosts=posts;
  content.innerHTML=`${head('动态管理','巡检公开内容、媒体与互动数据')}<div class="toolbar"><input id="postSearch" placeholder="搜索作者或动态内容" oninput="filterPosts()"><select id="postVisibility" onchange="filterPosts()"><option value="">全部范围</option><option>PUBLIC</option><option>FRIENDS</option><option>PRIVATE</option></select><span class="muted">共 ${posts.length} 条</span></div><div id="postRows"></div>`; filterPosts();
}
window.filterPosts=()=>{const q=($('#postSearch')?.value||'').toLowerCase(),v=$('#postVisibility')?.value||'';const rows=(window.adminPosts||[]).filter(p=>(!q||String(p.text||'').toLowerCase().includes(q)||String(p.author_name||'').toLowerCase().includes(q)||String(p.author_uid||'').includes(q))&&(!v||p.visibility===v));$('#postRows').innerHTML=rows.length?`<div class="admin-card">${rows.map(p=>`<div class="item"><div class="row"><b>${esc(p.author_name||'未知用户')}</b><code>UID ${esc(p.author_uid||'-')}</code>${badge(p.visibility)}<span class="muted">${date(p.created_at)}</span></div><p>${esc(p.text||'[媒体动态]')}</p><div class="muted">动态 ${p.id} · 媒体 ${p.media.length} · 点赞 ${p.like_count} · 评论 ${p.comment_count}</div><button class="danger" data-action="delete-post" data-id="${p.id}">删除动态</button></div>`).join('')}</div>`:empty('没有符合条件的动态');};
window.deletePost=async(id)=>{if(confirm('删除后不可恢复，确定继续？')){await call(`/social/posts/${id}`,{method:'DELETE'});toast('动态已删除');await renderPosts();}};

async function renderComments(){const rows=await call('/social/comments');window.adminComments=rows;content.innerHTML=`${head('评论管理','检索评论内容并处理违规信息')}<div class="toolbar"><input id="commentSearch" placeholder="搜索用户或评论" oninput="filterComments()"><span class="muted">共 ${rows.length} 条</span></div><div id="commentRows"></div>`;filterComments();}
window.filterComments=()=>{const q=($('#commentSearch')?.value||'').toLowerCase();const rows=(window.adminComments||[]).filter(x=>!q||String(x.text||'').toLowerCase().includes(q)||String(x.author_name||'').toLowerCase().includes(q));$('#commentRows').innerHTML=rows.length?`<div class="admin-table-wrap"><table><thead><tr><th>用户</th><th>动态</th><th>评论内容</th><th>操作</th></tr></thead><tbody>${rows.map(x=>`<tr><td>${esc(x.author_name||'未知用户')}</td><td>#${x.post_id}</td><td>${esc(x.text)}</td><td><button class="danger" data-action="delete-comment" data-id="${x.id}">删除</button></td></tr>`).join('')}</tbody></table></div>`:empty('暂无评论');};
window.deleteComment=async(id)=>{if(confirm('确定删除该评论？')){await call(`/social/comments/${id}`,{method:'DELETE'});toast('评论已删除');await renderComments();}};

async function renderFriends(){const d=await call('/social/friends');content.innerHTML=`${head('好友关系','查看好友关系及申请状态')}<div class="admin-grid"><section class="admin-card col6"><h3>好友关系 · ${d.friendships.length}</h3>${d.friendships.map(x=>`<div class="queue-row"><span class="queue-icon">♧</span><div><strong>${esc(x.user_a.name)} ↔ ${esc(x.user_b.name)}</strong><small>UID ${esc(x.user_a.uid||'-')} · UID ${esc(x.user_b.uid||'-')} · ${date(x.created_at)}</small></div><button class="danger" data-action="delete-friendship" data-id="${x.id}">解除</button></div>`).join('')||empty('暂无好友关系')}</section><section class="admin-card col6"><h3>好友申请 · ${d.requests.length}</h3>${d.requests.map(x=>`<div class="queue-row"><span class="queue-icon">→</span><div><strong>${esc(x.requester.name)} → ${esc(x.addressee.name)}</strong><small>UID ${esc(x.requester.uid||'-')} → ${esc(x.addressee.uid||'-')} · ${esc(x.message||'无验证消息')}</small></div>${badge(x.status)}</div>`).join('')||empty('暂无好友申请')}</section></div>`;}
window.deleteFriendship=async(id)=>{if(confirm('确定解除这组好友关系？')){await call(`/social/friends/${id}`,{method:'DELETE'});toast('好友关系已解除');await renderFriends();}};

async function renderReviews(){const rows=await call('/reviews/letters');content.innerHTML=`${head('纸飞机审核','只处理命中风险规则的待审核内容')}<div class="admin-card">${rows.map(x=>`<div class="item"><div class="row"><b>纸飞机 #${x.id}</b><span class="muted">${date(x.created_at)}</span></div><pre>${esc(x.content||'[内容已销毁]')}</pre><button class="ok" data-action="review" data-id="${x.id}" data-value="approve">通过</button> <button class="danger" data-action="review" data-id="${x.id}" data-value="reject">拒绝</button></div>`).join('')||empty('审核队列已清空')}</div>`;}
window.review=async(id,action)=>{await call(`/reviews/letters/${id}/${action}`,{method:'POST',body:action==='approve'?JSON.stringify({release_now:false}):undefined});toast(action==='approve'?'已通过':'已拒绝');await renderReviews();};

async function renderComplaints(){const rows=await call('/complaints');window.adminComplaints=rows;content.innerHTML=`${head('举报中心','核对举报对象、原因和原始内容')}<div class="toolbar"><select id="complaintStatus" onchange="filterComplaints()"><option value="">全部状态</option><option>PENDING</option><option>HANDLED</option><option>REJECTED</option></select><span class="muted">共 ${rows.length} 条</span></div><div id="complaintRows"></div>`;filterComplaints();}
window.filterComplaints=()=>{const s=$('#complaintStatus')?.value||'';const rows=(window.adminComplaints||[]).filter(x=>!s||x.status===s);$('#complaintRows').innerHTML=rows.length?`<div class="admin-card">${rows.map(x=>`<div class="item"><div class="row"><b>举报 ${x.id}</b>${badge(x.status)}<span class="muted">${date(x.created_at)}</span></div><p><b>${esc(x.reason)}</b> · ${esc(x.description||'无补充说明')}</p>${x.reporter?`<div class="muted">举报人：${esc(x.reporter.username||x.reporter.anonymous_name)}（UID ${esc(x.reporter.uid)}）</div>`:''}${x.target_user?`<div class="muted">被举报用户：${esc(x.target_user.username||x.target_user.anonymous_name)}（UID ${esc(x.target_user.uid)}）</div>`:''}<pre>${esc(x.target_content||'[无可见内容]')}</pre>${x.status==='PENDING'? `<button class="ok" data-action="handle-complaint" data-id="${x.id}" data-value="HANDLED">确认违规</button> <button class="ghost-action" data-action="handle-complaint" data-id="${x.id}" data-value="REJECTED">驳回举报</button>${x.target_user?` <button class="danger" data-action="ban-reported" data-user-id="${x.target_user.id}" data-id="${x.id}">封禁账号</button>`:''}`:''}</div>`).join('')}</div>`:empty('没有符合条件的举报');};
window.banReportedUser=async(userId,complaintId)=>{if(!confirm('确认封禁被举报账号并将举报标记为已处理？'))return;const review_note=prompt('封禁原因','举报核实违规')||'举报核实违规';await call(`/complaints/${complaintId}/resolve`,{method:'POST',body:JSON.stringify({decision:'VIOLATION',action:'BAN',review_note})});toast('账号已封禁，举报已处理');await renderComplaints();};
window.handleComplaint=async(id,status)=>{const review_note=prompt('请输入审核结论或处理依据');if(!review_note)return;const decision=status==='REJECTED'?'REJECTED':'VIOLATION';let action='NONE';if(decision==='VIOLATION'){action=prompt('处置方式：NONE / REMOVE_CONTENT / MUTE / BAN','REMOVE_CONTENT')||'NONE';action=action.toUpperCase();}await call(`/complaints/${id}/resolve`,{method:'POST',body:JSON.stringify({decision,action,review_note})});toast('举报已完成闭环处理');await renderComplaints();};

async function renderWords(){const rows=await call('/sensitive-words');content.innerHTML=`${head('敏感词库','维护内容安全规则，新增后立即生效')}<div class="toolbar"><input id="newWord" placeholder="输入敏感词"><button class="primary" data-action="add-word">添加</button><span class="muted">共 ${rows.length} 条</span></div><div class="admin-table-wrap"><table><thead><tr><th>词语</th><th>分类</th><th>级别</th><th>操作</th></tr></thead><tbody>${rows.map(x=>`<tr><td><b>${esc(x.word)}</b></td><td>${esc(x.category)}</td><td>${badge(x.level)}</td><td><button class="danger" data-action="remove-word" data-id="${x.id}">删除</button></td></tr>`).join('')}</tbody></table></div>`;}
window.addWord=async()=>{const word=$('#newWord').value.trim();if(!word)return;await call('/sensitive-words',{method:'POST',body:JSON.stringify({word,category:'custom',level:'MEDIUM'})});toast('敏感词已添加');await renderWords();};
window.removeWord=async(id)=>{if(confirm('确定删除该规则？')){await call(`/sensitive-words/${id}`,{method:'DELETE'});toast('规则已删除');await renderWords();}};

async function renderConfigs(){const rows=await call('/configs');content.innerHTML=`${head('运行配置','修改平台运行参数，保存后即时生效')}<div class="admin-card">${rows.map(x=>`<div class="item row"><div style="min-width:260px;flex:1"><b>${esc(x.config_key)}</b></div><input style="max-width:360px" id="cfg_${esc(x.config_key)}" value="${esc(x.config_value)}"><button class="primary" data-action="save-config" data-value="${esc(x.config_key)}">保存</button></div>`).join('')}</div>`;}
window.saveConfig=async(key)=>{await call(`/configs/${key}`,{method:'PUT',body:JSON.stringify({config_value:$(`#cfg_${key}`).value})});toast('配置已保存');};
function renderMaintenance(){content.innerHTML=`${head('维护任务','高影响操作仅在确认需要时执行')}<div class="admin-grid"><section class="admin-card col4"><h3>重建打捞池</h3><p class="muted">重新同步可打捞纸飞机索引。</p><button class="primary" data-action="maintain" data-value="rebuild-available-pools">执行</button></section><section class="admin-card col4"><h3>释放到期纸飞机</h3><p class="muted">立即扫描并释放已到期内容。</p><button class="primary" data-action="maintain" data-value="process-due-letters-once">执行</button></section><section class="admin-card col4"><h3>过期内容清理</h3><p class="muted">销毁已超过保存期限的数据。</p><button class="danger" data-action="maintain" data-value="cleanup-once">执行</button></section></div><div id="maintainMsg"></div>`;}
window.maintain=async(action)=>{if(!confirm('确定执行该维护任务？'))return;const result=await call(`/maintenance/${action}`,{method:'POST'});$('#maintainMsg').innerHTML=`<div class="notice">任务完成：${esc(JSON.stringify(result))}</div>`;toast('维护任务已完成');};

document.addEventListener('click',(event)=>{
  const node=event.target.closest('[data-action]'); if(!node)return;
  const id=Number(node.dataset.id||0), value=node.dataset.value||'';
  const actions={
    render:()=>render(value), 'open-create-user':()=>openCreateUser(), 'search-users':()=>searchUsers(),
    'edit-user':()=>editUserById(id), 'close-dialog':()=>closeAdminDialog(), 'create-user':()=>createUser(),
    'restore-user':()=>restoreUser(id,value), 'mute-user':()=>muteUser(id), 'ban-user':()=>banUser(id), 'save-user':()=>saveUser(id),
    'delete-post':()=>deletePost(id), 'delete-comment':()=>deleteComment(id), 'delete-friendship':()=>deleteFriendship(id),
    review:()=>review(id,value), 'handle-complaint':()=>handleComplaint(id,value),
    'ban-reported':()=>banReportedUser(Number(node.dataset.userId),id),
    'add-word':()=>addWord(), 'remove-word':()=>removeWord(id), 'save-config':()=>saveConfig(value), maintain:()=>maintain(value),
  };
  const action=actions[node.dataset.action]; if(action){event.preventDefault();action();}
});

document.querySelectorAll('[data-tab]').forEach((node)=>node.onclick=()=>render(node.dataset.tab));
$('#adminLoginBtn').onclick=async()=>{try{await call('/login',{method:'POST',body:JSON.stringify({username:$('#adminUser').value,password:$('#adminPass').value})});showAdmin();}catch(error){$('#adminLoginMsg').innerHTML=`<div class="notice error">${esc(error.message)}</div>`;}};
$('#adminPass').addEventListener('keydown',(event)=>{if(event.key==='Enter')$('#adminLoginBtn').click();});
$('#adminLogout').onclick=async()=>{try{await call('/logout',{method:'POST'});}finally{showLogin();}};
function showAdmin(){$('#adminLogin').classList.add('hidden');$('#adminWork').classList.remove('hidden');render('dashboard');}
function showLogin(message=''){$('#adminWork').classList.add('hidden');$('#adminLogin').classList.remove('hidden');$('#adminLoginMsg').innerHTML=message?`<div class="notice error">${esc(message)}</div>`:'';}
call('/me').then(showAdmin).catch(()=>{});
