-- Varredura dos binds declarados na configuração Lua do Hyprland.
--
-- Mesma ideia do omarchy-menu-keybindings: carrega o hyprland.lua do usuário
-- com um `hl` de mentira que só anota as chamadas de bind/unbind, sem tocar
-- no compositor. Diferença: também registra o arquivo que fez a chamada, para
-- a coluna Origem. Saída em TSV, uma linha por chamada:
--   BIND\t<modmask>\t<tecla>\t<descrição>\t<tipo>\t<comando>\t<arquivo>
--   UNBIND\t<modmask>\t<tecla>\t<arquivo>
-- O caminho do hyprland.lua vem da variável de ambiente OMGR_HYPRLAND_LUA.

local modifiers = { SHIFT = 1, CTRL = 4, CONTROL = 4, ALT = 8, SUPER = 64, WIN = 64, LOGO = 64, MOD4 = 64 }

local function split_keys(keys)
  local modmask, key = 0, ""
  for part in string.gmatch(tostring(keys or ""), "[^+]+") do
    local value = part:gsub("^%s+", ""):gsub("%s+$", "")
    local modifier = modifiers[string.upper(value)]
    if modifier then
      modmask = modmask + modifier
    else
      key = value
    end
  end
  return modmask, key
end

local function clean(text)
  return (tostring(text or ""):gsub("[\t\n\r]", " "))
end

-- Primeiro arquivo da pilha que não é o helpers.lua nem este stub.
local stub_source = debug.getinfo(1, "S").source

local function caller_file()
  for level = 2, 24 do
    local info = debug.getinfo(level, "S")
    if not info then
      break
    end
    local src = info.source or ""
    if src ~= stub_source and src:sub(1, 1) == "@" then
      local path = src:sub(2)
      if not path:match("/default/hypr/helpers%.lua$") then
        return path
      end
    end
  end
  return ""
end

local function lua_literal(value)
  local t = type(value)
  if t == "string" then
    return string.format("%q", value)
  elseif t == "number" or t == "boolean" then
    return tostring(value)
  elseif t == "table" then
    local parts = {}
    for k, v in pairs(value) do
      parts[#parts + 1] = tostring(k) .. "=" .. lua_literal(v)
    end
    table.sort(parts)
    return "{" .. table.concat(parts, ",") .. "}"
  end
  return "nil"
end

local function dispatcher(kind, arg)
  return { __omgr = true, kind = kind, arg = arg }
end

local function dsp_proxy(path)
  return setmetatable({ path = path }, {
    __index = function(self, key)
      return dsp_proxy(self.path .. "." .. tostring(key))
    end,
    __call = function(self, ...)
      local first = ...
      local args = {}
      for i = 1, select("#", ...) do
        args[i] = lua_literal(select(i, ...))
      end
      local expr = self.path .. "(" .. table.concat(args, ", ") .. ")"
      if self.path == "hl.dsp.exec_cmd" and type(first) == "string" then
        return dispatcher("exec", first)
      end
      return dispatcher("lua", expr)
    end,
  })
end

local noop
noop = setmetatable({}, {
  __index = function(_, key)
    if type(key) == "number" and key ~= 1 and key ~= 0 then
      return nil
    end
    return noop
  end,
  __call = function() return noop end,
  __len = function() return 0 end,
  __lt = function() return false end,
  __le = function() return false end,
  __unm = function() return 0 end,
  __add = function() return 0 end,
  __sub = function() return 0 end,
  __mul = function() return 0 end,
  __div = function() return 0 end,
  __mod = function() return 0 end,
  __idiv = function() return 0 end,
  __pow = function() return 0 end,
  __concat = function(left, right)
    if rawequal(left, noop) then
      return tostring(right)
    end
    return tostring(left)
  end,
  __tostring = function() return "" end,
})

local raw_ipairs = ipairs
function ipairs(list)
  if rawequal(list, noop) then
    return function() end, list, 0
  end
  return raw_ipairs(list)
end

local function describe(bind_dispatcher)
  if type(bind_dispatcher) == "table" and bind_dispatcher.__omgr then
    return bind_dispatcher.kind, bind_dispatcher.arg
  elseif type(bind_dispatcher) == "string" then
    return "exec", bind_dispatcher
  elseif o and o.bind_commands and o.bind_commands[bind_dispatcher] then
    return "exec", o.bind_commands[bind_dispatcher]
  elseif o and o.bind_expressions and o.bind_expressions[bind_dispatcher] then
    return "lua", o.bind_expressions[bind_dispatcher]
  elseif type(bind_dispatcher) == "function" then
    return "function", ""
  end
  return "", ""
end

hl = setmetatable({
  dsp = dsp_proxy("hl.dsp"),
  bind = function(keys, bind_dispatcher, opts)
    opts = opts or {}
    local modmask, key = split_keys(keys)
    local kind, arg = describe(bind_dispatcher)
    io.write(table.concat({ "BIND", tostring(modmask), clean(key), clean(opts.description), kind, clean(arg), caller_file() }, "\t"), "\n")
    return noop
  end,
  unbind = function(keys)
    local modmask, key = split_keys(keys)
    io.write(table.concat({ "UNBIND", tostring(modmask), clean(key), caller_file() }, "\t"), "\n")
    return noop
  end,
  get_config = function() return nil end,
}, {
  __index = function() return noop end,
})

local config = os.getenv("OMGR_HYPRLAND_LUA")
if config and config ~= "" then
  debug.sethook(function()
    error("limite de instruções excedido")
  end, "", 50000000)
  local ok, err = pcall(dofile, config)
  debug.sethook()
  if not ok then
    io.stderr:write("omgr lua scan: " .. tostring(err) .. "\n")
    os.exit(3)
  end
end
