# omarchy-manager

Gerenciador em modo texto (TUI) para o Omarchy: atalhos do Hyprland, plugins
do Omarchy Shell e temas, em um único lugar, com teclado e mouse, em
português do Brasil e nas cores do tema ativo.

Versão 0.4.0. Feito para Omarchy com Hyprland em configuração Lua (testado
com Omarchy 4.5 e Hyprland 0.56.2).

## Instalar (como plugin do Omarchy)

```bash
omarchy plugin add https://github.com/JCsvg/omarchy-manager.git --enable
```

O Omarchy clona o repositório em
`~/.config/omarchy/plugins/io.github.jcsvg.omarchy-manager/`, valida o
manifesto e põe um ícone de engrenagem na barra. Clicar no ícone abre o
gerenciador em um terminal.

Aviso do próprio Omarchy, que vale aqui também: plugins rodam sem sandbox
dentro da sua sessão. Leia o código antes de instalar o de qualquer pessoa.

Na primeira abertura, se o Python do sistema não tiver o Textual, o
gerenciador cria um ambiente próprio em `~/.local/share/omarchy-manager/venv`
e instala ali `textual` e `qrcode` (precisa de internet, leva alguns
segundos). Para pular isso e usar os pacotes oficiais do Arch:

```bash
sudo pacman -S python-textual python-qrcode
```

Para chamar pelo terminal com o nome curto:

```bash
ln -s ~/.config/omarchy/plugins/io.github.jcsvg.omarchy-manager/bin/omarchy-manager ~/.local/bin/omarchy-manager
omarchy-manager
```

Atualizar: `omarchy plugin update io.github.jcsvg.omarchy-manager`

Remover: `omarchy plugin remove io.github.jcsvg.omarchy-manager`. Os arquivos
listados em "Arquivos do usuário" ficam; apague à mão se quiser. Se você
editou atalhos pelo gerenciador, apague também a linha de carregamento no fim
de `~/.config/hypr/bindings.lua` e o `omarchy-manager-bindings.lua`, e o
Hyprland volta aos atalhos originais no próximo reload.

Requisitos que já vêm com o Omarchy: `lua`, `hyprctl`, `omarchy`. Opcionais:
ImageMagick (`magick`) para a imagem dos fundos, `chafa` para blocos mais
nítidos em terminal sem gráficos, `openssl` e `avahi` para
o compartilhamento na rede local.

## Usar

| Tecla | O que faz |
|---|---|
| `Alt+L` / `Alt+→` | próxima aba (funciona de qualquer lugar, inclusive da pesquisa) |
| `Alt+H` / `Alt+←` | aba anterior |
| `1` `2` `3` `4` | Atalhos, Plugins, Temas, Config (fora de um campo de texto) |
| `/` | pesquisar |
| `j` `k` ou setas | navegar |
| `Enter` | executar a ação em foco |
| `Esc` | cancelar, limpar a pesquisa, desligar a prévia |
| `F5` | recarregar tudo |
| `?` | ajuda |
| `q` | sair |

O mouse seleciona linhas, aperta botões e troca de aba. A aba Config lista
todos os atalhos do programa e os caminhos dos arquivos que ele usa.

### Aba Atalhos

Lista os bindings efetivos do Hyprland com comando e origem (Omarchy,
usuário, plugin, gerenciador), pesquisa, filtro por origem e marcação de
duplicados. `e` edita: você pressiona a nova combinação, o programa mostra se
está livre ou quem já usa, e só grava depois da confirmação. A gravação vai
apenas para `~/.config/hypr/omarchy-manager-bindings.lua` (mais uma linha de
carregamento no fim do seu `bindings.lua`), com backup, e é desfeita sozinha
se o Hyprland acusar erro de configuração. `u` desfaz a última alteração.

### Aba Plugins

Todos os plugins que o Omarchy conhece, com nome e descrição em português.
`Espaço` liga ou desliga, `g` abre o repositório, `a` mostra os atalhos do
plugin, `c` compartilha, `d` desinstala (só plugin de terceiros, com
confirmação).

As traduções ficam em `src/omarchy_manager/data/plugins-pt-BR.json`. Para
corrigir uma ou traduzir um plugin que não está lá, crie
`~/.config/omarchy-manager/plugins-pt-BR.json` no mesmo formato:

```json
{ "id.do.plugin": { "nome": "Nome em português", "descricao": "O que ele faz." } }
```

Sem tradução, aparece o texto original do plugin.

### Aba Temas

Lista os temas, com paleta, exemplo de terminal e a imagem de fundo ao
lado. Em terminal que desenha imagens (Sixel no Foot; protocolo kitty no
kitty e no Ghostty) ela aparece em pixels de verdade; nos outros, ou em
janela estreita, em blocos coloridos, com uma linha dizendo o motivo. `h`/`l` ou as
setas esquerda e direita percorrem os fundos do tema em foco, e o fundo que
estiver exibido passa a ser o padrão daquele tema, sem passo extra (a
prévia mostra a posição, como "2 de 5"). Isso só guarda a escolha; nada
muda na área de trabalho, a não ser com a prévia ao vivo ligada. `p` abre a
lista de fundos, que também serve para tirar o padrão. `Enter` aplica o tema e a imagem padrão,
depois de confirmar.

Prévia ao vivo: `v` liga. Com ela ligada, o tema em foco na lista é aplicado
de verdade na área de trabalho, e cada mudança de linha troca o tema (com
meio segundo de espera para não disparar em rajada). `v` ou `Esc` desligam e
voltam ao tema e ao fundo de antes; trocar de aba e sair fazem o mesmo.
`Enter` mantém o tema que está na prévia. Segurar `Ctrl` por meio segundo
faz a prévia do tema em foco, ou do tema sob o mouse, enquanto a tecla
estiver pressionada (ver limites abaixo). Se o programa for morto no meio de
uma prévia, a próxima abertura restaura o tema anterior.

`Criar tema com IA` abre um chat (Claude Code, Codex, OpenCode ou Copilot
CLI, o que estiver instalado) em um terminal novo, dentro de uma pasta de
trabalho própria, com o agente de `agents/criador-de-temas.md`.

### Compartilhar com outro computador da mesma rede

Quem envia: `c` na aba Plugins (ou `Compartilhar` na aba Temas), depois
`Enviar na rede local`. Aparecem um código de 6 palavras, um convite em
texto e o QR Code do convite. Quem recebe: aba Temas, botão `Receber`, cola
o convite, confere se o código de 6 palavras é igual nos dois computadores e
baixa. Plugin recebido é instalado desligado; tema recebido não é aplicado.

Pelo terminal:

```bash
omarchy-manager share <id-do-plugin-ou-slug-do-tema>
omarchy-manager receive
```

A transferência é direta entre os dois computadores, por HTTPS com um
certificado criado só para aquele envio, vale por 10 minutos ou 1 download e
não passa por nenhum servidor na internet. Se a rede bloquear a conexão
entre os aparelhos, use `Guardar como arquivo` e mande o arquivo por outro
meio.

## Arquivos do usuário

```text
~/.config/omarchy-manager/config.toml            imagem padrão por tema
~/.config/omarchy-manager/plugin-shortcuts.toml  aliases plugin -> trecho de comando
~/.config/omarchy-manager/plugins-pt-BR.json     suas traduções de plugins
~/.config/hypr/omarchy-manager-bindings.lua      atalhos gerenciados (gerado)
~/.local/state/omarchy-manager/backups/          backups (20 mais recentes)
~/.local/state/omarchy-manager/manager.log       log de operações
~/.local/state/omarchy-manager/previa-original.json  tema a restaurar, só durante uma prévia
~/.local/share/omarchy-manager/                  ambiente Python, workspaces da IA, pacotes recebidos
```

Nada é gravado em `/usr/share/omarchy/`.

## Limites conhecidos

- Captura de `Super + tecla` na edição de atalhos: usa um submap temporário
  do Hyprland. A lógica tem teste, mas falta a validação com uma pessoa no
  teclado em todos os terminais.
- Prévia segurando `Ctrl`: o terminal não informa quando uma tecla é solta,
  então o programa pergunta ao Hyprland 4 vezes por segundo se o `Ctrl` está
  pressionado. Isso só foi testado com o estado do `Ctrl` simulado. Se não
  funcionar no seu teclado, a tecla `v` faz o mesmo de forma garantida.
- Compartilhamento: testado com os dois lados no mesmo computador. A
  descoberta automática (mDNS) entre aparelhos diferentes e o comportamento
  em Wi-Fi com isolamento de clientes ainda não foram validados; colar o
  convite ou ler o QR não depende da descoberta.
- O formato de plugin do Omarchy não tem campo para registrar atalho de
  teclado nem item de menu. Para abrir com uma tecla, adicione ao seu
  `~/.config/hypr/bindings.lua`, por exemplo:
  `o.bind("SUPER + CTRL + G", "Omarchy Manager", { tui = os.getenv("HOME") .. "/.config/omarchy/plugins/io.github.jcsvg.omarchy-manager/bin/omarchy-manager" })`

## Desenvolver

```bash
git clone https://github.com/JCsvg/omarchy-manager.git
cd omarchy-manager
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q
bin/omarchy-manager
```

Também há um `packaging/PKGBUILD` para quem preferir um pacote Arch
(`packaging/empacotar.sh`, depois `sudo pacman -U`). Não instale o pacote e
o plugin ao mesmo tempo: são duas cópias do mesmo programa.

`DECISOES.md` registra as provas técnicas e o porquê de cada escolha.
Licença MIT.
