"""Dirige o omarchy-manager em um pseudoterminal real e imprime o que mudou na tela.

Uso: pty_drive.py <executável> <passo> [<passo>...]
Cada passo é `texto` (bytes enviados, com \\e para ESC) ou `sleep:N`.
Depois de cada passo imprime as palavras-chave vistas desde o passo anterior.
"""
import fcntl, os, pty, re, select, signal, struct, sys, termios, time

CHAVES = ["Carregando plugins", "plugins descobertos", "Carregando temas", "temas, atual", "Lendo atalhos",
          "atalhos,", "Tecla", "Traceback", "Prévia ao vivo", "Config"]

def main():
    exe, passos = sys.argv[1], sys.argv[2:]
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(exe, [exe], dict(os.environ, TERM="xterm-256color"))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 48, 160, 0, 0))
    def ler(seg):
        buf, fim = b"", time.time() + seg
        while time.time() < fim:
            if select.select([fd], [], [], 0.1)[0]:
                try: buf += os.read(fd, 65536)
                except OSError: break
        return re.sub(rb"\x1b\[[0-9;?<>=:]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[=>]", b"", buf).decode("utf-8", "replace")
    t = ler(5); print("inicio:", [c for c in CHAVES if c in t])
    for p in passos:
        if p.startswith("sleep:"):
            t = ler(float(p[6:]))
        else:
            os.write(fd, p.replace("\\e", "\x1b").encode()); t = ler(4)
        print(repr(p), "->", [c for c in CHAVES if c in t], "| abas ativas vistas:", sorted(set(re.findall(r"(?:FILTRO|Pesquisar (?:plugin|tema|por tecla))", t))))
    os.write(fd, b"\x1b[113;5u"); time.sleep(0.3); os.write(fd, b"\x03")
    time.sleep(1)
    try:
        w, st = os.waitpid(pid, os.WNOHANG)
        if w == 0: os.kill(pid, signal.SIGKILL); print("fim: precisou matar")
        else: print("fim: exit", os.waitstatus_to_exitcode(st))
    except ChildProcessError: print("fim: já saiu")
main()
