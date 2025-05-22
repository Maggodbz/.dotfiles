-- Set <leader> key to space
vim.g.mapleader = " "

-- Leader key
vim.g.mapleader = " "

-- Line Numbers
vim.opt.number = true              -- Show absolute line numbers
vim.opt.relativenumber = true     -- Show relative line numbers

-- Tabs & Indentation
vim.opt.tabstop = 4               -- Number of spaces per <Tab>
vim.opt.shiftwidth = 4           -- Number of spaces for autoindent
vim.opt.expandtab = true         -- Convert tabs to spaces
vim.opt.smartindent = true       -- Smart autoindenting on new lines

-- UI Enhancements
vim.opt.cursorline = true        -- Highlight current line
vim.opt.wrap = false             -- Disable line wrap
vim.opt.termguicolors = true     -- Enable full-color support
vim.opt.signcolumn = "yes"       -- Always show sign column (LSP, git, etc.)

-- Search
vim.opt.ignorecase = true        -- Case-insensitive by default
vim.opt.smartcase = true         -- Case-sensitive if uppercase present
vim.opt.hlsearch = true          -- Highlight matches
vim.opt.incsearch = true         -- Show matches while typing

-- Performance
vim.opt.updatetime = 300         -- Faster completion
vim.opt.timeoutlen = 500         -- Shorter key timeout

-- Clipboard
vim.opt.clipboard = "unnamedplus" -- Use system clipboard (works for X11/mac/WSL)

-- Split behavior
vim.opt.splitright = true        -- Vertical splits open to the right
vim.opt.splitbelow = true        -- Horizontal splits open below

-- Mouse
vim.opt.mouse = "a"              -- Enable mouse support in all modes

-- Undo
vim.opt.undofile = true          -- Persistent undo

-- Copy yanked text to system clipboard using wl-copy (Wayland)
vim.api.nvim_create_autocmd("TextYankPost", {
  pattern = "*",
  callback = function()
    vim.fn.system("wl-copy", vim.fn.getreg('"'))
  end,
})

-- Bootstrap lazy.nvim
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    "git", "clone", "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git", lazypath
  })
end
vim.opt.rtp:prepend(lazypath)

-- Plugin configuration helper functions

-- Treesitter
local function setup_treesitter()
  require("nvim-treesitter.configs").setup({
    ensure_installed = { "lua", "python", "bash", "javascript", "json", "yaml" },
    highlight = { enable = true },
  })
end

-- Colorscheme
local function setup_colorscheme()
  require("vscode_modern").setup({
    cursorline = true,
    transparent_background = false,
    nvim_tree_darker = true,
  })
  vim.cmd("colorscheme vscode_modern")
end

-- NvimTree
local function setup_nvim_tree()
  require("nvim-tree").setup()
  vim.keymap.set("n", "<leader>e", ":NvimTreeToggle<CR>", { noremap = true, silent = true })
end

-- Telescope
local function setup_telescope()
  local telescope = require("telescope")
  telescope.setup()
  local builtin = require("telescope.builtin")
  local map = vim.keymap.set
  map("n", "<leader>ff", builtin.find_files, {})
  map("n", "<leader>fg", builtin.live_grep, {})
  map("n", "<leader>fb", builtin.buffers, {})
  map("n", "<leader>fh", builtin.help_tags, {})
end

-- LSP Configs
local function setup_lsp()
  local lspconfig = require("lspconfig")

  local servers = {
    pyright = {},
    bashls = {},
    tsserver = {
      cmd = { "typescript-language-server", "--stdio" },
    },
    lua_ls = {
      settings = {
        Lua = {
          diagnostics = { globals = { "vim" } },
        },
      },
    },
  }

  for server, config in pairs(servers) do
    lspconfig[server].setup(config)
  end
end

-- Autocompletion
local function setup_cmp()
  local cmp = require("cmp")
  cmp.setup({
    mapping = cmp.mapping.preset.insert({
      ["<Tab>"] = cmp.mapping.select_next_item(),
      ["<S-Tab>"] = cmp.mapping.select_prev_item(),
      ["<CR>"] = cmp.mapping.confirm({ select = true }),
    }),
    sources = {
      { name = "nvim_lsp" },
    },
  })
end

-- DAP (Debug Adapter Protocol)
local function setup_dap()
  local dap = require("dap")

  -- Python adapter
  dap.adapters.python = {
    type = "executable",
    command = "python",
    args = { "-m", "debugpy.adapter" },
  }

  dap.configurations.python = {
    {
      type = "python",
      request = "launch",
      name = "Launch file",
      program = "${file}",
      pythonPath = function()
        return "python"
      end,
    },
  }

  -- Add other language configs here if needed
end

-- DAP UI
local function setup_dap_ui()
  local dap, dapui = require("dap"), require("dapui")
  dapui.setup()

  dap.listeners.after.event_initialized["dapui_config"] = function()
    dapui.open()
  end
  dap.listeners.before.event_terminated["dapui_config"] = function()
    dapui.close()
  end
  dap.listeners.before.event_exited["dapui_config"] = function()
    dapui.close()
  end
end

-- DAP Keymaps
local function setup_dap_keymaps()
  local dap = require("dap")
  local map = vim.keymap.set
  map("n", "<F5>", dap.continue)
  map("n", "<F10>", dap.step_over)
  map("n", "<F11>", dap.step_into)
  map("n", "<F12>", dap.step_out)
  map("n", "<Leader>b", dap.toggle_breakpoint)
  map("n", "<Leader>B", function()
    dap.set_breakpoint(vim.fn.input("Breakpoint condition: "))
  end)
end

-- Plugin list
require("lazy").setup({
  -- Syntax & UI
  {
    "nvim-treesitter/nvim-treesitter",
    build = ":TSUpdate",
    config = setup_treesitter,
  },
  {
    "gmr458/vscode_modern_theme.nvim",
    lazy = false,
    priority = 1000,
    config = setup_colorscheme,
  },
  {
    "nvim-tree/nvim-tree.lua",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = setup_nvim_tree,
  },
  {
    "nvim-telescope/telescope.nvim",
    dependencies = { "nvim-lua/plenary.nvim" },
    config = setup_telescope,
  },

  -- LSP & Completion
  {
    "neovim/nvim-lspconfig",
    config = setup_lsp,
  },
  {
    "hrsh7th/nvim-cmp",
    dependencies = {
      "hrsh7th/cmp-nvim-lsp",
      "L3MON4D3/LuaSnip",
    },
    config = setup_cmp,
  },

  -- Debugging
  {
    "mfussenegger/nvim-dap",
    config = function()
      setup_dap()
      setup_dap_keymaps()
    end,
  },
  {
    "rcarriga/nvim-dap-ui",
    dependencies = {
      "mfussenegger/nvim-dap",
      "nvim-neotest/nvim-nio", -- 🔧 REQUIRED fix
    },
    config = setup_dap_ui,
  },
  {
    "theHamsta/nvim-dap-virtual-text",
    config = function()
      require("nvim-dap-virtual-text").setup()
    end,
  },
})