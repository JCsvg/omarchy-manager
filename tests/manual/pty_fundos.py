"""Em pseudoterminal com Sixel: aperta `l` duas vezes na aba Temas e confere que a
imagem muda sem sobrar a anterior. Usa HOME de configuração isolado: não toca no
config.toml real. Uso: pty_fundos.py <executável>"""
import fcntl, os, pty, re, select, struct, sys, tempfile, termios, time

exe = sys.argv[1]
tmp = tempfile.mkdtemp(prefix="omgr-fundos-")
env = {k: v for k, v in os.environ.items() if k != "HYPRLAND_INSTANCE_SIGNATURE"}
env.update(TERM="xterm-256color", XDG_CONFIG_HOME=tmp)
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
                os.write(fd, b"\x1b[6;20;10t\x1b[?62;4;22c")
    return buf

def resumo(rotulo, b):
    six = [(int(w), int(h), len(d)) for d, w, h in re.findall(rb'(\x1bP[0-9;]*q"\d+;\d+;(\d+);(\d+).*?\x1b\\)', b, flags=re.S)]
    t = re.sub(rb"\x1bP.*?\x1b\\|\x1b\[[0-9;?<>=:]*[A-Za-z]", b"", b, flags=re.S).decode("utf-8", "replace")
    pos = re.findall(r"(\d+ de \d+)", t)
    # entre uma imagem e a seguinte, a área precisa ser repintada em branco
    print(f"{rotulo}: sixels={six} posição={pos[-1] if pos else '-'} padrão={'sim' if '● padrão' in t else 'não'}")

resumo("abertura", ler(8))
os.write(fd, b"l"); resumo("l", ler(4))
os.write(fd, b"l"); resumo("l", ler(4))
os.write(fd, b"h"); resumo("h (volta, deve vir do cache)", ler(2))
os.write(fd, b"q"); ler(4)
cfg = os.path.join(tmp, "omarchy-manager", "config.toml"); print("config isolado:", open(cfg).read().strip().splitlines()[-1][:110] if os.path.exists(cfg) else "não gravado")
