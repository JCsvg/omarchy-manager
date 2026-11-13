"""Pseudoterminal que responde às consultas de gráficos como um terminal de verdade.

Uso: pty_grafico.py <executável> <sixel|kitty|nada> [colunas linhas]
Abre na aba Temas, espera a imagem, troca de aba e volta, e diz quais
sequências gráficas saíram em cada momento. Confirma as sequências emitidas;
não mostra nada na tela (para ver de verdade, abra em um Foot).
"""
import fcntl, os, pty, re, select, signal, struct, sys, termios, time

exe, modo = sys.argv[1], sys.argv[2]
cols, rows = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (170, 48)
CEL_L, CEL_A = 10, 20
pid, fd = pty.fork()
if pid == 0:
    os.execvpe(exe, [exe, "--aba", "temas"], {**{k: v for k, v in os.environ.items() if k != "HYPRLAND_INSTANCE_SIGNATURE"}, "TERM": "xterm-256color", "OMARCHY_MANAGER_IMAGEM": ""})  # sem Hyprland: o teste não lê o Ctrl real
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, cols * CEL_L, rows * CEL_A))

def ler(seg):
    buf, fim = b"", time.time() + seg
    while time.time() < fim:
        if select.select([fd], [], [], 0.05)[0]:
            try: dado = os.read(fd, 1 << 16)
            except OSError: break
            buf += dado
            if b"\x1b[c" in dado:  # consulta: responde como o terminal responderia
                resp = b""
                if modo == "kitty" and b"\x1b_Gi=31" in buf: resp += b"\x1b_Gi=31;OK\x1b\\"
                if b"\x1b[16t" in buf: resp += b"\x1b[6;%d;%dt" % (CEL_A, CEL_L)
                resp += b"\x1b[?62;4;22c" if modo == "sixel" else b"\x1b[?62;22c"
                os.write(fd, resp); print("  [harness respondeu à consulta]")
    return buf

def resumo(rotulo, b):
    six = re.findall(rb'\x1bP[0-9;]*q"\d+;\d+;(\d+);(\d+)', b)
    pos = re.findall(rb'\x1b\[(\d+);(\d+)H\x1bP', b)
    kit = re.findall(rb"\x1b_Ga=T,[^;]*", b)
    apg = len(re.findall(rb"\x1b_Ga=d,d=I", b))
    blocos = b.count("▀".encode()) + b.count("▄".encode())
    t = re.sub(rb"\x1bP.*?\x1b\\|\x1b_G.*?\x1b\\|\x1b\[[0-9;?<>=:]*[A-Za-z]", b"", b, flags=re.S).decode("utf-8", "replace")
    motivo = re.search(r"Imagem em blocos:[^\n\r]{0,90}", t)
    print(f"{rotulo}: sixel={[(int(w), int(h)) for w, h in six][:3]} em(lin,col)={[(int(a), int(c)) for a, c in pos][:3]} "
          f"kitty={len(kit)} apagar_kitty={apg} meio_blocos={blocos} bytes={len(b)}" + (f" | {motivo.group(0)}" if motivo else ""))

resumo("abertura (aba Temas)", ler(9))
os.write(fd, b"\x1b[B"); resumo("seta para baixo (outro tema)", ler(5))
os.write(fd, b"\x1bh"); resumo("Alt+H (sai da aba)", ler(3))
os.write(fd, b"\x1bl"); resumo("Alt+L (volta)", ler(4))
os.write(fd, b"?"); resumo("? (diálogo de ajuda por cima)", ler(3))
os.write(fd, b"\x1b"); resumo("Esc (fecha o diálogo)", ler(4))
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 100, 1000, 800)); os.kill(pid, signal.SIGWINCH)
resumo("janela estreita 100x40", ler(4))
os.write(fd, b"q"); t0 = time.time(); resto = ler(8); print("após q: %d bytes em 8 s" % len(resto))
if len(resto) > 2000:
    limpo = re.sub(rb"\x1bP.*?\x1b\\|\x1b_G.*?\x1b\\|\x1b\[[0-9;?<>=:]*[A-Za-z]", b"", resto, flags=re.S).decode("utf-8", "replace")
    print("texto após q:", " ".join(limpo.split())[:700])
try:
    w, st = os.waitpid(pid, os.WNOHANG)
    print("fim:", "travou" if w == 0 else f"exit {os.waitstatus_to_exitcode(st)}")
    if w == 0: os.kill(pid, signal.SIGKILL)
except ChildProcessError:
    print("fim: saiu")
