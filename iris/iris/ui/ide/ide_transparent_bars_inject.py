"""Theia Activity Bar 투명화 — CSS + DOM 직접 조작 스크립트."""

from __future__ import annotations

import json
from pathlib import Path

_CSS_CANDIDATES = (
  Path(__file__).resolve().parents[4]
  / "iris-ide"
  / "theia-extensions"
  / "iris-product"
  / "src"
  / "browser"
  / "iris-transparent-shell.css",
)

# Theia/Lumino 레이아웃·Activity Bar 변수 — rgba(0,0,0,0)로 완전 투명
_TRANSPARENT_CSS_VARS = (
  "--theia-activityBar-background",
  "--theia-activityBar-border",
  "--theia-activityBar-activeBackground",
  "--theia-activityBar-inactiveBackground",
  "--theia-layout-color0",
  "--theia-layout-color1",
  "--theia-layout-color2",
  "--theia-layout-color3",
  "--theia-layout-color4",
)

_SIDE_PANEL_SELECTORS = (
  "#theia-left-side-panel",
  "#theia-right-side-panel",
)

# 아이콘 마스크·glyph — 배경 투명화 대상에서 제외
_ICON_SKIP_SELECTOR = (
  ".p-TabBar-tabIcon, .codicon, .fa, .file-icon, img, svg, .theia-icon"
)


def load_iris_shell_css() -> str:
  for path in _CSS_CANDIDATES:
    try:
      return path.read_text(encoding="utf-8")
    except OSError:
      continue
  return ""


def build_transparency_inject_script(css: str) -> str:
  """CSS 주입 + CSS 변수·DOM 인라인 스타일 강제 적용."""
  css_json = json.dumps(css)
  vars_json = json.dumps(list(_TRANSPARENT_CSS_VARS))
  panels_json = json.dumps(list(_SIDE_PANEL_SELECTORS))
  icon_skip_json = json.dumps(_ICON_SKIP_SELECTOR)
  return f"""
(function() {{
  var cssText = {css_json};
  var styleId = 'iris-transparent-shell-runtime';
  var styleNode = document.getElementById(styleId);
  if (!styleNode) {{
    styleNode = document.createElement('style');
    styleNode.id = styleId;
    document.head.appendChild(styleNode);
  }}
  if (cssText) {{
    styleNode.textContent = cssText;
  }}

  var ICON_SKIP = {icon_skip_json};

  function isIconNode(node) {{
    if (!node || node.nodeType !== 1) return false;
    if (node.matches(ICON_SKIP)) return true;
    if (node.closest('.p-TabBar-tabIcon')) return true;
    return false;
  }}

  function forceTransparent(el) {{
    if (!el || isIconNode(el)) return;
    el.style.setProperty('background', 'rgba(0,0,0,0)', 'important');
    el.style.setProperty('background-color', 'rgba(0,0,0,0)', 'important');
    el.style.setProperty('background-image', 'none', 'important');
    el.style.setProperty('border-color', 'rgba(0,0,0,0)', 'important');
    el.style.setProperty('box-shadow', 'none', 'important');
  }}

  function restoreSideIcons(panel) {{
    if (!panel) return;
    panel.querySelectorAll('.p-TabBar-tabIcon:not(.codicon):not(.fa)').forEach(function(icon) {{
      icon.style.setProperty('opacity', '0.88', 'important');
      icon.style.setProperty('background-color', '#94a3b8', 'important');
    }});
    panel.querySelectorAll('.codicon.p-TabBar-tabIcon, .fa.p-TabBar-tabIcon').forEach(function(icon) {{
      icon.style.setProperty('opacity', '0.88', 'important');
      icon.style.setProperty('color', '#94a3b8', 'important');
      icon.style.setProperty('background', 'none', 'important');
      icon.style.setProperty('background-color', 'transparent', 'important');
      icon.style.setProperty('-webkit-mask-image', 'none', 'important');
      icon.style.setProperty('mask-image', 'none', 'important');
    }});
    panel.querySelectorAll('.p-TabBar-tab.p-mod-current .p-TabBar-tabIcon:not(.codicon):not(.fa)').forEach(function(icon) {{
      icon.style.setProperty('opacity', '1', 'important');
      icon.style.setProperty('background-color', '#e8f0fe', 'important');
    }});
    panel.querySelectorAll('.p-TabBar-tab.p-mod-current .codicon.p-TabBar-tabIcon, .p-TabBar-tab.p-mod-current .fa.p-TabBar-tabIcon').forEach(function(icon) {{
      icon.style.setProperty('opacity', '1', 'important');
      icon.style.setProperty('color', '#e8f0fe', 'important');
      icon.style.setProperty('background', 'none', 'important');
      icon.style.setProperty('background-color', 'transparent', 'important');
    }});
  }}

  function transparentizeSidePanel(selector) {{
    var panel = document.querySelector(selector);
    if (!panel) return;
    forceTransparent(panel);
    panel.querySelectorAll('*').forEach(function(node) {{
      if (isIconNode(node)) return;
      if (node.classList.contains('p-TabBar-tabLabel')) return;
      forceTransparent(node);
    }});
    restoreSideIcons(panel);
  }}

  function applyIrisTransparentBars() {{
    var root = document.documentElement;
    {vars_json}.forEach(function(name) {{
      root.style.setProperty(name, 'rgba(0,0,0,0)');
      if (document.body) {{
        document.body.style.setProperty(name, 'rgba(0,0,0,0)');
      }}
    }});

    {panels_json}.forEach(function(selector) {{
      transparentizeSidePanel(selector);
    }});

    document.querySelectorAll('.p-TabBar.theia-app-sides, .p-TabBar.theia-app-left, .p-TabBar.theia-app-right').forEach(function(bar) {{
      forceTransparent(bar);
      bar.querySelectorAll('.p-TabBar-content, .p-TabBar-tab').forEach(function(tab) {{
        if (!isIconNode(tab)) forceTransparent(tab);
      }});
    }});
  }}

  applyIrisTransparentBars();

  if (!window.__irisTransparentBarsObserver) {{
    var pending = null;
    var schedule = function() {{
      if (pending) return;
      pending = window.setTimeout(function() {{
        pending = null;
        applyIrisTransparentBars();
      }}, 80);
    }};
    window.__irisTransparentBarsObserver = new MutationObserver(schedule);
    if (document.body) {{
      window.__irisTransparentBarsObserver.observe(document.body, {{
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['style', 'class']
      }});
    }}
  }}
}})();
"""
