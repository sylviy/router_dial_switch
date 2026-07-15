// ============================================================================
// 「上网方式」选择器查找器
// ----------------------------------------------------------------------------
// 用法:
//   1) 在路由器 Web 界面里,手动点到「上网设置 / WAN」那一页;
//   2) 打开浏览器控制台(F12 → Console / 控制台;Safari 是 开发 → 显示 Web 检查器);
//   3) 把本文件内容整段复制、粘贴进控制台、回车。
// 它会自动找出拨号方式控件,并**直接打印出该填进 profile 的那一行**。
// ============================================================================
(() => {
  const MODE = /(pppoe|dhcp|l2tp|pptp|ipv6|静态|动态|自动获取|static|dynamic|宽带拨号)/i;

  // 为一个元素生成一个"稳"的 CSS 选择器:优先 #id,其次 [name='..'],
  // 最后用一个不像随机哈希的 class。
  const cssFor = (el) => {
    if (el.id) return '#' + el.id;
    const name = el.getAttribute && el.getAttribute('name');
    if (name) return el.tagName.toLowerCase() + "[name='" + name + "']";
    const cls = (el.className || '').toString().trim().split(/\s+/)
      .filter(c => c && !/\d/.test(c))[0];          // 跳过含数字的哈希类名
    if (cls) return el.tagName.toLowerCase() + '.' + cls;
    return el.tagName.toLowerCase();
  };

  // 1) 首选:选项里含多个拨号方式的原生 <select>(常被"美化"插件隐藏)。
  let best = null, bestN = 0;
  document.querySelectorAll('select').forEach(s => {
    const n = [...s.options].filter(o => MODE.test(o.textContent || '')).length;
    if (n >= 2 && n > bestN) { best = s; bestN = n; }
  });
  if (best) {
    console.log('%c✓ 找到原生下拉(可能是隐藏的美化控件):', 'font-weight:bold');
    console.log('   选项:', [...best.options].map(o => o.textContent.trim()).join('  /  '));
    console.log('%c→ 把这一行填进 profile 的 selectors: 下面:', 'color:green;font-weight:bold');
    console.log('     dial_mode_select: "' + cssFor(best) + '"');
    return;
  }

  // 2) 没有原生 select → 找"显示着当前上网方式、且可见可点"的自定义控件。
  const cands = [...document.querySelectorAll('div,a,span,button')].filter(e => {
    const t = (e.innerText || '').trim();
    return MODE.test(t) && t.length < 16 && e.offsetParent !== null;
  });
  if (cands.length) {
    console.log('%c没有原生 select,疑似自定义 widget。候选如下', 'font-weight:bold');
    console.log('(挑那个"显示当前上网方式"的触发器):');
    cands.slice(0, 8).forEach(e =>
      console.log('   dial_mode_select: "' + cssFor(e) + '"   ← 显示: "'
        + (e.innerText || '').trim().slice(0, 16) + '"'));
    return;
  }

  console.log('没找到候选 —— 多半是没在正确的页面。先点到「上网设置 / WAN」页再运行。');
})();
