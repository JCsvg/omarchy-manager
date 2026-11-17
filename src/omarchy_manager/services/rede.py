"""Rede local: IPs das interfaces e teste real de porta (aba Compartilhar)."""

from __future__ import annotations

import errno
import json
import socket
from dataclasses import dataclass

from omarchy_manager.services.executor import ComandoAusente, executar


@dataclass(frozen=True)
class IpLocal:
    interface: str
    ip: str
    tipo: str  # "Wi-Fi", "cabo" ou "outra"


def _tipo(nome: str) -> str:
    if nome.startswith(("wl", "wlan")):
        return "Wi-Fi"
    if nome.startswith(("en", "eth", "eno", "enp")):
        return "cabo"
    return "outra"


def interpretar_ip_addr(texto: str) -> list[IpLocal]:
    """Lê a saída de `ip -j -4 addr`. Ignora loopback e interfaces sem IPv4."""
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError:
        return []
    saida: list[IpLocal] = []
    for itf in dados if isinstance(dados, list) else []:
        nome = str(itf.get("ifname", ""))
        if not nome or nome == "lo" or "LOOPBACK" in itf.get("flags", []):
            continue
        for a in itf.get("addr_info", []):
            ip = str(a.get("local", ""))
            if a.get("family") == "inet" and ip and not ip.startswith("127."):
                saida.append(IpLocal(nome, ip, _tipo(nome)))
    return sorted(saida, key=lambda i: i.tipo == "outra")  # cabo e Wi-Fi antes de docker, bridges, VPN


def ips_locais() -> list[IpLocal]:
    """IPv4 de cada interface (sem loopback). Lista vazia se `ip` não existir."""
    try:
        r = executar(["ip", "-j", "-4", "addr"], timeout=5)
    except ComandoAusente:
        return []
    return interpretar_ip_addr(r.stdout) if r.ok else []


def testar_porta(ip: str, porta: str | int) -> tuple[bool, str]:
    """Tenta escutar de verdade em ip:porta e solta em seguida. (livre, motivo)."""
    try:
        n = int(str(porta).strip())
    except ValueError:
        return False, "porta não é um número"
    if not 1 <= n <= 65535:
        return False, "porta fora de 1 a 65535"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # igual ao servidor HTTP do envio
        s.bind((ip, n))
        s.listen(1)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            return False, "porta ocupada"
        if exc.errno in (errno.EACCES, errno.EPERM):
            return False, "sem permissão (portas abaixo de 1024 exigem root)"
        if exc.errno == errno.EADDRNOTAVAIL:
            return False, "esse IP não pertence a este computador"
        return False, exc.strerror or "não foi possível escutar"
    finally:
        s.close()
    return True, "livre"
