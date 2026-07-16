// ============================================================================
// 「使能开关」(enable_toggle)选择器查找器
// ----------------------------------------------------------------------------
// 适用场景:进了 IPv6 / 某功能页,页面上却什么设置都没有 —— 多半是整个区块要等
// 某个"总开关"打开才渲染(Tenda/TP-Link 的 IPv6 页都是这样)。把找到的开关
// pin 成 profile 的 selectors.enable_toggle,引擎会在找不到拨号控件时自动打开它
// (绝不会把已开启的开关点关)。
//
// 用法:
//   1) 在路由器 Web 界面里,手动点到那个"空空如也"的功能页(开关保持关闭);
//   2) 打开浏览器控制台(F12 → Console / 控制台);
//   3) 把本文件内容整段复制、粘贴进控制台、回车。
// 它会列出所有开关形态的元素、各自的开/关状态,并**直接打印出该填进 profile
// 的那一行**;命中数也当场验证(和老版 find_dial_selector.js 不同,不给没验证
// 过的选择器)。
//
// 注意:这里只能验证普通 CSS。若打印结果说"没有唯一 CSS",请改跑
//   python cli.py diagnose
// 它用 Playwright 引擎还能验证 :has-text() 这类 label 锚定写法,并直接进入
// 一键写入 profile 的流程。
// ============================================================================
(() => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const visible = el => !!(el.offsetParent || el.getClientRects().length);

  // 与 engine/diagnose.py 同一张网:checkbox / role / aria / 常见 class 片段
  const NET = "input[type=checkbox], [role=switch], [role=checkbox], " +
              "[aria-checked], [aria-pressed], [class*='switch'], " +
              "[class*='toggle'], [class*='slider'], [class*='onoff'], " +
              "[class*='enable']";

  const stateOf = el => {
    if (el.tagName.toLowerCase() === 'input') return !!el.checked;
    const ac = el.getAttribute('aria-checked') ?? el.getAttribute('aria-pressed');
    if (ac !== null) return ac === 'true';
    const toks = ((el.className || '') + '').toLowerCase().split(/[^a-z0-9]+/);
    if (['checked', 'on', 'active', 'open', 'enabled'].some(t => toks.includes(t)))
      return true;
    return null;   // 未知:引擎会当作"可能是关的"去点一次
  };

  const labelOf = el => {
    let p = el.parentElement;
    for (let i = 0; i < 3 && p; i++) {
      const t = norm(p.innerText);
      if (t && t.length < 30) return t;
      p = p.parentElement;
    }
    return '';
  };

  // 稳定优先的候选选择器;每个都当场 querySelectorAll 计数,只报唯一的。
  const uniqueCss = el => {
    const cands = [];
    if (el.id) cands.push('#' + CSS.escape(el.id));
    const name = el.getAttribute && el.getAttribute('name');
    if (name) cands.push(el.tagName.toLowerCase() + "[name='" + name + "']");
    const cls = (el.className || '').toString().trim().split(/\s+/)
      .filter(c => c && !/\d/.test(c));                 // 跳过含数字的哈希类名
    if (cls.length)
      cands.push(el.tagName.toLowerCase() + '.' + cls.map(CSS.escape).join('.'));
    for (const sel of cands) {
      try { if (document.querySelectorAll(sel).length === 1) return sel; }
      catch (e) { /* ignore bad selector */ }
    }
    return null;
  };

  const seen = new Set();
  const found = [];
  document.querySelectorAll(NET).forEach(el => {
    if (!visible(el) || seen.has(el)) return;
    seen.add(el);
    found.push({el, state: stateOf(el), label: labelOf(el), sel: uniqueCss(el)});
  });

  if (!found.length) {
    console.log('没找到开关形态的元素。可能:① 没在正确的页面;② 开关在 iframe 里' +
      '(控制台左上角把作用域切到对应 frame 再跑);③ 形态太特殊 —— 直接跑 ' +
      'python cli.py diagnose,它按 frame 全扫且能验证 Playwright 写法。');
    return;
  }

  console.log('%c找到 ' + found.length + ' 个开关形态的元素(关着的最可疑):',
              'font-weight:bold');
  found.sort((a, b) => (a.state === true) - (b.state === true));
  found.forEach(f => {
    const st = f.state === true ? '开' : (f.state === false ? '关' : '未知');
    if (f.sel) {
      console.log('  [' + st + '] label="' + f.label + '"');
      console.log('%c    → enable_toggle: "' + f.sel + '"',
                  'color:green;font-weight:bold');
    } else {
      console.log('  [' + st + '] label="' + f.label + '" —— 没有唯一 CSS;' +
        '改跑 python cli.py diagnose(能验证 :has-text() 的 label 锚定写法)');
    }
  });
  console.log('把绿色那行填进 profiles/<品牌>.yaml 的 selectors: 下面,' +
              '或直接重跑 python cli.py <mode>,失败时会进入一键写入流程。');
})();
