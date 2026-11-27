/*!
 * IIOT-PRD Renderer · 渲染层
 * 目标：用 Vue 3 渲染函数 API 写组件（h(type, props, children) + setup 返回 render），
 *      在离线单文件里跑起来；一旦 window.Vue 存在（内联真 Vue 或同目录放 vue.global.prod.js），
 *      本文件整体退化为空壳，组件零改动切到真 Vue。
 *
 * 与真 Vue 的差异（必须知道，避免写成依赖响应式的东西）：
 *   1. 无响应式依赖收集：状态改动后显式调用 app.render()；
 *   2. 列表按 key 做最简复用，不做最长递增子序列；
 *   3. 同一时刻焦点元素上的 value/checked 不覆写，避免输入时跳光标；
 *   4. 只实现本项目用到的 props：class/style/事件/disabled/value/checked/data-*。
 */
(function () {
  if (window.Vue && window.Vue.h && window.Vue.createApp) {
    window.__RUNTIME__ = 'vue';
    return;
  }
  window.__RUNTIME__ = 'shim';

  var TEXT = Symbol ? Symbol('text') : '__text__';

  function isVNode(v) {
    return v && typeof v === 'object' && 'type' in v;
  }

  function flatten(children, out) {
    out = out || [];
    for (var i = 0; i < children.length; i++) {
      var c = children[i];
      if (c == null || c === false || c === true) continue;
      if (Array.isArray(c)) flatten(c, out);
      else if (isVNode(c)) out.push(c);
      else out.push({ type: TEXT, props: {}, children: [], text: String(c) });
    }
    return out;
  }

  function h(type, props, children) {
    if (arguments.length === 2) {
      if (Array.isArray(props) || typeof props === 'string' || typeof props === 'number') {
        children = props;
        props = null;
      }
    }
    var kids = [];
    if (children != null) {
      kids = Array.isArray(children) ? flatten(children) : flatten([children]);
    }
    return { type: type, props: props || {}, children: kids, key: props && props.key != null ? props.key : null };
  }

  function setStyle(el, style) {
    if (!style) return;
    if (typeof style === 'string') {
      el.setAttribute('style', style);
      return;
    }
    for (var k in style) {
      if (!Object.prototype.hasOwnProperty.call(style, k)) continue;
      var v = style[k];
      if (v == null || v === false) continue;
      if (k.indexOf('--') === 0) el.style.setProperty(k, v);
      else el.style[k] = typeof v === 'number' && !/^(zIndex|opacity|flex|order|lineHeight)$/.test(k) ? v + 'px' : v;
    }
  }

  function patchProps(el, oldP, newP) {
    oldP = oldP || {};
    newP = newP || {};
    var k;
    for (k in oldP) {
      if (!Object.prototype.hasOwnProperty.call(oldP, k)) continue;
      if (k in newP) continue;
      if (k === 'class' || k === 'style' || k === 'key') continue;
      if (/^on[A-Z]/.test(k)) {
        el.removeEventListener(k.slice(2).toLowerCase(), oldP[k]);
      } else {
        el.removeAttribute(k);
      }
    }
    for (k in newP) {
      if (!Object.prototype.hasOwnProperty.call(newP, k)) continue;
      var v = newP[k], ov = oldP[k];
      if (k === 'key') continue;
      if (k === 'class') {
        var cls = Array.isArray(v) ? v.filter(Boolean).join(' ') : v;
        if (cls) el.setAttribute('class', cls);
        else el.removeAttribute('class');
        continue;
      }
      if (k === 'style') {
        if (v !== ov) { el.removeAttribute('style'); setStyle(el, v); }
        continue;
      }
      if (/^on[A-Z]/.test(k)) {
        var evt = k.slice(2).toLowerCase();
        if (ov !== v) {
          if (ov) el.removeEventListener(evt, ov);
          if (v) el.addEventListener(evt, v);
        }
        continue;
      }
      if (v === ov) continue;
      if (v == null || v === false) { el.removeAttribute(k); continue; }
      if (k === 'value') {
        if (el === document.activeElement) continue;
        el.value = v;
        el.setAttribute('value', v);
        continue;
      }
      if (k === 'checked') {
        if (el === document.activeElement && el.checked === v) continue;
        el.checked = !!v;
        continue;
      }
      el.setAttribute(k, v === true ? '' : v);
    }
  }

  function mountChildren(el, vnodes, oldVnodes) {
    oldVnodes = oldVnodes || [];
    var oldNodes = Array.prototype.slice.call(el.childNodes);
    var oldByKey = {};
    for (var i = 0; i < oldVnodes.length; i++) {
      if (oldVnodes[i].key != null) oldByKey[oldVnodes[i].key] = i;
    }
    var next = [];
    for (var j = 0; j < vnodes.length; j++) {
      var v = vnodes[j];
      var node = null;
      if (v.key != null && oldByKey[v.key] != null) {
        var oi = oldByKey[v.key];
        node = oldNodes[oi];
        if (node) node = patchNode(node, oldVnodes[oi], v);
      }
      if (!node) node = createNode(v);
      next.push(node);
    }
    for (var k = 0; k < next.length; k++) {
      if (el.childNodes[k] !== next[k]) el.insertBefore(next[k], el.childNodes[k] || null);
    }
    while (el.childNodes.length > next.length) el.removeChild(el.lastChild);
    return next;
  }

  function resolveComponent(c, props, instance) {
    var propsDef = c.props || {};
    var resolved = {};
    for (var p in propsDef) resolved[p] = props[p] !== undefined ? props[p] : propsDef[p];
    for (var q in props) if (!(q in resolved)) resolved[q] = props[q];
    var ctx = {
      attrs: props,
      emit: function () {},
      slots: {},
      expose: function () {}
    };
    var render = null;
    if (typeof c.setup === 'function') {
      var ret = c.setup(resolved, ctx);
      if (typeof ret === 'function') render = ret;
      else if (ret && typeof ret.render === 'function') render = ret.render;
      else if (typeof c.render === 'function') render = c.render;
    } else if (typeof c.render === 'function') {
      render = c.render;
    }
    if (!render) return h('span', null, ['[组件 ' + (c.name || '匿名') + ' 无可渲染内容]']);
    var out = render.call(instance || null, h);
    out = out || { type: 'span', props: {}, children: [] };
    out.__comp = c;
    return out;
  }

  function createNode(v) {
    if (v.type === TEXT) {
      return document.createTextNode(v.text != null ? v.text : '');
    }
    if (typeof v.type === 'object' && v.type !== null) {
      var inner = resolveComponent(v.type, v.props, v.instance);
      var host = document.createElement('div');
      host.className = 'cmp-host';
      host.style.display = 'contents';
      var real = createNode(inner);
      host.appendChild(real);
      return host;
    }
    if (typeof v.type === 'function') {
      var produced = v.type(v.props || {}, h);
      return createNode(Array.isArray(produced) ? h('div', null, produced) : produced);
    }
    var el = document.createElement(v.type || 'div');
    patchProps(el, null, v.props);
    var kids = v.children || [];
    for (var i = 0; i < kids.length; i++) el.appendChild(createNode(kids[i]));
    return el;
  }

  function patchNode(el, oldV, newV) {
    if (!oldV || (oldV.type !== newV.type)) {
      var fresh = createNode(newV);
      if (el.parentNode) el.parentNode.replaceChild(fresh, el);
      return fresh;
    }
    if (newV.type === TEXT) {
      if (el.nodeValue !== newV.text) el.nodeValue = newV.text;
      return el;
    }
    if (typeof newV.type === 'object') {
      var innerNew = resolveComponent(newV.type, newV.props, newV.instance);
      var real = el.firstChild;
      if (real) {
        var swapped = patchNode(real, oldV.__inner || null, innerNew);
        if (swapped !== real) { el.replaceChild(swapped, real); }
      }
      newV.__inner = innerNew;
      return el;
    }
    patchProps(el, oldV.props, newV.props);
    mountChildren(el, newV.children || [], oldV.children || []);
    return el;
  }

  function createApp(rootComponent) {
    var app = {
      _root: rootComponent,
      _el: null,
      _vnode: null,
      mount: function (selector) {
        var host = typeof selector === 'string' ? document.querySelector(selector) : selector;
        this._el = host;
        var vnode = isVNode(rootComponent) ? rootComponent : resolveComponent(rootComponent, {}, null);
        this._vnode = vnode;
        var dom = createNode(vnode);
        host.innerHTML = '';
        host.appendChild(dom);
        return this;
      },
      render: function () {
        if (!this._el) return this;
        var next = resolveComponent(this._root, {}, null);
        var dom = patchNode(this._el.firstChild, this._vnode, next);
        if (dom !== this._el.firstChild) {
          this._el.innerHTML = '';
          this._el.appendChild(dom);
        }
        this._vnode = next;
        return this;
      }
    };
    return app;
  }

  window.MiniVue = { h: h, createApp: createApp, version: 'shim-1.0' };
  window.h = h;
})();
