"""Pseudoterminal que se identifica como Foot: confere que recarregar a paleta (F5) emite o
OSC 11 com o alpha do foot.ini e que as cores de fundo explícitas são as mesmas de antes.
Uso: pty_transparencia.py <executável>. Só lê; não aplica tema."""
import fcntl, os, pty, re, select, struct, sys, termios, time

exe = sys.argv[1]
env = {k: v for k, v in os.environ.items() if k != "HYPRLAND_INSTANCE_SIGNATURE"}
env["TERM"] = "xterm-256color"
pid, fd = pty.fork()
if pid == 0:
    os.execvpe(exe, [exe, "--aba", "temas"], env)
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 48, 170, 1700, 960))

def ler(seg):
    buf, fim = b"", time.time() + seg
    while time.time() < fim:
        if select.select([fd], [], [], 0.05)[0]:
            try: dado = os.read(fd, 1 << 16)
            except OSError: break
            buf += dado
            if b"\x1b[c" in dado:
                os.write(fd, b"\x1b[6;20;10t\x1bP>|foot(1.28.0)\x1b\\\x1b[?62;22c")
    return buf

def resumo(rotulo, b):
    osc = [o.decode() for o in re.findall(rb"\x1b\]11;([^\x07]*)\x07", b)]
    fundos = sorted(set(m.decode() for m in re.findall(rb"48;2;(\d+;\d+;\d+)", b)))
    print(f"{rotulo}: OSC 11 = {osc} | {len(fundos)} cores de fundo explícitas")
    return set(fundos)

a = resumo("abertura", ler(8))
os.write(fd, b"\x1b[15~")
b = resumo("F5 (recarrega a paleta)", ler(6))
print("cores de fundo novas depois do F5:", sorted(b - a) or "nenhuma")
os.write(fd, b"q"); ler(4)
