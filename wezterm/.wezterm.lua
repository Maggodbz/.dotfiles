local wezterm = require 'wezterm'

return {
  -- UI settings (optional tweaks)
  enable_wayland = false,
  enable_tab_bar = true,
  use_fancy_tab_bar = false,
  hide_tab_bar_if_only_one_tab = true,
  color_scheme = 'Red Planet',
  window_background_opacity = 0.8,
  -- front_end = "Software",

  keys = {
    -- 🔀 Split panes with Shift + Alt + Arrow
    {key="h",  mods="SUPER|SHIFT", action=wezterm.action.SplitHorizontal{domain="CurrentPaneDomain"}},
    {key="l", mods="SUPER|SHIFT", action=wezterm.action.SplitHorizontal{domain="CurrentPaneDomain"}},
    {key="k",    mods="SUPER|SHIFT", action=wezterm.action.SplitVertical{domain="CurrentPaneDomain"}},
    {key="j",  mods="SUPER|SHIFT", action=wezterm.action.SplitVertical{domain="CurrentPaneDomain"}},

    -- 🧭 Navigate with Super + Arrows
    {key="h",  mods="SUPER", action=wezterm.action.ActivatePaneDirection("Left")},
    {key="l", mods="SUPER", action=wezterm.action.ActivatePaneDirection("Right")},
    {key="k",    mods="SUPER", action=wezterm.action.ActivatePaneDirection("Up")},
    {key="j",  mods="SUPER", action=wezterm.action.ActivatePaneDirection("Down")},

    -- ❌ Close pane with Super + C
    {key="c", mods="SUPER", action=wezterm.action.CloseCurrentPane{confirm=true}},

    -- 🔍 Search with Alt + F
    {key="f", mods="SUPER", action=wezterm.action.Search{CaseInSensitiveString=""}},

    -- ➕ New tab with Alt + T
    {key="t", mods="SUPER", action=wezterm.action.SpawnTab("CurrentPaneDomain")},

    -- ❌ Close tab with Alt + C
    {key="x", mods="SUPER", action=wezterm.action.CloseCurrentTab{confirm=true}},

     -- 🧭 Move between tabs
    {key="n", mods="SUPER", action=wezterm.action.ActivateTabRelative(1)},   -- Alt+n → next tab
    {key="p", mods="SUPER", action=wezterm.action.ActivateTabRelative(-1)},  -- Alt+p → previous tab

    -- 🔢 Go to tab 1-3 directly
    {key="1", mods="SUPER", action=wezterm.action.ActivateTab(0)},
    {key="2", mods="SUPER", action=wezterm.action.ActivateTab(1)},
    {key="3", mods="SUPER", action=wezterm.action.ActivateTab(2)},
  },
}
