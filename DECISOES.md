# Decisões técnicas, omarchy-manager

Registro das provas da Fase 0 (plano, seção 13) e das decisões que elas
sustentam. Data da rodada: 2026-11-13, nesta máquina (Omarchy, Hyprland 0.56.2,
Foot 1.28.0, Herdr 0.9.5, Python 3.13.18 em venv, Textual 8.2.8).

Os scripts das provas ficam em `docs/provas/`. Tudo o que está marcado como
"requer validação manual do JC" não foi testado com uma pessoa no teclado e
não deve ser lido como validado.

## 1. Captura de combinações com Super (plano 6.3)

### O que foi verificado

1. O Hyprland do Omarchy usa configuração em Lua. `hyprctl keyword` responde
   `keyword can't work with non-legacy parsers. Use eval.` Portanto a via
   clássica de criar submap e binds em tempo de execução por `keyword` não
   existe aqui.
2. `hyprctl eval '<lua>'` executa Lua dentro do compositor. A API `hl`
   expõe, entre outros: `bind`, `unbind`, `define_submap`, `dsp.submap`,
   `get_current_submap`, `on`, `is_key_down`, `dispatch`, `exec_cmd`.
3. `hl.bind("SUPER + CTRL + ALT + SHIFT + F24", hl.dsp.exec_cmd("true"), {description=...})`
   via `hyprctl eval` criou um bind visível em `hyprctl binds -j` na hora, e
   `hl.unbind(...)` o removeu. A opção `submap` dentro da tabela de opções
   foi ignorada (o bind ficou no submap raiz); submaps são criados por
   `hl.define_submap(nome, function() ... end)` (assinatura confirmada:
   o 2º argumento tem de ser função).
4. `hl.on("input.keyboard.key", fn)` existe e dispara a cada tecla. Com um
   `wtype -k F24` sintético o handler recebeu 3 números `(a, b, estado)`;
   `estado` é 1 no press e 0 no release, `a` veio 9 tanto para F24 quanto
   para Shift+F23, então esse argumento não identifica a tecla de forma
   útil sem mais investigação. O handler devolver `true` não impediu nada
   de observável. A assinatura é `HL.EventSubscription` com métodos
   `remove()` e `is_active()`; `unsubscribe` não existe (um hook de prova
   ficou vivo até um `hyprctl reload`, que o removeu; `configerrors` ficou
   vazio e os 254 binds voltaram iguais).
5. Precedente no próprio Omarchy: `default/hypr/bindings/utilities.lua`
   cria binds temporários com `hl.bind` e os liga/desliga com
   `set_enabled`, e avisa que `hl.unbind(chord)` remove TODOS os binds
   daquele chord, inclusive os do usuário.
6. O Textual 8 fala o protocolo de teclado do kitty (há
   `_keyboard_protocol.py` e o parser reconhece o modificador `super`).
   Isso só vale para teclas que chegam ao terminal, ou seja, que o Hyprland
   não consumiu antes.

### Decisão

Solução 1 do plano (submap temporário) é a escolhida, com esta forma:

- a TUI pede, por `hyprctl eval`, um `hl.define_submap("omarchy-manager-capture", ...)`
  com um bind por tecla de uma lista conhecida (letras, dígitos, F1-F24,
  teclas de navegação, `code:NN` do ABNT2 e teclas XF86 multimídia) e a
  opção de ignorar modificadores, cujo handler Lua lê o estado de Super,
  Ctrl, Alt e Shift com `hl.is_key_down` e grava `modmask<TAB>tecla` em um
  arquivo de troca dentro de `$XDG_RUNTIME_DIR`;
- `Esc` tem bind próprio que só volta ao submap raiz;
- a TUI entra no submap com `hl.dispatch("submap", ...)`, espera o arquivo,
  e sempre sai com `hl.dsp.submap("reset")` em `finally`, inclusive por
  timeout de 15 s;
- nenhum bind do usuário é removido: o submap é separado e o retorno ao
  submap raiz restaura tudo.

Motivo: usa só API já confirmada por prova (`define_submap`, `bind`,
`dispatch`, `is_key_down`) e tem precedente de uso pelo próprio Omarchy;
não depende de protocolo Wayland de inibição, que o Foot e o Herdr não
pedem por conta própria e exigiria um cliente gráfico extra.

A solução 2 (capturador Wayland com inibição de atalhos) fica como
alternativa documentada caso o submap falhe em alguma tecla. Não foi
prototipada.

**Requer validação manual do JC:** pressionar `Super + tecla` dentro do
capturador, no Foot e no Herdr, e confirmar que a ação antiga não dispara,
que `Esc` cancela e que `<`, `>`, `ç`, acentos, F-keys e teclas de mídia
são reconhecidos. Nada disso foi testado com uma pessoa no teclado. O
`is_key_down("SUPER_L")` deu `Unknown keysym`; o nome correto do keysym
(`Super_L`) ainda precisa ser confirmado nessa validação.

## 2. Hover e clique no terminal (plano, Fase 0)

Prova `docs/provas/prova_hover_clique.py`, headless com o Pilot do Textual:

- hover sobre um `Button` liga `mouse_hover` e expõe o `tooltip`: OK;
- clique no botão dispara `Button.Pressed` (1 clique = 1 evento): OK;
- clique em uma linha da `DataTable` move o cursor e dispara
  `RowHighlighted`; `RowSelected` só vem com Enter ou segundo clique na
  mesma linha. A interface usa `RowHighlighted` para selecionar e Enter
  para ativar.

**Requer validação manual do JC:** a entrega real dos eventos de mouse
pelo Foot e pelo Herdr (ambos suportam SGR mouse, mas não foi testado ao
vivo nesta sessão). O terminal desta sessão reportou `TERM_PROGRAM=herdr`.

## 3. Prévia de imagem com Sixel e fallback (plano 8.1)

- `chafa` não está instalado.
- `img2sixel` (libsixel 1.10.5) devolve 0 bytes e código 0 para o PNG do
  fundo atual, tanto por caminho quanto por stdin, inclusive com PPM na
  entrada. Não serve como gerador confiável aqui.
- `magick <png> -resize 200x sixel:-` gerou 27.214 bytes começando com
  `ESC P 0;1;0 q`, Sixel válido.
- Fallback: `magick <png> -resize 40x20! -depth 8 ppm:-` gera um P6 de
  2.413 bytes que um parser de 10 linhas em Python puro converte em
  blocos `▀` com cor 24 bits, sem PIL.

Decisão: `ThemePreview` tenta, nesta ordem, `chafa` (se existir), `magick
... sixel:-` e o fallback por PPM em blocos. O Sixel só é emitido quando o
terminal se declara capaz (consulta DA1 ou `TERM_PROGRAM`/`TERM` em
`foot`); dentro da área do Textual a prévia padrão é a de blocos, porque o
Textual redesenha células e corromperia uma imagem Sixel sobreposta. O
Sixel fica para um modo "ver em tamanho maior" que suspende a TUI.

**Requer validação manual do JC:** ver a imagem Sixel no Foot (suporta) e
no Herdr (não confirmado).

## 4. Troca dinâmica de cores (plano, seção 5)

Prova `docs/provas/prova_cores_dinamicas.py`: dois `Theme` do Textual
construídos a partir de dicionários no formato do `colors.toml`,
registrados com `App.register_theme` e trocados com `app.theme = nome` com
a aplicação aberta. `background` e `foreground` mudaram de `#1A1B26` /
`#A9B1D6` para `#eff1f5` / `#4C4F69`. OK.

Decisão: `services/paleta.py` lê `~/.local/state/omarchy/current/theme/colors.toml`
(o mesmo caminho que `omarchy theme set` mantém), aplica fallback ANSI
por chave ausente e registra o tema no Textual; a aplicação relê a paleta
ao abrir, em `F5` e depois de aplicar um tema.

## 5. mDNS, código de confirmação e HTTPS entre 2 máquinas (plano, seção 10)

Não executado. Há 1 máquina nesta sessão. **Requer validação manual do JC
com 2 computadores no mesmo Wi-Fi.** A Fase 6 fica depois das Fases 1 a 4.

## 6. Outras descobertas que mudaram o desenho

1. `hyprctl binds -j` reporta todo bind Lua como `dispatcher: "__lua"` e
   `arg: "<número>"`. O comando real não está lá. O próprio Omarchy
   (`omarchy-menu-keybindings`) resolve isso rodando o `hyprland.lua` do
   usuário em um `lua -E` com um stub de `hl`, só para coletar os binds.
   O gerenciador faz o mesmo, em `services/lua_scan.py`, e aproveita para
   registrar o arquivo de origem de cada bind (`debug.getinfo`), que é o
   que preenche a coluna Origem (`Omarchy`, `usuário`, `plugin`,
   `gerenciador`).
2. `omarchy theme list` devolve nomes de exibição ("Tokyo Night");
   `omarchy theme dir` e `omarchy theme set` querem o slug ("tokyo-night").
   O slug atual está em `~/.local/state/omarchy/current/theme.name`. O
   gerenciador resolve slug a partir dos diretórios reais e usa o nome de
   exibição só para mostrar.
3. Plugins de terceiros moram em `~/.config/omarchy/plugins/<id>`; os
   nativos em `$OMARCHY_PATH/shell/plugins/<pasta>` com pasta diferente do
   id (`clipboard` -> `omarchy.clipboard`). A lista JSON não traz o caminho,
   então o catálogo indexa os `manifest.json` dos dois lugares por `id`.
4. Hyprland 0.56.0 emitiu JSON inválido em `binds -j` (nota no script do
   Omarchy). `HyprlandService` tem fallback para a saída textual.
5. Correção: na primeira rodada anotei que `python-textual` e `python-pytest`
   não existiam nos repositórios, mas o comando usado (`pacman -Q`) só olha
   o que está instalado. `pacman -Ss` mostra `extra/python-textual 8.2.8-2`,
   `extra/python-rich`, `extra/python-pytest` e os `python-build`,
   `python-installer`, `python-hatchling`. O venv com `uv` continua sendo o
   ambiente de desenvolvimento; o pacote usa só dependências oficiais (seção 8).

## 7. IA para temas (plano, seção 9 e Fase 5)

Conferido no `--help` de cada CLI instalada em 2026-11-13:

| CLI | Como recebe o agente | Prompt inicial |
|---|---|---|
| `claude` | `--append-system-prompt-file AGENTE-CRIADOR-DE-TEMAS.md` e `CLAUDE.md` no diretório | argumento posicional |
| `codex` | `AGENTS.md` no diretório | argumento posicional `[PROMPT]` |
| `opencode` | `AGENTS.md` no diretório | `--prompt <texto>` |
| `copilot` | `AGENTS.md` no diretório | nenhum: `-p/--prompt` é só modo não interativo |

Terminal: `omarchy-launch-terminal` usa `xdg-terminal-exec --dir=<pasta>`
(`$TERMINAL=xdg-terminal-exec` nesta máquina), então esse é o adaptador
preferido; `foot`, `alacritty`, `ghostty`, `kitty` e `wezterm` são
alternativas, cada um com a própria lista de argumentos. Nenhum comando é
montado por concatenação.

Decisões:

- o workspace é `~/.local/share/omarchy-manager/theme-workspaces/<slug>/`,
  com o agente copiado duas vezes (nome neutro e nome que cada IA lê
  sozinha) e, se escolhido, o tema base copiado para `base/<slug>/` sem
  `.git`;
- o diálogo recusa abrir sem IA instalada ou sem terminal e explica o que
  falta;
- o agente instrui a só copiar para `~/.config/omarchy/themes/` após um
  "sim" explícito; o gerenciador não importa o tema sozinho (a importação
  pós-chat fica para depois: o usuário usa `Atualizar` na aba Temas).

**Requer validação manual do JC:** abrir cada adaptador de verdade e ver se
o prompt inicial chega como esperado (os testes usam executáveis falsos).

## 9. Compartilhamento na rede local (plano, seção 10 e Fase 6)

Implementado e testado em 1 máquina, com os 2 lados no loopback
(`tests/integration/test_lan_loopback.py`):

- pacote `.omarchy-bundle` (tar.gz com `bundle.json`, `payload/`,
  `checksums.sha256`), exclusão de `.git`, credenciais (`*.pem`, `*.key`,
  `.env`, `*token*`, `*secret*`…), caches, logs, backups e links para fora
  do projeto; limites de 500 MiB, 10.000 arquivos e 256 MiB por arquivo;
- validação do pacote: hash SHA-256 do arquivo, caminho absoluto, `..`,
  entrada que não é arquivo regular (link, dispositivo), lista do
  `bundle.json` divergente do conteúdo, checksum e tamanho por arquivo;
  tudo com teste de rejeição;
- certificado autoassinado de 1 dia gerado por `openssl` (chave EC P-256),
  TLS 1.3, fingerprint SHA-256 do certificado;
- código de confirmação de 6 palavras (48 bits) derivado por HMAC da
  fingerprint e do segredo: os 2 lados calculam o mesmo valor;
- o cliente conecta com `CERT_NONE` e fixa a fingerprint do certificado
  recebido antes de enviar o segredo (`Bearer`); fingerprint errada recusa
  sem vazar o segredo; segredo errado recebe 403;
- 1 download ou 10 minutos; depois 410; `encerrar()` apaga o segredo, o
  certificado e o pacote temporário;
- importação: plugin extraído em temporário, mostrado com manifesto e lista
  de executáveis, copiado para `~/.config/omarchy/plugins/<id>` só após
  confirmação e NUNCA ligado (não existe chamada a `plugin enable` nesse
  caminho); tema vai para `~/.config/omarchy/themes/<slug>` e aparece na
  prévia, sem `theme set`; conflito oferece cancelar ou substituir após
  backup; sem renomear ID de plugin;
- fallback sem par: `Guardar como arquivo` em `~/Downloads`, com o hash
  impresso para conferência por outro canal;
- `omarchy-manager share <id>` e `omarchy-manager receive [--convite]`.

Decisões:

- mDNS pelo `avahi-publish`/`avahi-browse` do sistema (o `avahi-daemon`
  está ativo nesta máquina; a stdlib do Python não fala mDNS e `zeroconf`
  não está instalado). Sem avahi, o anúncio é pulado e o convite colado à
  mão continua funcionando.
- QR Code: não há biblioteca no sistema; o convite é um texto
  `omarchy-manager://host:porta/fingerprint/segredo` que a interface mostra
  para copiar ou gerar QR por fora. Fica como melhoria.

**Não validado, exige 2 máquinas reais (não simulado):** descoberta mDNS
entre dispositivos distintos, roteamento em Wi-Fi doméstico, rede com
isolamento de clientes (quando bloqueia, a interface só oferece o arquivo),
IPv6 entre hosts, cancelamento no meio da transferência pela rede. O
loopback prova o protocolo, não a rede.

## 8. Empacotamento (plano, Fase 7)

Decisão: `packaging/PKGBUILD` com `depends=(python>=3.13 python-textual>=8
lua omarchy hyprland)`, todos de repositório oficial (`extra/python-textual
8.2.8-2`, conferido com `pacman -Ss` em 2026-11-13). Sem AUR e sem
vendorizar.

Motivo: a dúvida anterior nascia de um comando errado (ver seção 6, item 5).
Com o pacote oficial disponível, vendorizar o Textual (mais rich,
markdown-it-py, mdurl, platformdirs, pygments) duplicaria 5 pacotes que o
sistema já tem, perderia as atualizações de segurança do repositório e
precisaria de rede no `build()`, o que o makepkg desaconselha. Depender do
AUR faria a instalação exigir um helper como `yay`.

Como o pacote é construído e testado:

- `packaging/empacotar.sh`: `git archive HEAD` gera o tarball (sha256
  impresso), `makepkg -f --cleanbuild` constrói a wheel com
  `python -m build`, roda `check()` (os testes unitários dentro do build),
  instala com `python -m installer` e copia `agents/criador-de-temas.md`
  para `/usr/share/omarchy-manager/agents/` (o `AiLauncher` já procura ali),
  README, DECISOES e LICENSE; depois roda `namcap`;
- resultado em 2026-11-13: `omarchy-manager-0.1.0-1-any.pkg.tar.zst`,
  169.376 bytes, namcap sem `E:`. Os `W:` são dois falsos positivos
  conhecidos: módulos `omarchy_manager.*` apontados como "uninstalled
  dependency" (o namcap não vê o próprio pacote) e `lua`, `omarchy`,
  `hyprland` como "may not be needed" (são chamados por subprocesso, não
  importados);
- `sudo pacman -U` instalou o pacote nesta máquina; `omarchy-manager
  --versao` responde `0.1.0` em `/usr/bin`;
- `packaging/testar-conta-limpa.sh`: roda o binário instalado com `env -i`,
  HOME e XDG_* em um temporário vazio e PATH só do sistema. Passou: import
  vem de `/usr/lib/python3.14/site-packages`, as 3 abas abrem, 24 temas do
  sistema aparecem, só o HOME temporário recebe arquivos, nada em
  `/usr/share/omarchy`.

Limite: isso simula uma conta nova, não é uma. O compositor, o DBus e o
`omarchy-shell` em execução são os da sessão do JC, e sem
`HYPRLAND_INSTANCE_SIGNATURE` o ambiente limpo lista 0 atalhos e 0 plugins
(esperado). **Requer decisão do JC** se vale criar um usuário real e logar
nele para validar.

Instalados nesta máquina durante a Fase 7, com `sudo pacman -S` (todos
oficiais e removíveis com `pacman -Rns`): `python-build`,
`python-installer`, `python-hatchling`, `python-textual`, `namcap`,
`python-pytest`, `python-pytest-asyncio`, e o próprio `omarchy-manager`.
A configuração do Hyprland e do Omarchy do JC não foi tocada nesta fase.

## 10. Rodada de ajustes após o primeiro uso real (versão 0.2.0)

### Troca de abas

Relato: não dava para alternar entre as abas. Em pseudoterminal, com as
sequências do protocolo kitty e as legadas, as teclas `1` `2` `3` e o clique
na aba funcionaram enquanto o foco estava em uma tabela. O caso que prende é
o foco em um campo de texto (a pesquisa): ali os dígitos viram texto, e não
existia nenhum atalho de aba que funcionasse de dentro do campo. A tentativa
de reproduzir em uma janela real do Foot foi abandonada para não roubar o
foco de quem estava usando a máquina.

Correção: `Alt+L` / `Alt+→` e `Alt+H` / `Alt+←` com prioridade sobre o widget
em foco, mais `4` para a aba Config. Testes cobrem a troca com o foco na
pesquisa e o clique em cada aba. Se o problema original tiver outra causa
(por exemplo, algo específico do Herdr), ela não foi encontrada.

### Prévia ao vivo e a soltura do Ctrl

O Textual 8.2.8 liga o protocolo kitty com as flags 1, 8 e 16 (desambiguar,
reportar todas as teclas, texto associado), mas não a flag 2 (tipos de
evento). Sem ela o terminal não envia a soltura de tecla, e o parser do
Textual nem aceitaria o campo extra. Portanto a soltura do Ctrl não chega à
aplicação por nenhum terminal.

Decisão: o mecanismo garantido é a tecla `v`, que liga e desliga a prévia.
Para o Ctrl, a aplicação pergunta ao Hyprland (`hl.is_key_down("Control_L")`
e `Control_R` por `hyprctl eval`, 4 vezes por segundo, só com a aba Temas
ativa e o terminal em foco). A chamada funciona e devolve falso com a tecla
solta; um Ctrl sintético do `wtype` não é enxergado por ela, então o caso
"pressionado" só foi testado com o estado injetado nos testes. **Requer
validação manual com o teclado físico.** Se o Hyprland não responder, a
sondagem se desliga sozinha.

Garantia de restauração: o tema e o fundo originais vão para
`previa-original.json` antes do primeiro `omarchy theme set`. Restauram:
`v`, `Esc`, troca de aba, `q`, o `finally` de `main()`, `atexit`, SIGTERM e
SIGHUP, e a abertura seguinte se o arquivo ainda existir. Debounce de 0,5 s.

### Traduções dos plugins

Arquivo embutido com 80 plugins (os que existiam na máquina de
desenvolvimento em 2026-11-13) e arquivo do usuário com prioridade. A coluna
"Ações" da tabela deu lugar à coluna "Descrição"; as ações continuam nos
botões e nas teclas.

### QR Code

`extra/python-qrcode` existe no repositório oficial e entrou nas
dependências; sem a biblioteca, o programa usa `qrencode -t UTF8`; sem os
dois, mostra só o convite em texto. Desenho em blocos de meia altura, preto
sobre branco fixo para ser legível em tema claro e escuro.

### Distribuição como plugin do Omarchy

`omarchy plugin add <url-git>` clona o repositório inteiro para
`~/.config/omarchy/plugins/<id>/` e exige `manifest.json` na raiz, com
`schemaVersion` 1, um ponto de entrada por tipo declarado e nenhum link
simbólico. O formato só conhece os tipos `bar`, `bar-widget`, `menu`,
`overlay`, `panel` e `service`: não há como um plugin registrar atalho de
teclado, item no menu do Omarchy ou comando no PATH.

Decisão: o repositório é o plugin. Tipo `bar-widget`, com um ícone que chama
`omarchy-launch-tui` apontando para `bin/omarchy-manager` dentro da pasta do
plugin. Esse script usa o Python do sistema se ele já tiver o Textual 8 e,
se não, cria um venv em `~/.local/share/omarchy-manager/venv` com `uv` (ou
`python -m venv`) na primeira execução. O código roda direto de `src/`, por
`PYTHONPATH`, sem instalar nada no sistema.

O pacote pacman continua possível pelo `PKGBUILD`, mas não deve conviver com
o plugin: seriam duas cópias com versões que divergem a cada atualização.

### Publicação

Histórico refeito antes do primeiro push, com o e-mail
`noreply` do GitHub no autor, para não expor e-mail pessoal em repositório
público. Nome de pessoa em `LICENSE`, `pyproject.toml` e `PKGBUILD` trocado
pelo usuário do GitHub.

## 11. Imagem do fundo em pixels (versão 0.3.0)

Por que saía em blocos: era decisão da Fase 0 (seção 3). A aba Temas sempre
desenhava a miniatura em meio bloco, em qualquer terminal, por receio de o
Textual corromper um Sixel sobreposto. Não era falha de detecção: não havia
detecção. Os terminais em uso na máquina de desenvolvimento são Foot (que
desenha Sixel) e Herdr rodando dentro de um Foot.

Biblioteca: `textual-image` 0.14.4 foi avaliada. Faz o que é preciso (Sixel
e protocolo kitty dentro do Textual), mas não está nos repositórios oficiais
do Arch (só no AUR), exige `pillow` e é LGPL-3, o que complica copiar para
dentro de um projeto MIT. Decisão: não depender dela. O widget
`ui/imagem.py` usa a mesma técnica (linhas em branco para o Textual e a
imagem pendurada como segmento de controle na última linha, de modo que é o
compositor que decide quando redesenhar), em cerca de 150 linhas, e a
codificação fica com o ImageMagick, que já era dependência opcional. Assim o
pacote pacman e o venv do lançador funcionam sem nada novo.

Detecção: uma consulta ao terminal antes de o Textual assumir a entrada, com
APC de consulta do protocolo kitty, `CSI 16 t` (tamanho da célula) e `CSI c`
(atributos primários, onde o 4 indica Sixel e que também serve de
sentinela). Resultado em cache. O tamanho da célula é relido por `TIOCGWINSZ`
a cada desenho, porque muda com o zoom da fonte. O nome do terminal só entra
na frase que explica os blocos. `OMARCHY_MANAGER_IMAGEM=blocos|sixel|kitty`
força um modo.

Desempenho: decodificar um papel de parede grande leva de 1 a 2,6 s. Cada
arquivo é reduzido uma vez para um JPEG de até 1600 px em
`~/.cache/omarchy-manager/miniaturas/` e daí o Sixel sai em cerca de 0,3 s.
Tudo em thread, com cache em memória por (arquivo, tamanho do widget, tamanho
da célula) e descarte do pedido se o usuário já foi para outro tema.

Regras de desenho: a imagem só é emitida se o widget está inteiro na tela, a
tela está ativa (sem diálogo por cima) e a imagem foi gerada para o tamanho
atual. Em janela estreita (abaixo de 125 colunas) o painel rola, então ali
valem os blocos. A imagem kitty é apagada explicitamente ao trocar de aba,
abrir diálogo, esconder ou desmontar o widget; o Sixel some sozinho quando o
Textual repinta as células.

Blocos: quando há `chafa`, usa símbolos de bloco, meio bloco e quadrante
(o dobro da resolução horizontal do meio bloco); sem ele, o meio bloco
próprio. Uma linha abaixo da imagem diz por que ela está em blocos.

Achado no caminho: o `chafa` consulta o terminal de controle por conta
própria e, chamado de dentro da TUI, disputava a entrada do teclado (o `q`
deixava de sair). Corrigido com `--probe off` e com `stdin` fechado em todo
subprocesso.

O que foi visto e o que não foi:

- visto em captura de tela de um Foot real: a imagem do fundo em pixels no
  painel direito (Sixel) e, em janela estreita, os blocos do chafa;
- confirmado só pelas sequências emitidas, em um pseudoterminal que responde
  às consultas: posição e tamanho do Sixel, ausência de imagem ao trocar de
  aba e com diálogo aberto, redesenho ao voltar, e todo o caminho do
  protocolo kitty (transmissão, apagar ao sair da aba e ao abrir diálogo);
- não verificado: protocolo kitty em um kitty ou Ghostty de verdade (nenhum
  dos dois está instalado), o comportamento dentro do Herdr e do tmux (a
  detecção decide pelo que eles responderem), e rolagem com imagem.

## 12. Troca de fundo com h/l e padrão automático (versão 0.4.0)

Na aba Temas, `h`/`l` e as setas esquerda e direita percorrem em ciclo os
fundos do tema em foco. O fundo exibido passa a ser o padrão do tema, gravado
em `[theme_defaults]` pelo mesmo caminho atômico, 0,6 s depois da última
tecla. A gravação pendente é forçada ao mudar de tema, trocar de aba, abrir a
lista de fundos, sair e desmontar a aba.

- As setas vivem na tabela de temas (que antes as usava para rolar na
  horizontal); as letras são atalhos da aba e, com o foco na pesquisa, viram
  texto. `Alt+H`/`Alt+L` continuam sendo troca de aba.
- Nada é aplicado no sistema. A exceção é a prévia ao vivo ligada: aí o fundo
  da área de trabalho acompanha o exibido, e a restauração do tema e do fundo
  originais continua valendo.
- A tecla `p` e o botão viraram "Lista de fundos": o mesmo diálogo de antes,
  útil para pular direto a um fundo e a única forma de tirar o padrão.
- Tema com 0 ou 1 fundo: as teclas só deixam uma frase na linha de estado.

## 13. Navegação nos diálogos (versão 0.5.0)

Todos os diálogos herdam de `Dialogo` (`ui/dialogs.py`): esquerda/direita e
`h`/`l` andam entre os botões habilitados, em ciclo; cima/baixo e `j`/`k`
andam entre os controles ou navegam a lista em foco; com o foco em um campo
de texto, as letras e as setas horizontais são do campo, e cima/baixo saem
dele. Cada diálogo ganha uma linha de rodapé com as teclas. A captura de
atalho fica de fora da base de propósito, porque ali toda tecla é a resposta.

Destaque do foco: o botão "primário" era pintado de cor cheia mesmo sem foco
e parecia ser o selecionado. Agora só o botão em foco tem cor cheia (a de
destaque, ou a de erro em ação destrutiva); os outros ficam neutros. O foco
inicial de toda confirmação é `Cancelar`.

## 14. Transparência do Foot depois de trocar de tema (versão 0.6.0)

Sintoma: no Foot com fundo transparente, a TUI ficava opaca depois de
`Aplicar` e só voltava ao normal ao abrir de novo.

Causa: não era o caminho de recolorir da TUI. O `omarchy theme set` chama
`omarchy-theme-set-foot`, que escreve em todo Foot aberto um
`OSC 11;[alpha]cor`. O alpha vem só do `foot.ini` do tema; se o tema não
define alpha, o script manda `[100]`, opaco, e ignora o `alpha` que o usuário
pôs em `~/.config/foot/foot.ini`. Com `alpha-mode=all` a cor que a TUI pinta
em cada célula não muda nada: o que mudou foi o alpha do terminal. Uma janela
nova lê o `foot.ini` de novo e nasce transparente, daí a impressão de que
reabrir consertava. Medido em uma janela de teste: região com o papel de
parede visível na abertura, cor chapada depois do `OSC 11;[100]`, papel de
parede de volta depois de `OSC 11;[25]`.

Correção: ao recarregar a paleta (abertura, `Aplicar`, prévia ao vivo,
restauração, `F5`, saída com restauração), a TUI reenvia o OSC 11 ao próprio
terminal com o alpha lido do `foot.ini` do usuário (seguindo `include=`,
seção `colors-dark` ou `colors-light` conforme o tema). Só quando o terminal
responde ao XTVERSION como Foot (o `TERM` não serve: o Omarchy configura
`term=xterm-256color`) e o alpha configurado é menor que 1.

Limites: só a janela da TUI é corrigida. Os outros Foot abertos continuam
opacos depois de uma troca de tema, o que é comportamento do script do
Omarchy e acontece também quando o tema é trocado por fora. Dentro do Herdr
ou do tmux o XTVERSION não é do Foot e nada é enviado. Uma troca de tema
feita por fora com a TUI aberta só é corrigida no próximo `F5`.

Também ajustado: `aplicar_paleta` registra o tema do Textual sempre com o
mesmo nome por modo, então passou a pedir `refresh_css` explicitamente.

Sentido inverso (algo opaco já na abertura em tema claro): o teste confere
que tela, abas e painéis têm todos a cor de fundo do tema, em escuro e em
claro. Nenhum contêiner com cor própria foi encontrado.

## 15. Prompt do terminal com Oh My Posh

Fato: a opção de prompt da aba Terminal deixou de usar o Starship e passou a
usar o Oh My Posh (33.0.0, binário em `~/.local/bin/oh-my-posh`), com tema no
estilo M365Princess guardado em `~/.config/omarchy-manager/`. O app liga e
desliga um bloco entre marcadores no `~/.bashrc` (`oh-my-posh init bash
--config ...`), com backup a cada gravação. Operação idempotente e
reversível. Nada do Omarchy é alterado. Os segmentos usam texto branco ou
escuro conforme o fundo, sem texto preto sobre cor escura.

## 16. Aba Compartilhar

Pedido do JC: aba própria (tecla `7`) para oferecer e receber plugins,
temas, pastas e arquivos pela rede local, mantendo os diálogos `c` de
Plugins e Temas. As salvaguardas abaixo vieram do IAM e o JC pode vetar.

Fatos:

- `services/rede.py`: IPv4 por interface via `ip -j -4 addr` (sem loopback,
  cabo e Wi-Fi primeiro) e teste de porta por `bind` + `listen` real no IP
  escolhido, com `SO_REUSEADDR` como no servidor de envio.
- `services/oferta.py`: `Catalogo` (só entra o que foi marcado; a listagem
  pública traz id, tipo, nome, tamanho e nunca o caminho local),
  `ServidorOferta` (HTTPS TLS 1.3, certificado de `gerar_certificado`,
  vale 30 minutos) e `ClienteOferta`.
- Protocolo: `POST /conectar` pede a aprovação de quem oferece (IP do
  cliente e código de 6 palavras, 60 s para responder, 1 pedido por vez) e
  devolve um token de sessão preso ao IP; `GET /lista` e `GET /item/<id>`
  exigem o token. Sem aprovação, 403. Item baixado leva SHA-256, conferido
  pelo cliente.
- Sem convite não há segredo compartilhado. A confiança vem da fingerprint
  fixada pelo cliente, do código de 6 palavras derivado só dela (segredo
  vazio em `codigo_de_confirmacao`) e da aprovação manual. Os 2 lados
  precisam ver o mesmo código; o cliente o mostra antes de pedir a conexão.
- `bundle.py` ganhou o tipo `pasta`, que só vale para guardar em Downloads
  e é recusado por `instalar_recebido`. Plugin e tema recebidos usam
  `RevisarBundle` (em `ui/share.py`), que divide `resumo_do_bundle` e
  `instalar_revisado` com o `Receber`.
- `services/recebidos.py`: destino em `~/Downloads/omarchy-manager/`, nome
  reduzido ao basename, modo 0644 (diretórios 0755), `JaExiste` quando o
  destino existe; sobrescrever só após pergunta, com o antigo movido para
  `~/.local/state/omarchy-manager/backups/`.
- Arquivo marcado à mão com nome que casa as exclusões do bundle (token,
  secret, credential, chaves, `.env`) é recusado, no cadastro e de novo no
  envio. Essa regra é escolha de implementação, não pedido literal.
- Cores da caixa de porta: verde `#3fb950` e vermelho `#f85149` fixos. No
  tema ativo do JC (`green = #e75a50`) o verde da paleta é avermelhado e
  não distinguiria livre de ocupada.
- O CSS do app (`DataTable { height: 1fr }`) vence o `DEFAULT_CSS` dos
  widgets; as alturas das tabelas da aba são definidas por `styles.height`.

Testes: `tests/unit/test_rede_oferta.py`,
`tests/integration/test_oferta_loopback.py` e
`tests/integration/test_app_compartilhar.py`, todos só em 127.0.0.1.

Não validado: 2 máquinas reais (mDNS não é usado nesta aba), Wi-Fi com
isolamento de clientes, IPv6 (a aba só lista IPv4), firewall bloqueando a
porta escolhida (o teste de bind prova que dá para escutar, não que o outro
computador alcança).
